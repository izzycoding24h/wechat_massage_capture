#!/usr/bin/env python3
"""PySide6 desktop UI for the WeChat evidence capture tool."""

from __future__ import annotations

import dataclasses
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
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
)

from capture_core import (
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
    verify_evidence_dir,
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


class VerifyWorker(QObject):
    finished = Signal(object)
    failed = Signal(str, str)

    def __init__(self, evidence_dir: str) -> None:
        super().__init__()
        self.evidence_dir = evidence_dir

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(verify_evidence_dir(self.evidence_dir))
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
        self.worker: CaptureWorker | VerifyWorker | None = None

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
        for label in ("准备", "校准测试", "正式采集", "复验哈希"):
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(160, 44))
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self._switch_page)
        shell.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(16)

        self.status_banner = QLabel("就绪。先打开微信目标群，然后填写参数。")
        self.status_banner.setObjectName("statusBanner")
        self.status_banner.setWordWrap(True)
        content_layout.addWidget(self.status_banner)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        shell.addWidget(content, 1)

        self.stack.addWidget(self._build_prepare_page())
        self.stack.addWidget(self._build_calibration_page())
        self.stack.addWidget(self._build_capture_page())
        self.stack.addWidget(self._build_verify_page())
        self.setCentralWidget(root)
        self.sidebar.setCurrentRow(0)

    def _build_prepare_page(self) -> QWidget:
        page = self._page()
        title = self._title("准备")
        body = QLabel("打开微信桌面版目标群，确认聊天停在最新消息位置。参数会用于校准和正式采集。")
        body.setObjectName("bodyText")
        body.setWordWrap(True)
        page.layout().addWidget(title)
        page.layout().addWidget(body)

        form_box = self._section("基础参数")
        form = QFormLayout(form_box)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        self.group_name = QLineEdit()
        self.group_name.setPlaceholderText("输入微信群名或窗口标题中的识别文字")
        form.addRow("群名", self.group_name)

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
        self.output_dir.setPlaceholderText("留空时自动生成证据目录")
        browse = QPushButton("选择目录")
        browse.clicked.connect(self._choose_output_dir)
        output_layout.addWidget(self.output_dir, 1)
        output_layout.addWidget(browse)
        form.addRow("保存位置", output_row)

        page.layout().addWidget(form_box)

        note = QLabel("正式采集期间微信会持续占用前台。停止采集请按 Ctrl+Alt+S，界面上的停止按钮只是辅助。")
        note.setObjectName("notice")
        note.setWordWrap(True)
        page.layout().addWidget(note)
        page.layout().addStretch(1)
        return page

    def _build_calibration_page(self) -> QWidget:
        page = self._page()
        page.layout().addWidget(self._title("校准测试"))
        intro = QLabel("先测试当前电脑和微信窗口的滚动幅度。目标是相邻截图保留足够重叠，避免漏内容。")
        intro.setObjectName("bodyText")
        intro.setWordWrap(True)
        page.layout().addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        params = self._section("常用参数")
        form = QFormLayout(params)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        self.target_overlap = QDoubleSpinBox()
        self.target_overlap.setRange(0.05, 0.90)
        self.target_overlap.setSingleStep(0.05)
        self.target_overlap.setDecimals(2)
        self.target_overlap.setValue(0.35)
        form.addRow("重叠比例", self.target_overlap)

        self.adaptive_fixed_steps = QSpinBox()
        self.adaptive_fixed_steps.setRange(0, 100)
        self.adaptive_fixed_steps.setValue(8)
        form.addRow("固定步数", self.adaptive_fixed_steps)

        self.adaptive_step_clicks = QSpinBox()
        self.adaptive_step_clicks.setRange(-1000, 1000)
        self.adaptive_step_clicks.setValue(100)
        form.addRow("每步滚轮力度", self.adaptive_step_clicks)

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.05, 10.0)
        self.interval.setSingleStep(0.05)
        self.interval.setDecimals(2)
        self.interval.setValue(0.2)
        form.addRow("截图间隔秒", self.interval)
        grid.addWidget(params, 0, 0)

        advanced = QGroupBox("高级参数")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_layout = QFormLayout(advanced)
        self.capture_method = QComboBox()
        self.capture_method.addItems(("auto", *CAPTURE_METHODS))
        advanced_layout.addRow("截图方式", self.capture_method)

        self.scroll_mode = QComboBox()
        self.scroll_mode.addItems(SCROLL_MODES)
        self.scroll_mode.setCurrentText("adaptive")
        advanced_layout.addRow("滚动模式", self.scroll_mode)

        self.scroll_x_ratio = QDoubleSpinBox()
        self.scroll_x_ratio.setRange(0.10, 0.95)
        self.scroll_x_ratio.setSingleStep(0.01)
        self.scroll_x_ratio.setDecimals(2)
        self.scroll_x_ratio.setValue(0.68)
        advanced_layout.addRow("滚动 X 比例", self.scroll_x_ratio)

        self.scroll_y_ratio = QDoubleSpinBox()
        self.scroll_y_ratio.setRange(0.10, 0.95)
        self.scroll_y_ratio.setSingleStep(0.01)
        self.scroll_y_ratio.setDecimals(2)
        self.scroll_y_ratio.setValue(0.55)
        advanced_layout.addRow("滚动 Y 比例", self.scroll_y_ratio)

        self.duplicate_threshold = QDoubleSpinBox()
        self.duplicate_threshold.setRange(0.0, 0.1)
        self.duplicate_threshold.setSingleStep(0.001)
        self.duplicate_threshold.setDecimals(3)
        self.duplicate_threshold.setValue(0.003)
        advanced_layout.addRow("重复阈值", self.duplicate_threshold)

        self.stable_limit = QSpinBox()
        self.stable_limit.setRange(0, 100)
        self.stable_limit.setValue(8)
        advanced_layout.addRow("稳定停止次数", self.stable_limit)
        grid.addWidget(advanced, 0, 1)

        page.layout().addLayout(grid)

        actions = QHBoxLayout()
        self.scroll_test_button = QPushButton("运行校准测试")
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

        result_box = self._section("测试结果")
        result_layout = QGridLayout(result_box)
        self.before_preview = self._preview_label("before.png")
        self.after_preview = self._preview_label("after.png")
        self.calibration_summary = QLabel("还没有运行校准测试。")
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
        page.layout().addWidget(self._title("正式采集"))
        warning = QLabel("点击开始后，微信窗口会反复被置前并接收滚动操作。看到起始日期附近时，请按 Ctrl+Alt+S 停止。")
        warning.setObjectName("notice")
        warning.setWordWrap(True)
        page.layout().addWidget(warning)

        actions = QHBoxLayout()
        self.start_capture_button = QPushButton("开始正式采集")
        self.start_capture_button.setObjectName("primaryButton")
        self.start_capture_button.clicked.connect(self._confirm_and_start_capture)
        self.stop_button = QPushButton("辅助停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._request_stop)
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.clicked.connect(self._open_last_output)
        actions.addWidget(self.start_capture_button)
        actions.addWidget(self.stop_button)
        actions.addStretch(1)
        actions.addWidget(self.open_output_button)
        page.layout().addLayout(actions)

        stats = self._section("采集状态")
        stats_layout = QGridLayout(stats)
        self.capture_state = QLabel("未开始")
        self.capture_count = QLabel("0")
        self.capture_output = QLabel("未生成")
        self.capture_output.setTextInteractionFlags(Qt.TextSelectableByMouse)
        stats_layout.addWidget(QLabel("状态"), 0, 0)
        stats_layout.addWidget(self.capture_state, 0, 1)
        stats_layout.addWidget(QLabel("已保存截图"), 1, 0)
        stats_layout.addWidget(self.capture_count, 1, 1)
        stats_layout.addWidget(QLabel("输出目录"), 2, 0)
        stats_layout.addWidget(self.capture_output, 2, 1)
        page.layout().addWidget(stats)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("logView")
        page.layout().addWidget(self.log_view, 1)
        return page

    def _build_verify_page(self) -> QWidget:
        page = self._page()
        page.layout().addWidget(self._title("复验哈希"))
        intro = QLabel("选择包含 sha256sums.txt 的证据输出目录，检查文件是否和采集完成时一致。")
        intro.setObjectName("bodyText")
        intro.setWordWrap(True)
        page.layout().addWidget(intro)

        row = QHBoxLayout()
        self.verify_dir = QLineEdit()
        self.verify_dir.setPlaceholderText("选择证据目录")
        choose = QPushButton("选择目录")
        choose.clicked.connect(self._choose_verify_dir)
        self.verify_button = QPushButton("开始复验")
        self.verify_button.setObjectName("primaryButton")
        self.verify_button.clicked.connect(self._start_verify)
        row.addWidget(self.verify_dir, 1)
        row.addWidget(choose)
        row.addWidget(self.verify_button)
        page.layout().addLayout(row)

        self.verify_result = QTextEdit()
        self.verify_result.setReadOnly(True)
        self.verify_result.setObjectName("logView")
        page.layout().addWidget(self.verify_result, 1)
        return page

    def _page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        return page

    def _title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("pageTitle")
        return label

    def _section(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        return box

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
        self.target_overlap.setValue(float(self.settings.get("target_overlap", 0.35)))
        self.adaptive_fixed_steps.setValue(int(self.settings.get("adaptive_fixed_steps", 8)))
        self.adaptive_step_clicks.setValue(int(self.settings.get("adaptive_step_clicks", 100)))
        self.interval.setValue(float(self.settings.get("interval", 0.2)))
        self.capture_method.setCurrentText(self.settings.get("capture_method", "auto"))
        self.scroll_mode.setCurrentText(self.settings.get("scroll_mode", "adaptive"))
        self.scroll_x_ratio.setValue(float(self.settings.get("scroll_x_ratio", 0.68)))
        self.scroll_y_ratio.setValue(float(self.settings.get("scroll_y_ratio", 0.55)))
        self.duplicate_threshold.setValue(float(self.settings.get("duplicate_threshold", 0.003)))
        self.stable_limit.setValue(int(self.settings.get("stable_limit", 8)))

    def _settings_payload(self, calibrated: bool | None = None) -> dict[str, Any]:
        payload = dict(self.settings)
        payload.update(
            {
                "group_name": self.group_name.text().strip(),
                "start_date": iso_from_qdate(self.start_date.date()),
                "end_date": iso_from_qdate(self.end_date.date()),
                "output_dir": self.output_dir.text().strip(),
                "target_overlap": self.target_overlap.value(),
                "adaptive_fixed_steps": self.adaptive_fixed_steps.value(),
                "adaptive_step_clicks": self.adaptive_step_clicks.value(),
                "interval": self.interval.value(),
                "capture_method": self.capture_method.currentText(),
                "scroll_mode": self.scroll_mode.currentText(),
                "scroll_x_ratio": self.scroll_x_ratio.value(),
                "scroll_y_ratio": self.scroll_y_ratio.value(),
                "duplicate_threshold": self.duplicate_threshold.value(),
                "stable_limit": self.stable_limit.value(),
            }
        )
        if calibrated is not None:
            payload["calibrated"] = calibrated
        return payload

    def _config_from_ui(self) -> CaptureConfig | None:
        group_name = self.group_name.text().strip()
        if not group_name:
            QMessageBox.warning(self, "缺少群名", "请输入微信群名或窗口标题中的识别文字。")
            self.sidebar.setCurrentRow(0)
            return None
        start = iso_from_qdate(self.start_date.date())
        end = iso_from_qdate(self.end_date.date())
        if start > end:
            QMessageBox.warning(self, "日期不正确", "起始日期不能晚于结束日期。")
            return None
        return CaptureConfig(
            group_name=group_name,
            start_date=start,
            end_date=end,
            output_dir=self.output_dir.text().strip(),
            interval=self.interval.value(),
            scroll_mode=self.scroll_mode.currentText(),
            target_overlap=self.target_overlap.value(),
            adaptive_fixed_steps=self.adaptive_fixed_steps.value(),
            adaptive_step_clicks=self.adaptive_step_clicks.value(),
            capture_method=self.capture_method.currentText(),
            scroll_x_ratio=self.scroll_x_ratio.value(),
            scroll_y_ratio=self.scroll_y_ratio.value(),
            duplicate_threshold=self.duplicate_threshold.value(),
            stable_limit=self.stable_limit.value(),
        )

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择截图保存目录", self.output_dir.text() or str(Path.home()))
        if directory:
            self.output_dir.setText(directory)

    def _choose_verify_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择证据目录", self.verify_dir.text() or self.last_output_dir or str(Path.home()))
        if directory:
            self.verify_dir.setText(directory)

    def _set_running(self, running: bool, mode: str = "") -> None:
        for button in (self.scroll_test_button, self.diagnostics_button, self.start_capture_button, self.verify_button):
            button.setEnabled(not running)
        self.stop_button.setEnabled(running and mode == "capture")

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
        config = self._config_from_ui()
        if config is None:
            return
        self.status_banner.setText("正在运行校准测试。请不要操作微信窗口。")
        self.log_view.append("开始校准测试")
        self._start_worker("scroll_test", config)

    def _start_diagnostics(self) -> None:
        config = self._config_from_ui()
        if config is None:
            return
        self.status_banner.setText("正在运行截图诊断。诊断不会滚动聊天。")
        self._start_worker("diagnostics", config)

    def _confirm_and_start_capture(self) -> None:
        config = self._config_from_ui()
        if config is None:
            return
        calibrated = bool(self.settings.get("calibrated"))
        message = "开始后微信会占用前台并自动滚动。看到起始日期附近时，请按 Ctrl+Alt+S 停止。"
        if not calibrated:
            message += "\n\n当前没有保存过校准配置，建议先运行校准测试。仍要继续吗？"
        reply = QMessageBox.question(self, "确认开始采集", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.settings = self._settings_payload(calibrated=calibrated)
        write_settings(self.settings)
        self.capture_count.setText("0")
        self.capture_state.setText("采集中，按 Ctrl+Alt+S 停止")
        self.status_banner.setText("采集中，按 Ctrl+Alt+S 停止。GUI 停止按钮仅作为辅助。")
        self.sidebar.setCurrentRow(2)
        self.log_view.clear()
        self.log_view.append("正式采集开始。主停止方式：Ctrl+Alt+S")
        self._start_worker("capture", config)

    def _request_stop(self) -> None:
        if isinstance(self.worker, CaptureWorker):
            self.worker.stop()
            self.status_banner.setText("已请求停止。等待当前截图或滚动动作结束。")
            self.capture_state.setText("正在停止")

    def _start_verify(self) -> None:
        directory = self.verify_dir.text().strip()
        if not directory:
            QMessageBox.warning(self, "缺少目录", "请选择包含 sha256sums.txt 的证据目录。")
            return
        if self.worker_thread is not None:
            QMessageBox.information(self, "正在运行", "已有任务正在运行，请等待完成。")
            return
        self._set_running(True)
        self.verify_result.clear()
        self.verify_result.append("开始复验")
        self.worker_thread = QThread()
        self.worker = VerifyWorker(directory)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._handle_verify_finished)
        self.worker.failed.connect(self._handle_worker_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _handle_capture_event(self, event: CaptureEvent) -> None:
        data = event.data or {}
        if event.kind == "log":
            self.log_view.append(event.message)
        elif event.kind == "screenshot_saved":
            self.capture_count.setText(str(data.get("saved_index", "")))
            self.capture_state.setText("采集中，按 Ctrl+Alt+S 停止")
        elif event.kind == "window_selected":
            self.log_view.append(event.message)
        elif event.kind == "finished":
            self.capture_state.setText(f"已结束：{data.get('stop_reason', '')}")
        elif event.message:
            self.log_view.append(event.message)

    def _handle_worker_finished(self, result: dict[str, Any]) -> None:
        self.last_output_dir = result.get("output_dir", "")
        self.capture_output.setText(self.last_output_dir or "未生成")
        self.verify_dir.setText(self.last_output_dir)
        stop_reason = result.get("stop_reason", "")
        self.status_banner.setText(f"任务完成：{stop_reason}")
        self.log_view.append(f"任务完成：{stop_reason}")
        if result.get("scroll_test_result"):
            self.last_scroll_result = result["scroll_test_result"]
            self._render_scroll_result(result["scroll_test_result"], self.last_output_dir)
        if result.get("diagnostics_result"):
            QMessageBox.information(self, "诊断完成", f"诊断图片已保存到：\n{self.last_output_dir}")
        self._set_running(False)

    def _handle_verify_finished(self, result: dict[str, Any]) -> None:
        if result.get("ok"):
            self.verify_result.append(f"OK：已复验 {result.get('checked', 0)} 个文件。")
        else:
            self.verify_result.append("FAILED")
            for failure in result.get("failures", []):
                self.verify_result.append(f"  {failure}")
        extras = result.get("extras", [])
        if extras:
            self.verify_result.append(f"WARNING：有 {len(extras)} 个额外文件未列入 sha256sums.txt。")
            for relpath in extras[:20]:
                self.verify_result.append(f"  extra: {relpath}")
        self.status_banner.setText("复验完成。")
        self._set_running(False)

    def _handle_worker_failed(self, message: str, detail: str) -> None:
        self.status_banner.setText("任务失败。请查看日志。")
        if self.stack.currentIndex() == 3:
            self.verify_result.append("ERROR: " + message)
            self.verify_result.append(detail)
        else:
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
        before = result.get("before", {}).get("relative_path", "scroll-test/before.png")
        after = result.get("after", {}).get("relative_path", "scroll-test/after.png")
        self._set_preview(self.before_preview, Path(output_dir) / before)
        self._set_preview(self.after_preview, Path(output_dir) / after)
        movement = float(result.get("estimated_shift_ratio") or 0)
        target = 1.0 - self.target_overlap.value()
        if 0.55 <= movement <= 0.75:
            verdict = "适合正式采集"
        elif movement < 0.55:
            verdict = "移动偏小，可以增加固定步数或滚轮力度"
        else:
            verdict = "移动偏大，建议增加重叠比例或降低固定步数"
        self.calibration_summary.setText(
            f"估算移动比例：{movement:.1%}，目标移动：{target:.1%}。判断：{verdict}。"
        )
        self.sidebar.setCurrentRow(1)

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
            QMessageBox.information(self, "没有输出目录", "还没有生成输出目录。")
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
