#!/usr/bin/env python3
"""PySide6 desktop UI for the WeChat evidence capture tool."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QObject, QSize, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
)

from capture_core import (
    BYTES_PER_GB,
    BYTES_PER_MB,
    CAPTURE_METHODS,
    SCROLL_MODES,
    CaptureConfig,
    CaptureEvent,
    CaptureRunResult,
    default_end_date,
    default_start_date,
    run_capture,
    run_diagnostics,
    run_scroll_test,
)


APP_NAME = "WechatMessageCapture"
SETTINGS_FILE = "settings.json"


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / f".{APP_NAME}"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return app_data_dir() / SETTINGS_FILE


def read_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_settings(payload: dict[str, Any]) -> None:
    settings_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def qdate_from_iso(value: str) -> QDate:
    date = QDate.fromString(value, "yyyy-MM-dd")
    return date if date.isValid() else QDate.currentDate()


def iso_from_qdate(value: QDate) -> str:
    return value.toString("yyyy-MM-dd")


class CaptureWorker(QObject):
    event = Signal(object)
    finished = Signal(object)
    failed = Signal(str, str)

    def __init__(self, mode: str, config: CaptureConfig) -> None:
        super().__init__()
        self.mode = mode
        self.config = config
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    @Slot()
    def run(self) -> None:
        try:
            result: CaptureRunResult
            if self.mode == "capture":
                result = run_capture(self.config, callback=self.event.emit, stop_event=self.stop_event)
            elif self.mode == "scroll_test":
                result = run_scroll_test(self.config, callback=self.event.emit, stop_event=self.stop_event)
            elif self.mode == "diagnostics":
                result = run_diagnostics(self.config, callback=self.event.emit, stop_event=self.stop_event)
            else:
                raise ValueError(f"Unknown worker mode: {self.mode}")
            self.finished.emit(dataclasses.asdict(result))
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("微信截图取证工具")
        self.resize(1180, 760)
        self.settings = read_settings()
        self.last_scroll_result: dict[str, Any] | None = None
        self.last_output_dir = ""
        self.worker_thread: QThread | None = None
        self.worker: CaptureWorker | None = None

        self._build_ui()
        self._load_settings()
        self._apply_styles()

    def _build_ui(self) -> None:
        root = QWidget()
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(188)
        for label in ("首页", "第一步 准备", "第二步 测试校准", "第三步 正式采集"):
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(160, 44))
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self._switch_page)
        shell.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(16)

        self.status_banner = QLabel("请先阅读首页流程，再按步骤完成准备、测试校准和正式采集。")
        self.status_banner.setObjectName("statusBanner")
        self.status_banner.setWordWrap(True)
        content_layout.addWidget(self.status_banner)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        shell.addWidget(content, 1)

        self.stack.addWidget(self._build_home_page())
        self.stack.addWidget(self._build_prepare_page())
        self.stack.addWidget(self._scrollable_page(self._build_calibration_page()))
        self.stack.addWidget(self._build_capture_page())
        self.setCentralWidget(root)
        self.sidebar.setCurrentRow(0)

    def _build_home_page(self) -> QWidget:
        page = self._page()
        page.layout().addWidget(self._title("首页"))

        intro = QLabel(
            "这个工具用于自动保存已经打开的微信桌面版聊天窗口截图。"
            "它不会读取微信数据库，也不会自动判断聊天日期；你需要先把微信单聊或群聊单独弹出成聊天窗口。"
        )
        intro.setObjectName("bodyText")
        intro.setWordWrap(True)
        page.layout().addWidget(intro)

        flow = self._section("使用流程")
        flow_layout = QGridLayout(flow)
        flow_layout.setHorizontalSpacing(18)
        flow_layout.setVerticalSpacing(12)
        steps = (
            ("第一步 准备", "在微信聊天列表中双击目标单聊或群聊，让它单独弹出，再填写聊天窗口名、日期和总保存位置。"),
            ("第二步 测试校准", "运行一次测试，查看 before/after 缩略图，确认滚动幅度和截图重叠。"),
            ("第三步 正式采集", "开始后微信会占用前台；看到起始日期附近时按 Ctrl+Alt+S 停止。"),
        )
        for row, (heading, text) in enumerate(steps):
            heading_label = QLabel(heading)
            heading_label.setObjectName("stepHeading")
            text_label = QLabel(text)
            text_label.setObjectName("bodyText")
            text_label.setWordWrap(True)
            flow_layout.addWidget(heading_label, row, 0)
            flow_layout.addWidget(text_label, row, 1)
        flow_layout.setColumnStretch(1, 1)
        page.layout().addWidget(flow)

        calibration_notice = QLabel(
            "必须先测试校准再正式采集。不同显示器宽高、DPI、微信窗口大小都会影响滚动幅度；"
            "跳过测试可能导致相邻截图重叠不足、内容遗漏或截图效果不好。"
        )
        calibration_notice.setObjectName("notice")
        calibration_notice.setWordWrap(True)
        page.layout().addWidget(calibration_notice)

        stop_notice = QLabel(
            "正式采集的主要停止方式是 Ctrl+Alt+S。触发后不会立刻停在当前画面，"
            "程序会完成当前轮截图或滚动动作，再写入清单和哈希文件后结束。"
        )
        stop_notice.setObjectName("bodyText")
        stop_notice.setWordWrap(True)
        page.layout().addWidget(stop_notice)
        page.layout().addStretch(1)
        return page

    def _build_prepare_page(self) -> QWidget:
        page = self._page()
        title = self._title("第一步 准备")
        body = QLabel("先把要截图的微信单聊或群聊单独弹出成聊天窗口，再确认聊天停在最新消息位置。")
        body.setObjectName("bodyText")
        body.setWordWrap(True)
        page.layout().addWidget(title)
        page.layout().addWidget(body)

        window_notice = QLabel(
            "重要：必须在微信聊天列表中双击目标单聊或群聊，让聊天窗口单独展示。"
            "如果只在微信主窗口左侧聊天列表中打开，程序可能无法正确捕捉和滚动，正式采集会失败。"
        )
        window_notice.setObjectName("notice")
        window_notice.setWordWrap(True)
        page.layout().addWidget(window_notice)

        form_box = self._section("基础参数")
        form = QFormLayout(form_box)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        self.group_name = QLineEdit()
        self.group_name.setPlaceholderText("输入微信单聊或者群聊窗口标题中的识别文字")
        form.addRow("聊天窗口名", self.group_name)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("起始日期", self.start_date)

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("结束日期", self.end_date)

        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        self.output_dir = QLineEdit()
        self.output_dir.setPlaceholderText("选择总保存位置，每次运行会自动新建子文件夹")
        browse = QPushButton("选择目录")
        browse.clicked.connect(self._choose_output_dir)
        output_layout.addWidget(self.output_dir, 1)
        output_layout.addWidget(browse)
        form.addRow("总保存位置", output_row)
        form.addRow("", self._hint("例如选择 D:\\微信截图，正式采集时会自动生成 正式采集_20260610_234612 这样的本次运行文件夹。"))

        page.layout().addWidget(form_box)

        note = QLabel("正式采集期间微信会持续占用前台。停止采集请按 Ctrl+Alt+S，界面上的停止按钮只是辅助。")
        note.setObjectName("notice")
        note.setWordWrap(True)
        page.layout().addWidget(note)
        page.layout().addStretch(1)
        return page

    def _build_calibration_page(self) -> QWidget:
        page = self._page()
        page.layout().addWidget(self._title("第二步 测试校准"))
        intro = QLabel(
            "先测试当前电脑和微信窗口的滚动幅度。目标是相邻截图保留足够重叠，避免漏内容。"
            "完成后请优先看 before/after 两张图是否有重复聊天内容，百分比只是参考。"
        )
        intro.setObjectName("bodyText")
        intro.setWordWrap(True)
        page.layout().addWidget(intro)

        params = self._section("常用参数")
        form = QFormLayout(params)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.target_overlap = QSpinBox()
        self.target_overlap.setRange(20, 90)
        self.target_overlap.setSingleStep(5)
        self.target_overlap.setSuffix("%")
        self.target_overlap.setValue(35)
        self._add_form_row_with_side_hint(
            form,
            "重叠比例",
            self.target_overlap,
            "相邻截图保留的重复区域。太低会影响对比和查漏效果，建议 35%-50%，最低 20%。",
        )

        self.adaptive_fixed_steps = QSpinBox()
        self.adaptive_fixed_steps.setRange(0, 30)
        self.adaptive_fixed_steps.setValue(8)
        self._add_form_row_with_side_hint(
            form,
            "固定步数",
            self.adaptive_fixed_steps,
            "每张截图后执行几次滚轮步进。越大越快但更容易跳过内容；0 表示每轮重新测量，较慢但更稳。",
        )

        self.adaptive_step_clicks = QSpinBox()
        self.adaptive_step_clicks.setRange(-300, 300)
        self.adaptive_step_clicks.setSingleStep(10)
        self.adaptive_step_clicks.setValue(100)
        self._add_form_row_with_side_hint(
            form,
            "每步滚轮力度",
            self.adaptive_step_clicks,
            "单次滚轮步进的力度。绝对值越大移动越快但更容易跳过内容；测试发现方向反了再改成负数。",
        )

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.05, 10.0)
        self.interval.setSingleStep(0.05)
        self.interval.setDecimals(2)
        self.interval.setValue(0.2)
        self.interval.setSuffix(" 秒")
        self._add_form_row_with_side_hint(
            form,
            "截图间隔（单位：秒）",
            self.interval,
            "每次滚动后等待微信界面稳定再截图。太低可能截到未刷新画面，最低 0.05 秒，建议从 0.2 秒开始。",
        )
        page.layout().addWidget(params)

        self.advanced_params_toggle = QCheckBox("高级参数")
        self.advanced_params_toggle.setObjectName("advancedToggle")
        page.layout().addWidget(self.advanced_params_toggle)

        self.advanced_params_box = self._section("高级参数设置")
        advanced_form = QFormLayout(self.advanced_params_box)
        advanced_form.setHorizontalSpacing(16)
        advanced_form.setVerticalSpacing(12)
        advanced_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.capture_method = QComboBox()
        self.capture_method.addItems(("auto", *CAPTURE_METHODS))
        self._add_form_row_with_side_hint(
            advanced_form,
            "截图方式",
            self.capture_method,
            "auto：自动尝试并选择可用方式；imagegrab：系统截图，通常优先；pyautogui：通用截图，兼容性较好；mss-full：截全屏后裁切，适合多屏排查；mss-window：按窗口区域截图，部分电脑可能黑屏。",
        )

        self.scroll_mode = QComboBox()
        self.scroll_mode.addItems(SCROLL_MODES)
        self.scroll_mode.setCurrentText("adaptive")
        self._add_form_row_with_side_hint(
            advanced_form,
            "滚动模式",
            self.scroll_mode,
            "adaptive 会按重叠目标控制滚动；wheel、pageup、drag 主要用于排查，可能跳动更大。",
        )

        self.scroll_x_ratio = QDoubleSpinBox()
        self.scroll_x_ratio.setRange(0.10, 0.95)
        self.scroll_x_ratio.setSingleStep(0.01)
        self.scroll_x_ratio.setDecimals(2)
        self.scroll_x_ratio.setValue(0.68)
        self._add_form_row_with_side_hint(
            advanced_form,
            "滚动 X 比例",
            self.scroll_x_ratio,
            "点击和滚动位置的横向比例。滚不到聊天区时调整，数值越大越靠窗口右侧。",
        )

        self.scroll_y_ratio = QDoubleSpinBox()
        self.scroll_y_ratio.setRange(0.10, 0.95)
        self.scroll_y_ratio.setSingleStep(0.01)
        self.scroll_y_ratio.setDecimals(2)
        self.scroll_y_ratio.setValue(0.55)
        self._add_form_row_with_side_hint(
            advanced_form,
            "滚动 Y 比例",
            self.scroll_y_ratio,
            "点击和滚动位置的纵向比例。滚动没有生效时调整，让鼠标落在聊天内容区域。",
        )

        self.duplicate_threshold = QDoubleSpinBox()
        self.duplicate_threshold.setRange(0.0, 0.1)
        self.duplicate_threshold.setSingleStep(0.001)
        self.duplicate_threshold.setDecimals(3)
        self.duplicate_threshold.setValue(0.003)
        self._add_form_row_with_side_hint(
            advanced_form,
            "重复阈值",
            self.duplicate_threshold,
            "判断两张图是否几乎相同。越高越容易判重复并停止，越低会保留更多近似截图。",
        )

        self.stable_limit = QSpinBox()
        self.stable_limit.setRange(0, 100)
        self.stable_limit.setValue(8)
        self._add_form_row_with_side_hint(
            advanced_form,
            "稳定停止次数",
            self.stable_limit,
            "连续多次画面变化很小时自动结束。太低可能提前停止，太高会多做重复尝试。",
        )
        self.advanced_params_box.setVisible(False)
        self.advanced_params_toggle.toggled.connect(self._set_advanced_params_visible)
        page.layout().addWidget(self.advanced_params_box)

        actions = QHBoxLayout()
        self.scroll_test_button = QPushButton("运行测试校准")
        self.scroll_test_button.setObjectName("primaryButton")
        self.scroll_test_button.clicked.connect(self._start_scroll_test)
        self.diagnostics_button = QPushButton("截图诊断")
        self.diagnostics_button.clicked.connect(self._start_diagnostics)
        self.save_calibration_button = QPushButton("保存当前配置")
        self.save_calibration_button.clicked.connect(self._save_calibration)
        actions.addWidget(self.scroll_test_button)
        actions.addWidget(self.diagnostics_button)
        actions.addStretch(1)
        actions.addWidget(self.save_calibration_button)
        page.layout().addLayout(actions)

        self.calibration_loading_text = QLabel("正在启动测试校准，请保持微信窗口可见。")
        self.calibration_loading_text.setObjectName("bodyText")
        self.calibration_loading_text.setVisible(False)
        self.calibration_loading = QProgressBar()
        self.calibration_loading.setObjectName("loadingBar")
        self.calibration_loading.setRange(0, 0)
        self.calibration_loading.setTextVisible(False)
        self.calibration_loading.setVisible(False)
        page.layout().addWidget(self.calibration_loading_text)
        page.layout().addWidget(self.calibration_loading)

        result_box = self._section("测试结果")
        result_layout = QGridLayout(result_box)
        self.before_preview = self._preview_label("before.png")
        self.after_preview = self._preview_label("after.png")
        self.calibration_summary = QLabel("还没有运行测试校准。")
        self.calibration_summary.setObjectName("bodyText")
        self.calibration_summary.setWordWrap(True)
        result_layout.addWidget(self.before_preview, 0, 0)
        result_layout.addWidget(self.after_preview, 0, 1)
        result_layout.addWidget(self.calibration_summary, 1, 0, 1, 2)
        page.layout().addWidget(result_box)
        page.layout().addStretch(1)
        return page

    def _build_capture_page(self) -> QWidget:
        page = self._page()
        page.layout().addWidget(self._title("第三步 正式采集"))
        warning = QLabel(
            "点击开始后，微信窗口会反复被置前并接收滚动操作。看到起始日期附近时，请按 Ctrl+Alt+S 停止；"
            "快捷键触发后会完成当前轮截图或滚动动作再结束。"
        )
        warning.setObjectName("notice")
        warning.setWordWrap(True)
        page.layout().addWidget(warning)

        protection = self._section("采集保护")
        protection_form = QFormLayout(protection)
        protection_form.setHorizontalSpacing(16)
        protection_form.setVerticalSpacing(10)
        protection_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.min_free_space_gb = QDoubleSpinBox()
        self.min_free_space_gb.setRange(1.0, 1024.0)
        self.min_free_space_gb.setDecimals(1)
        self.min_free_space_gb.setSingleStep(1.0)
        self.min_free_space_gb.setValue(10.0)
        self.min_free_space_gb.setSuffix(" GB")
        self._add_form_row_with_side_hint(
            protection_form,
            "至少保留磁盘空间（GB）",
            self.min_free_space_gb,
            "保存位置所在磁盘低于这个剩余空间时自动停止，避免长时间截图把电脑存储占满。建议普通用户保留 10 GB。",
        )
        page.layout().addWidget(protection)

        actions = QHBoxLayout()
        self.start_capture_button = QPushButton("开始正式采集")
        self.start_capture_button.setObjectName("primaryButton")
        self.start_capture_button.clicked.connect(self._confirm_and_start_capture)
        self.stop_button = QPushButton("辅助停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._request_stop)
        self.open_output_button = QPushButton("打开本次文件夹")
        self.open_output_button.clicked.connect(self._open_last_output)
        actions.addWidget(self.start_capture_button)
        actions.addWidget(self.stop_button)
        actions.addStretch(1)
        actions.addWidget(self.open_output_button)
        page.layout().addLayout(actions)

        stats = self._section("采集状态")
        stats_layout = QGridLayout(stats)
        self.capture_state = QLabel("未开始")
        self.capture_count = QLabel("0 张，共计 0 MB")
        self.capture_output = QLabel("未生成")
        self.capture_output.setTextInteractionFlags(Qt.TextSelectableByMouse)
        stats_layout.addWidget(QLabel("状态"), 0, 0)
        stats_layout.addWidget(self.capture_state, 0, 1)
        stats_layout.addWidget(QLabel("已保存截图"), 1, 0)
        stats_layout.addWidget(self.capture_count, 1, 1)
        stats_layout.addWidget(QLabel("本次运行文件夹"), 2, 0)
        stats_layout.addWidget(self.capture_output, 2, 1)
        page.layout().addWidget(stats)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("logView")
        page.layout().addWidget(self.log_view, 1)
        return page

    def _page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        return page

    def _scrollable_page(self, page: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(page)
        return area

    def _title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("pageTitle")
        return label

    def _section(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        return box

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("hintText")
        label.setWordWrap(True)
        return label

    def _add_form_row_with_hint(self, form: QFormLayout, label: str, widget: QWidget, hint: str) -> None:
        widget.setToolTip(hint)
        form.addRow(label, widget)
        form.addRow("", self._hint(hint))

    def _add_form_row_with_side_hint(self, form: QFormLayout, label: str, widget: QWidget, hint: str) -> None:
        widget.setToolTip(hint)
        widget.setMinimumWidth(240)
        widget.setMaximumWidth(340)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(14)
        hint_label = self._hint(hint)
        hint_label.setMinimumWidth(260)
        row_layout.addWidget(widget, 0)
        row_layout.addWidget(hint_label, 1)
        form.addRow(label, row)

    def _set_advanced_params_visible(self, checked: bool) -> None:
        if hasattr(self, "advanced_params_box"):
            self.advanced_params_box.setVisible(checked)

    def _preview_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumHeight(150)
        label.setObjectName("preview")
        label.setScaledContents(False)
        return label

    def _apply_styles(self) -> None:
        QApplication.setFont(QFont("Microsoft YaHei UI", 9))
        self.setStyleSheet(
            """
            QMainWindow { background: #f7f9fb; color: #27313a; }
            #sidebar { background: #e8eef3; border: 0; padding: 12px; }
            #sidebar::item { border-radius: 8px; padding: 10px 12px; color: #364650; }
            #sidebar::item:selected { background: #168f84; color: white; }
            QLabel#pageTitle { font-size: 24px; font-weight: 700; color: #202a31; }
            QLabel#bodyText { color: #485963; line-height: 1.35; }
            QLabel#hintText { color: #5e6d77; line-height: 1.35; font-size: 12px; }
            QLabel#stepHeading { color: #202a31; font-weight: 700; }
            QCheckBox#advancedToggle {
                color: #202a31;
                font-weight: 600;
                padding: 8px 0 2px 2px;
            }
            QLabel#statusBanner {
                background: #e8f5f3;
                color: #0f5f58;
                border: 1px solid #9fd6cf;
                border-radius: 8px;
                padding: 10px 12px;
            }
            QLabel#notice {
                background: #fff7df;
                color: #6a4d00;
                border: 1px solid #e3c86b;
                border-radius: 8px;
                padding: 10px 12px;
            }
            QGroupBox {
                background: white;
                border: 1px solid #d7dee5;
                border-radius: 8px;
                margin-top: 18px;
                padding: 14px;
                font-weight: 600;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
            QLineEdit, QDateEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                min-height: 30px;
                border: 1px solid #c4cdd6;
                border-radius: 6px;
                padding: 4px 8px;
                background: white;
                color: #27313a;
            }
            QLineEdit:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #168f84;
            }
            QPushButton {
                min-height: 32px;
                border: 1px solid #c4cdd6;
                border-radius: 7px;
                padding: 6px 12px;
                background: white;
                color: #27313a;
            }
            QPushButton:hover { background: #f1f5f8; }
            QPushButton:disabled { color: #8a98a5; background: #eef2f5; }
            QPushButton#primaryButton {
                background: #168f84;
                border: 1px solid #0f776d;
                color: white;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover { background: #0f776d; }
            QTextEdit#logView {
                background: #1f2930;
                color: #e9eef2;
                border: 0;
                border-radius: 8px;
                padding: 10px;
                font-family: Consolas, "Microsoft YaHei UI";
            }
            QLabel#preview {
                background: #edf2f5;
                border: 1px solid #cbd5dd;
                border-radius: 8px;
                color: #596b76;
            }
            QProgressBar#loadingBar {
                min-height: 8px;
                max-height: 8px;
                border: 0;
                border-radius: 4px;
                background: #dfe7ec;
            }
            QProgressBar#loadingBar::chunk {
                border-radius: 4px;
                background: #168f84;
            }
            """
        )

    def _switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def _load_settings(self) -> None:
        today = default_end_date()
        self.group_name.setText(self.settings.get("group_name", ""))
        self.start_date.setDate(qdate_from_iso(self.settings.get("start_date", default_start_date())))
        self.end_date.setDate(qdate_from_iso(self.settings.get("end_date", today)))
        self.output_dir.setText(self.settings.get("output_dir", ""))
        target_overlap = float(self.settings.get("target_overlap", 0.35))
        target_overlap_percent = round(target_overlap * 100 if target_overlap <= 1 else target_overlap)
        self.target_overlap.setValue(target_overlap_percent)
        self.adaptive_fixed_steps.setValue(int(self.settings.get("adaptive_fixed_steps", 8)))
        self.adaptive_step_clicks.setValue(int(self.settings.get("adaptive_step_clicks", 100)))
        self.interval.setValue(float(self.settings.get("interval", 0.2)))
        self.capture_method.setCurrentText(self.settings.get("capture_method", "auto"))
        self.scroll_mode.setCurrentText(self.settings.get("scroll_mode", "adaptive"))
        self.scroll_x_ratio.setValue(float(self.settings.get("scroll_x_ratio", 0.68)))
        self.scroll_y_ratio.setValue(float(self.settings.get("scroll_y_ratio", 0.55)))
        self.duplicate_threshold.setValue(float(self.settings.get("duplicate_threshold", 0.003)))
        self.stable_limit.setValue(int(self.settings.get("stable_limit", 8)))
        self.min_free_space_gb.setValue(float(self.settings.get("min_free_space_gb", 10.0)))

    def _settings_payload(self, calibrated: bool | None = None) -> dict[str, Any]:
        payload = dict(self.settings)
        payload.update(
            {
                "group_name": self.group_name.text().strip(),
                "start_date": iso_from_qdate(self.start_date.date()),
                "end_date": iso_from_qdate(self.end_date.date()),
                "output_dir": self.output_dir.text().strip(),
                "target_overlap": self._overlap_ratio_from_ui(),
                "adaptive_fixed_steps": self.adaptive_fixed_steps.value(),
                "adaptive_step_clicks": self.adaptive_step_clicks.value(),
                "interval": self.interval.value(),
                "capture_method": self.capture_method.currentText(),
                "scroll_mode": self.scroll_mode.currentText(),
                "scroll_x_ratio": self.scroll_x_ratio.value(),
                "scroll_y_ratio": self.scroll_y_ratio.value(),
                "duplicate_threshold": self.duplicate_threshold.value(),
                "stable_limit": self.stable_limit.value(),
                "min_free_space_gb": self.min_free_space_gb.value(),
            }
        )
        if calibrated is not None:
            payload["calibrated"] = calibrated
        return payload

    def _overlap_ratio_from_ui(self) -> float:
        return self.target_overlap.value() / 100.0

    def _config_from_ui(self, run_label: str = "") -> CaptureConfig | None:
        group_name = self.group_name.text().strip()
        if not group_name:
            QMessageBox.warning(self, "缺少聊天窗口名", "请输入微信单聊或者群聊窗口标题中的识别文字。")
            self.sidebar.setCurrentRow(1)
            return None
        start = iso_from_qdate(self.start_date.date())
        end = iso_from_qdate(self.end_date.date())
        if start > end:
            QMessageBox.warning(self, "日期不正确", "起始日期不能晚于结束日期。")
            return None
        if self.adaptive_step_clicks.value() == 0:
            QMessageBox.warning(self, "滚轮力度不正确", "每步滚轮力度不能为 0。正数向上找更早消息，方向反了再改成负数。")
            self.sidebar.setCurrentRow(2)
            return None
        try:
            output_dir = self._make_run_output_dir(run_label)
        except OSError as exc:
            QMessageBox.warning(self, "保存位置不可用", f"无法创建保存位置，请重新选择总保存位置。\n\n{exc}")
            self.sidebar.setCurrentRow(1)
            return None
        return CaptureConfig(
            group_name=group_name,
            start_date=start,
            end_date=end,
            output_dir=output_dir,
            min_free_space_gb=self.min_free_space_gb.value(),
            interval=self.interval.value(),
            scroll_mode=self.scroll_mode.currentText(),
            target_overlap=self._overlap_ratio_from_ui(),
            adaptive_fixed_steps=self.adaptive_fixed_steps.value(),
            adaptive_step_clicks=self.adaptive_step_clicks.value(),
            capture_method=self.capture_method.currentText(),
            scroll_x_ratio=self.scroll_x_ratio.value(),
            scroll_y_ratio=self.scroll_y_ratio.value(),
            duplicate_threshold=self.duplicate_threshold.value(),
            stable_limit=self.stable_limit.value(),
        )

    def _make_run_output_dir(self, run_label: str) -> str:
        parent_text = self.output_dir.text().strip()
        if not parent_text:
            return ""
        parent = Path(parent_text).expanduser()
        parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = run_label or "运行"
        candidate = parent / f"{safe_label}_{stamp}"
        suffix = 2
        while candidate.exists():
            candidate = parent / f"{safe_label}_{stamp}_{suffix:02d}"
            suffix += 1
        return str(candidate)

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择总保存位置", self.output_dir.text() or str(Path.home()))
        if directory:
            self.output_dir.setText(directory)

    def _set_running(self, running: bool, mode: str = "") -> None:
        for button in (self.scroll_test_button, self.diagnostics_button, self.start_capture_button):
            button.setEnabled(not running)
        self.stop_button.setEnabled(running and mode == "capture")
        calibration_running = running and mode == "scroll_test"
        diagnostics_running = running and mode == "diagnostics"
        self.calibration_loading_text.setVisible(calibration_running or diagnostics_running)
        self.calibration_loading.setVisible(calibration_running or diagnostics_running)
        if calibration_running:
            self.calibration_loading_text.setText("正在启动测试校准，请保持微信窗口可见。")
            self.scroll_test_button.setText("测试校准运行中")
            self.calibration_summary.setText("正在准备截图和滚动测试，通常需要几秒。请保持微信窗口可见。")
        elif diagnostics_running:
            self.calibration_loading_text.setText("正在运行截图诊断，请保持微信窗口可见。")
            self.diagnostics_button.setText("诊断运行中")
            self.calibration_summary.setText("正在测试不同截图方式，完成后会提示诊断图片的保存目录和文件名。")
        else:
            self.scroll_test_button.setText("运行测试校准")
            self.diagnostics_button.setText("截图诊断")

    def _start_worker(self, mode: str, config: CaptureConfig) -> None:
        if self.worker_thread is not None:
            QMessageBox.information(self, "正在运行", "已有任务正在运行，请等待完成或先停止。")
            return
        self._set_running(True, mode)
        self.worker_thread = QThread()
        self.worker = CaptureWorker(mode, config)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.event.connect(self._handle_capture_event)
        self.worker.finished.connect(self._handle_worker_finished)
        self.worker.failed.connect(self._handle_worker_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _start_scroll_test(self) -> None:
        config = self._config_from_ui("测试校准")
        if config is None:
            return
        self.status_banner.setText("正在运行测试校准。请不要操作微信窗口。")
        self.sidebar.setCurrentRow(2)
        self.log_view.append("开始测试校准")
        self._start_worker("scroll_test", config)

    def _start_diagnostics(self) -> None:
        config = self._config_from_ui("截图诊断")
        if config is None:
            return
        self.status_banner.setText("正在运行截图诊断。诊断不会滚动聊天。")
        self.sidebar.setCurrentRow(2)
        self.log_view.append("开始截图诊断")
        self._start_worker("diagnostics", config)

    def _confirm_and_start_capture(self) -> None:
        config = self._config_from_ui("正式采集")
        if config is None:
            return
        calibrated = bool(self.settings.get("calibrated"))
        message = (
            "开始后微信会占用前台并自动滚动。\n\n"
            "看到起始日期附近时，请按 Ctrl+Alt+S 停止。快捷键触发后不会立刻停在当前画面，"
            "程序会完成当前轮截图或滚动动作，随后写入清单和哈希文件再结束。\n\n"
            f"当前设置会至少保留 {config.min_free_space_gb:g} GB 磁盘空间；"
            "如果保存位置所在磁盘低于这个值，程序会自动停止，已保存的截图仍会保留。"
        )
        if not calibrated:
            message += "\n\n当前没有保存过测试校准配置，建议先运行测试校准。仍要继续吗？"
        reply = QMessageBox.question(self, "确认开始采集", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.settings = self._settings_payload(calibrated=calibrated)
        write_settings(self.settings)
        self.capture_count.setText("0 张，共计 0 MB")
        self.capture_state.setText("采集中，按 Ctrl+Alt+S 停止，当前轮完成后结束")
        self.status_banner.setText("采集中，按 Ctrl+Alt+S 停止。触发后会完成当前轮再结束，GUI 停止按钮仅作为辅助。")
        self.sidebar.setCurrentRow(3)
        self.log_view.clear()
        self.log_view.append("正式采集开始。主停止方式：Ctrl+Alt+S")
        self._start_worker("capture", config)

    def _request_stop(self) -> None:
        if isinstance(self.worker, CaptureWorker):
            self.worker.stop()
            self.status_banner.setText("已请求停止。正在完成当前轮截图或滚动动作，然后写入清单和哈希。")
            self.capture_state.setText("正在停止，等待当前轮完成")

    def _handle_capture_event(self, event: CaptureEvent) -> None:
        data = event.data or {}
        if event.kind == "log":
            self.log_view.append(event.message)
        elif event.kind == "screenshot_saved":
            saved_index = data.get("saved_index", "")
            self.capture_count.setText(
                f"{saved_index} 张，共计 {self._format_file_size(data.get('total_saved_size_bytes'))}"
            )
            self.capture_state.setText("采集中，按 Ctrl+Alt+S 停止，当前轮完成后结束")
        elif event.kind == "window_selected":
            self.log_view.append(event.message)
        elif event.kind == "stop_requested":
            hotkey = data.get("hotkey", "Ctrl+Alt+S")
            self.status_banner.setText(f"已收到 {hotkey}，正在结束中。当前轮完成后会写入清单和哈希。")
            self.capture_state.setText("正在结束中，等待当前轮完成")
            self.log_view.append(f"已收到停止快捷键：{hotkey}")
        elif event.kind == "low_disk_space":
            free_gb = self._format_number(data.get("free_gb"), 1)
            min_gb = self._format_number(data.get("min_free_space_gb"), 1)
            self.status_banner.setText("磁盘空间不足，已自动结束。已保存的截图仍在本次运行文件夹中。")
            self.capture_state.setText("磁盘空间不足，正在结束")
            self.log_view.append(f"磁盘空间不足：当前剩余约 {free_gb} GB，低于设置的 {min_gb} GB。")
        elif event.kind == "finished":
            self.capture_state.setText(f"已结束：{data.get('stop_reason', '')}")
        elif event.message:
            self.log_view.append(event.message)

    def _handle_worker_finished(self, result: dict[str, Any]) -> None:
        self.last_output_dir = result.get("output_dir", "")
        self.capture_output.setText(self.last_output_dir or "未生成")
        stop_reason = result.get("stop_reason", "")
        if stop_reason == "low_disk_space":
            self.status_banner.setText("磁盘空间不足，已自动结束。已保存的截图仍在本次运行文件夹中。")
            self.capture_state.setText("磁盘空间不足，已自动结束")
        else:
            self.status_banner.setText(f"任务完成：{stop_reason}")
        self.log_view.append(f"任务完成：{stop_reason}")
        if result.get("scroll_test_result"):
            self.last_scroll_result = result["scroll_test_result"]
            self._render_scroll_result(result["scroll_test_result"], self.last_output_dir)
        self._set_running(False)
        if result.get("diagnostics_result"):
            self._show_diagnostics_result(result["diagnostics_result"])

    def _handle_worker_failed(self, message: str, detail: str) -> None:
        self.status_banner.setText("任务失败。请查看日志。")
        self.log_view.append("ERROR: " + message)
        self.log_view.append(detail)
        QMessageBox.critical(self, "任务失败", message)
        self._set_running(False)

    def _cleanup_worker(self) -> None:
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker_thread = None
        self.worker = None

    def _render_scroll_result(self, result: dict[str, Any], output_dir: str) -> None:
        before = result.get("before", {}).get("relative_path", "测试校准图片/before.png")
        after = result.get("after", {}).get("relative_path", "测试校准图片/after.png")
        self._set_preview(self.before_preview, Path(output_dir) / before)
        self._set_preview(self.after_preview, Path(output_dir) / after)
        movement = float(result.get("estimated_shift_ratio") or 0)
        overlap = self._overlap_ratio_from_ui()
        reference_size = result.get("reference_screenshot_size_bytes")
        disk_space = result.get("disk_space") or {}
        free_space = disk_space.get("free_bytes")
        estimated_remaining = result.get("estimated_remaining_screenshots")
        if isinstance(estimated_remaining, int):
            remaining_text = f"约 {estimated_remaining:,} 张"
        else:
            remaining_text = "暂时无法估算"
        self.calibration_summary.setText(
            "图像估算移动："
            f"{movement:.1%}，仅作为参考，微信聊天里的空白、头像和固定区域可能让这个数偏低。\n"
            f"请直接看上面两张图：如果 before 和 after 之间仍能看到大约 {overlap:.0%} 的相同聊天内容，"
            "就可以保存当前配置；如果两张图几乎接不上，降低固定步数或每步滚轮力度；"
            "如果几乎没动，再增大固定步数或每步滚轮力度。\n\n"
            f"本次测试截图约 {self._format_file_size(reference_size)}/张，仅作参考。"
            "实际截图大小会随聊天内容、图片、表情、窗口大小变化。\n"
            f"当前保存位置所在磁盘可用 {self._format_file_size(free_space)}。\n"
            f"按当前保留空间设置，粗略估计还能保存 {remaining_text}。"
        )
        self.sidebar.setCurrentRow(2)

    def _show_diagnostics_result(self, result: dict[str, Any]) -> None:
        diagnostics_dir = Path(self.last_output_dir) / result.get("diagnostics_dir", "诊断图片")
        image_names = [
            Path(method.get("relative_path", "")).name
            for method in result.get("methods", [])
            if method.get("ok") and method.get("relative_path")
        ]
        image_summary = "\n".join(image_names[:8]) if image_names else "未生成可用诊断图片，请查看日志。"
        self.calibration_summary.setText(f"诊断完成。图片保存在：{diagnostics_dir}")
        self.status_banner.setText("截图诊断完成。请打开本次运行文件夹里的“诊断图片”。")
        QMessageBox.information(
            self,
            "诊断完成",
            f"诊断图片已保存到：\n{diagnostics_dir}\n\n文件名：\n{image_summary}",
        )

    def _format_number(self, value: Any, decimals: int = 1) -> str:
        try:
            return f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):
            return "未知"

    def _format_file_size(self, value: Any) -> str:
        try:
            size = int(value)
        except (TypeError, ValueError):
            return "未知"
        if size >= BYTES_PER_GB:
            return f"{size / BYTES_PER_GB:.1f} GB"
        return f"{size / BYTES_PER_MB:.2f} MB"

    def _set_preview(self, label: QLabel, path: Path) -> None:
        if not path.exists():
            label.setText(path.name)
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            label.setText(path.name)
            return
        label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _save_calibration(self) -> None:
        self.settings = self._settings_payload(calibrated=True)
        write_settings(self.settings)
        self.status_banner.setText("当前校准配置已保存。正式采集将默认使用这组参数。")
        QMessageBox.information(self, "已保存", "当前电脑的校准配置已保存。")

    def _open_last_output(self) -> None:
        if not self.last_output_dir:
            QMessageBox.information(self, "没有本次运行文件夹", "还没有生成本次运行文件夹。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_output_dir).resolve())))

    def closeEvent(self, event: Any) -> None:
        if self.worker_thread is not None:
            reply = QMessageBox.question(
                self,
                "任务正在运行",
                "任务仍在运行。要请求停止吗？停止完成后再关闭窗口。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self._request_stop()
            event.ignore()
            return
        self.settings = self._settings_payload(calibrated=self.settings.get("calibrated"))
        write_settings(self.settings)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
