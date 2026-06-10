#!/usr/bin/env python3
"""Core capture services for the WeChat evidence desktop and CLI tools."""

from __future__ import annotations

import argparse
import csv
import ctypes
import datetime as dt
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import shutil
import socket
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


SCRIPT_VERSION = "1.5.0"
DEFAULT_END_DATE = dt.date.today().isoformat()
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024
WECHAT_TITLE_HINTS = ("微信", "wechat", "weixin")
CAPTURE_METHODS = ("imagegrab", "pyautogui", "mss-full", "mss-window")
SCROLL_MODES = ("adaptive", "wheel", "pageup", "drag")
CAPTURES_DIR = "截图"
RECORDS_DIR = "运行记录"
DUPLICATES_DIR = "重复截图"
SCROLL_TEST_DIR = "测试校准图片"
DIAGNOSTICS_DIR = "诊断图片"
TMP_DIR = "_tmp"
EventCallback = Callable[["CaptureEvent"], None]
MANIFEST_FIELDS = [
    "attempt",
    "saved_index",
    "saved",
    "captured_at",
    "relative_path",
    "sha256",
    "capture_method",
    "window_title",
    "window_left",
    "window_top",
    "window_width",
    "window_height",
    "diff_from_previous",
    "duplicate_of",
    "blank_warning",
    "mean_luma",
    "stddev_luma",
    "scroll_mode_after",
    "scroll_clicks_after",
    "scroll_bursts_after",
    "notes",
]


@dataclass
class CaptureRow:
    attempt: int
    saved_index: int | str
    saved: bool
    captured_at: str
    relative_path: str
    sha256: str
    capture_method: str
    window_title: str
    window_left: int
    window_top: int
    window_width: int
    window_height: int
    diff_from_previous: str
    duplicate_of: str
    blank_warning: bool
    mean_luma: str
    stddev_luma: str
    scroll_mode_after: str
    scroll_clicks_after: int
    scroll_bursts_after: int
    notes: str


@dataclass
class CaptureEvent:
    kind: str
    message: str = ""
    data: dict[str, Any] | None = None


@dataclass
class CaptureConfig:
    group_name: str
    start_date: str
    end_date: str = DEFAULT_END_DATE
    output_dir: str = ""
    max_screenshots: int = 0
    min_free_space_gb: float = 10.0
    interval: float = 0.2
    scroll_clicks: int = 30
    scroll_mode: str = "adaptive"
    scroll_bursts: int = 3
    pageup_presses: int = 1
    drag_pixels: int = 360
    target_overlap: float = 0.35
    adaptive_step_clicks: int = 100
    adaptive_max_steps: int = 12
    adaptive_fixed_steps: int = 8
    adaptive_lock_after_first: bool = False
    adaptive_settle: float = 0.25
    match_x_start: float = 0.30
    match_x_end: float = 0.97
    match_y_start: float = 0.12
    match_y_end: float = 0.82
    scroll_x_ratio: float = 0.68
    scroll_y_ratio: float = 0.55
    duplicate_threshold: float = 0.003
    stable_limit: int = 8
    capture_method: str = "auto"
    no_click_before_scroll: bool = False
    hotkey: str = "ctrl+alt+s"
    preflight_seconds: int = 6
    no_maximize: bool = False
    allow_non_windows: bool = False


@dataclass
class CaptureRunResult:
    output_dir: str
    stop_reason: str
    saved_screenshots: int
    attempts: int
    manifest_path: str
    run_json_path: str
    sha256sums_path: str
    scroll_test_result: dict[str, Any] | None = None
    diagnostics_result: dict[str, Any] | None = None


class CaptureAbort(RuntimeError):
    """Raised for expected operator or environment aborts."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture visible screenshots from an already-open WeChat chat "
            "window on Windows, scrolling upward through chat history."
        )
    )
    parser.add_argument("--group-name", required=True, help="Target WeChat chat window title or identifying title text.")
    parser.add_argument("--start-date", required=True, help="Oldest date to capture, YYYY-MM-DD. Operator stops there.")
    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        help=f"Newest date covered by the run, YYYY-MM-DD. Defaults to {DEFAULT_END_DATE}.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Evidence output directory. Defaults to ./wechat_evidence_<group>_<timestamp>.",
    )
    parser.add_argument(
        "--max-screenshots",
        type=int,
        default=0,
        help="Maximum main screenshots to keep. Use 0 for unlimited until hotkey/Ctrl+C/stable limit.",
    )
    parser.add_argument(
        "--min-free-space-gb",
        type=float,
        default=10.0,
        help="Stop formal capture when output disk free space drops below this reserve in GB. Use 0 to disable.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.2,
        help="Seconds to wait after each scroll before the next screenshot.",
    )
    parser.add_argument(
        "--scroll-clicks",
        type=int,
        default=30,
        help="Mouse wheel clicks after each screenshot. Positive values scroll upward to older messages.",
    )
    parser.add_argument(
        "--scroll-mode",
        choices=SCROLL_MODES,
        default="adaptive",
        help="How to move to older messages after each screenshot.",
    )
    parser.add_argument(
        "--scroll-bursts",
        type=int,
        default=3,
        help="Number of repeated scroll actions per screenshot. Useful when WeChat only moves slightly.",
    )
    parser.add_argument(
        "--pageup-presses",
        type=int,
        default=1,
        help="Number of PageUp key presses per screenshot when --scroll-mode pageup is used.",
    )
    parser.add_argument(
        "--drag-pixels",
        type=int,
        default=360,
        help="Scrollbar drag distance when --scroll-mode drag is used. Positive means drag upward to older messages.",
    )
    parser.add_argument(
        "--target-overlap",
        type=float,
        default=0.35,
        help="Adaptive mode target overlap between neighboring screenshots. 0.35 means about 35%% overlap.",
    )
    parser.add_argument(
        "--adaptive-step-clicks",
        type=int,
        default=15,
        help="Wheel clicks per adaptive probe step.",
    )
    parser.add_argument(
        "--adaptive-max-steps",
        type=int,
        default=12,
        help="Maximum adaptive probe steps after each screenshot.",
    )
    parser.add_argument(
        "--adaptive-fixed-steps",
        type=int,
        default=0,
        help="In adaptive mode, skip per-screenshot measuring and directly apply this many calibrated wheel steps.",
    )
    parser.add_argument(
        "--adaptive-lock-after-first",
        action="store_true",
        help="Measure adaptive steps once on the first real screenshot, then reuse that step count for the rest of the run.",
    )
    parser.add_argument(
        "--adaptive-settle",
        type=float,
        default=0.25,
        help="Seconds to wait after each adaptive probe step before measuring movement.",
    )
    parser.add_argument(
        "--match-x-start",
        type=float,
        default=0.30,
        help="Left crop ratio for adaptive movement matching.",
    )
    parser.add_argument(
        "--match-x-end",
        type=float,
        default=0.97,
        help="Right crop ratio for adaptive movement matching.",
    )
    parser.add_argument(
        "--match-y-start",
        type=float,
        default=0.12,
        help="Top crop ratio for adaptive movement matching.",
    )
    parser.add_argument(
        "--match-y-end",
        type=float,
        default=0.82,
        help="Bottom crop ratio for adaptive movement matching.",
    )
    parser.add_argument(
        "--scroll-x-ratio",
        type=float,
        default=0.68,
        help="Window-width ratio used as the mouse X position for scrolling.",
    )
    parser.add_argument(
        "--scroll-y-ratio",
        type=float,
        default=0.55,
        help="Window-height ratio used as the mouse Y position for scrolling.",
    )
    parser.add_argument(
        "--duplicate-threshold",
        type=float,
        default=0.003,
        help="Normalized thumbnail difference at or below this value is treated as duplicate.",
    )
    parser.add_argument(
        "--stable-limit",
        type=int,
        default=8,
        help="Stop after this many consecutive duplicate/stable attempts. Use 0 to disable.",
    )
    parser.add_argument(
        "--capture-method",
        choices=("auto", *CAPTURE_METHODS),
        default="auto",
        help=(
            "Screenshot backend. auto tries imagegrab, pyautogui, mss-full, then mss-window "
            "and keeps the first non-black result."
        ),
    )
    parser.add_argument(
        "--diagnose-capture",
        action="store_true",
        help="Capture one diagnostic image with every backend, write diagnostics, and exit without scrolling.",
    )
    parser.add_argument(
        "--scroll-test",
        action="store_true",
        help="Capture before/after images around one scroll action, write scroll-test diagnostics, and exit.",
    )
    parser.add_argument(
        "--no-click-before-scroll",
        action="store_true",
        help="Do not click the configured chat-area point before each wheel scroll.",
    )
    parser.add_argument(
        "--hotkey",
        default="ctrl+alt+s",
        help="Global stop hotkey. Requires the keyboard package on Windows.",
    )
    parser.add_argument(
        "--preflight-seconds",
        type=int,
        default=6,
        help="Countdown after activating the selected WeChat window before capture starts.",
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip the typed CAPTURE confirmation prompt.",
    )
    parser.add_argument(
        "--no-maximize",
        action="store_true",
        help="Do not maximize the selected WeChat window before capture.",
    )
    parser.add_argument(
        "--allow-non-windows",
        action="store_true",
        help="Allow startup outside Windows for development checks only.",
    )
    return parser.parse_args()


def validate_date(value: str, field_name: str) -> dt.date:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CaptureAbort(f"{field_name} must be YYYY-MM-DD, got {value!r}.") from exc


def subtract_months(value: dt.date, months: int) -> dt.date:
    month_index = value.month - 1 - months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        next_month = dt.date(year + 1, 1, 1)
    else:
        next_month = dt.date(year, month + 1, 1)
    last_day = (next_month - dt.timedelta(days=1)).day
    return dt.date(year, month, min(value.day, last_day))


def default_start_date(today: dt.date | None = None) -> str:
    return subtract_months(today or dt.date.today(), 3).isoformat()


def default_end_date(today: dt.date | None = None) -> str:
    return (today or dt.date.today()).isoformat()


def emit_event(callback: EventCallback | None, kind: str, message: str = "", **data: Any) -> None:
    if callback is None:
        return
    callback(CaptureEvent(kind=kind, message=message, data=data or None))


class CallbackLogHandler(logging.Handler):
    def __init__(self, callback: EventCallback | None) -> None:
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        if self.callback is None:
            return
        emit_event(
            self.callback,
            "log",
            self.format(record),
            level=record.levelname,
            logger=record.name,
        )


def config_to_args(
    config: CaptureConfig,
    *,
    diagnose_capture: bool = False,
    scroll_test: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        group_name=config.group_name,
        start_date=config.start_date,
        end_date=config.end_date,
        output_dir=config.output_dir,
        max_screenshots=config.max_screenshots,
        min_free_space_gb=config.min_free_space_gb,
        interval=config.interval,
        scroll_clicks=config.scroll_clicks,
        scroll_mode=config.scroll_mode,
        scroll_bursts=config.scroll_bursts,
        pageup_presses=config.pageup_presses,
        drag_pixels=config.drag_pixels,
        target_overlap=config.target_overlap,
        adaptive_step_clicks=config.adaptive_step_clicks,
        adaptive_max_steps=config.adaptive_max_steps,
        adaptive_fixed_steps=config.adaptive_fixed_steps,
        adaptive_lock_after_first=config.adaptive_lock_after_first,
        adaptive_settle=config.adaptive_settle,
        match_x_start=config.match_x_start,
        match_x_end=config.match_x_end,
        match_y_start=config.match_y_start,
        match_y_end=config.match_y_end,
        scroll_x_ratio=config.scroll_x_ratio,
        scroll_y_ratio=config.scroll_y_ratio,
        duplicate_threshold=config.duplicate_threshold,
        stable_limit=config.stable_limit,
        capture_method=config.capture_method,
        diagnose_capture=diagnose_capture,
        scroll_test=scroll_test,
        no_click_before_scroll=config.no_click_before_scroll,
        hotkey=config.hotkey,
        preflight_seconds=config.preflight_seconds,
        no_confirm=True,
        no_maximize=config.no_maximize,
        allow_non_windows=config.allow_non_windows,
    )


def safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    value = re.sub(r"\s+", "_", value)
    return value[:80] or "wechat_group"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def make_output_dir(group_name: str, requested: str) -> Path:
    if requested:
        output_dir = Path(requested).expanduser().resolve()
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path.cwd() / f"wechat_evidence_{safe_filename(group_name)}_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / RECORDS_DIR / TMP_DIR).mkdir(parents=True, exist_ok=True)
    return output_dir


def _existing_disk_probe(path: Path) -> Path:
    probe = path.expanduser()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists():
        return probe
    return Path.cwd()


def disk_space_snapshot(path: str | Path) -> dict[str, Any]:
    probe = _existing_disk_probe(Path(path))
    usage = shutil.disk_usage(probe)
    return {
        "checked_path": str(probe.resolve()),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "total_gb": round(usage.total / BYTES_PER_GB, 3),
        "used_gb": round(usage.used / BYTES_PER_GB, 3),
        "free_gb": round(usage.free / BYTES_PER_GB, 3),
    }


def estimate_remaining_screenshots(
    free_bytes: int,
    min_free_space_gb: float,
    reference_screenshot_size_bytes: int,
) -> int | None:
    if reference_screenshot_size_bytes <= 0:
        return None
    reserve_bytes = max(0, int(float(min_free_space_gb) * BYTES_PER_GB))
    usable_bytes = max(0, int(free_bytes) - reserve_bytes)
    return usable_bytes // reference_screenshot_size_bytes


def disk_space_below_limit(snapshot: dict[str, Any], min_free_space_gb: float) -> bool:
    if min_free_space_gb <= 0:
        return False
    return int(snapshot.get("free_bytes", 0)) < int(min_free_space_gb * BYTES_PER_GB)


def emit_low_disk_space_event(
    callback: EventCallback | None,
    snapshot: dict[str, Any],
    min_free_space_gb: float,
) -> None:
    emit_event(
        callback,
        "low_disk_space",
        "Disk free space is below the configured reserve.",
        free_bytes=snapshot.get("free_bytes", 0),
        free_gb=snapshot.get("free_gb", 0),
        min_free_space_gb=min_free_space_gb,
        checked_path=snapshot.get("checked_path", ""),
    )


def records_dir(output_dir: Path) -> Path:
    path = output_dir / RECORDS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_dir(output_dir: Path) -> Path:
    path = records_dir(output_dir) / TMP_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_logging(output_dir: Path) -> logging.Logger:
    logger = logging.getLogger("wechat_capture")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    log_path = records_dir(output_dir) / "capture.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def close_logging(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def set_windows_dpi_awareness(logger: logging.Logger) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        logger.info("Set process DPI awareness via shcore.")
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            logger.info("Set process DPI awareness via user32.")
        except Exception as exc:
            logger.warning("Could not set process DPI awareness: %s", exc)


def load_capture_dependencies() -> tuple[Any, Any, Any, Any, Any, Any]:
    missing: list[str] = []
    try:
        import pyautogui
    except Exception:
        pyautogui = None
        missing.append("pyautogui")
    try:
        import pygetwindow
    except Exception:
        pygetwindow = None
        missing.append("pygetwindow")
    try:
        import mss
    except Exception:
        mss = None
        missing.append("mss")
    try:
        from PIL import Image, ImageGrab, ImageStat
    except Exception:
        Image = None
        ImageGrab = None
        ImageStat = None
        missing.append("Pillow")

    if missing:
        names = ", ".join(missing)
        raise CaptureAbort(f"Missing dependencies: {names}. Run SETUP-WINDOWS.bat or pip install -r requirements.txt.")
    return pyautogui, pygetwindow, mss, Image, ImageStat, ImageGrab


def dependency_versions(packages: Iterable[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def choose_largest_window(windows: list[Any]) -> Any:
    return max(windows, key=lambda w: max(0, int(w.width)) * max(0, int(w.height)))


def find_capture_window(gw: Any, group_name: str, logger: logging.Logger) -> Any:
    all_windows = [
        w
        for w in gw.getAllWindows()
        if getattr(w, "title", "").strip() and int(getattr(w, "width", 0)) > 250 and int(getattr(w, "height", 0)) > 250
    ]
    group_lower = group_name.lower()
    group_matches = [w for w in all_windows if group_lower in w.title.lower()]
    if group_matches:
        window = choose_largest_window(group_matches)
        logger.info("Selected window by group-name match: %r", window.title)
        return window

    active_window = None
    try:
        active_window = gw.getActiveWindow()
    except Exception:
        active_window = None

    wechat_matches = [
        w
        for w in all_windows
        if any(hint in w.title.lower() for hint in WECHAT_TITLE_HINTS)
    ]
    if active_window and active_window.title:
        active_title = active_window.title.lower()
        if group_lower in active_title or any(hint in active_title for hint in WECHAT_TITLE_HINTS):
            logger.info("Selected active WeChat-like window: %r", active_window.title)
            return active_window

    if wechat_matches:
        window = choose_largest_window(wechat_matches)
        logger.warning(
            "Group name was not found in window titles. Falling back to largest WeChat-like window: %r",
            window.title,
        )
        return window

    if active_window and active_window.title:
        logger.warning(
            "No WeChat-like window title found. Falling back to active window: %r. Confirm carefully.",
            active_window.title,
        )
        return active_window

    raise CaptureAbort("No suitable window found. Open the target WeChat group window before running the script.")


def activate_window(window: Any, maximize: bool, logger: logging.Logger) -> None:
    try:
        if getattr(window, "isMinimized", False):
            window.restore()
            time.sleep(0.5)
    except Exception as exc:
        logger.warning("Could not restore selected window: %s", exc)

    try:
        window.activate()
        time.sleep(0.6)
    except Exception as exc:
        logger.warning("Could not activate selected window through pygetwindow: %s", exc)

    if maximize:
        try:
            window.maximize()
            time.sleep(0.8)
        except Exception as exc:
            logger.warning("Could not maximize selected window: %s", exc)


def window_region(window: Any) -> dict[str, int]:
    left = int(window.left)
    top = int(window.top)
    width = int(window.width)
    height = int(window.height)
    if width <= 0 or height <= 0:
        raise CaptureAbort(f"Selected window has invalid size: {width}x{height}.")
    return {"left": left, "top": top, "width": width, "height": height}


def capture_mss_window(mss_module: Any, Image: Any, region: dict[str, int], destination: Path) -> None:
    monitor = {
        "left": region["left"],
        "top": region["top"],
        "width": region["width"],
        "height": region["height"],
    }
    with mss_module.mss() as sct:
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        image.save(destination, format="PNG", optimize=False)


def capture_mss_full(mss_module: Any, Image: Any, region: dict[str, int], destination: Path) -> None:
    with mss_module.mss() as sct:
        virtual = sct.monitors[0]
        shot = sct.grab(virtual)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        left = region["left"] - int(virtual["left"])
        top = region["top"] - int(virtual["top"])
        right = left + region["width"]
        bottom = top + region["height"]
        if left < 0 or top < 0 or right > image.width or bottom > image.height:
            raise ValueError(
                "window region is outside the virtual desktop: "
                f"crop=({left},{top},{right},{bottom}), desktop={image.width}x{image.height}"
            )
        image.crop((left, top, right, bottom)).save(destination, format="PNG", optimize=False)


def capture_imagegrab(ImageGrab: Any, region: dict[str, int], destination: Path) -> None:
    bbox = (
        region["left"],
        region["top"],
        region["left"] + region["width"],
        region["top"] + region["height"],
    )
    try:
        image = ImageGrab.grab(bbox=bbox, all_screens=True)
    except TypeError:
        image = ImageGrab.grab(bbox=bbox)
    image.convert("RGB").save(destination, format="PNG", optimize=False)


def capture_pyautogui(pyautogui: Any, region: dict[str, int], destination: Path) -> None:
    image = pyautogui.screenshot(
        region=(region["left"], region["top"], region["width"], region["height"])
    )
    image.convert("RGB").save(destination, format="PNG", optimize=False)


def capture_using_method(
    method: str,
    pyautogui: Any,
    mss_module: Any,
    Image: Any,
    ImageGrab: Any,
    region: dict[str, int],
    destination: Path,
) -> None:
    if method == "imagegrab":
        capture_imagegrab(ImageGrab, region, destination)
    elif method == "pyautogui":
        capture_pyautogui(pyautogui, region, destination)
    elif method == "mss-full":
        capture_mss_full(mss_module, Image, region, destination)
    elif method == "mss-window":
        capture_mss_window(mss_module, Image, region, destination)
    else:
        raise ValueError(f"unknown capture method: {method}")


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_signature(Image: Any, path: Path) -> bytes:
    resample = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
    with Image.open(path) as image:
        return image.convert("L").resize((64, 64), resample).tobytes()


def signature_difference(previous: bytes | None, current: bytes) -> float | None:
    if previous is None:
        return None
    total = sum(abs(a - b) for a, b in zip(previous, current))
    return total / (len(current) * 255.0)


def image_luma_stats(Image: Any, ImageStat: Any, path: Path) -> tuple[float, float, bool]:
    resample = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
    with Image.open(path) as image:
        gray = image.convert("L").resize((64, 64), resample)
        stat = ImageStat.Stat(gray)
    mean = float(stat.mean[0])
    stddev = float(stat.stddev[0])
    likely_blank = mean < 8.0 and stddev < 3.0
    return mean, stddev, likely_blank


def capture_method_sequence(requested: str) -> tuple[str, ...]:
    if requested == "auto":
        return CAPTURE_METHODS
    return (requested,)


def capture_window_with_fallback(
    pyautogui: Any,
    mss_module: Any,
    Image: Any,
    ImageStat: Any,
    ImageGrab: Any,
    region: dict[str, int],
    tmp_dir: Path,
    attempt: int,
    requested_method: str,
    logger: logging.Logger,
) -> tuple[Path, str, float, float, bool]:
    method_results: list[tuple[Path, str, float, float, bool]] = []
    errors: list[str] = []

    for method in capture_method_sequence(requested_method):
        candidate = tmp_dir / f"attempt_{attempt:06d}_{method}.png"
        try:
            capture_using_method(method, pyautogui, mss_module, Image, ImageGrab, region, candidate)
            mean_luma, stddev_luma, blank_warning = image_luma_stats(Image, ImageStat, candidate)
            method_results.append((candidate, method, mean_luma, stddev_luma, blank_warning))
            logger.info(
                "Capture method %s attempt %s stats: mean_luma=%.2f stddev_luma=%.2f blank=%s",
                method,
                attempt,
                mean_luma,
                stddev_luma,
                blank_warning,
            )
            if not blank_warning:
                for old_path, _, _, _, _ in method_results[:-1]:
                    old_path.unlink(missing_ok=True)
                return candidate, method, mean_luma, stddev_luma, blank_warning
        except Exception as exc:
            errors.append(f"{method}: {type(exc).__name__}: {exc}")
            logger.warning("Capture method %s failed on attempt %s: %s", method, attempt, exc)

    if method_results:
        # If every backend produced a black-looking image, keep the one with the
        # most texture. This makes the failed evidence auditable while still
        # letting the run metadata explain the failure.
        chosen = max(method_results, key=lambda item: (item[3], item[2]))
        for old_path, _, _, _, _ in method_results:
            if old_path != chosen[0]:
                old_path.unlink(missing_ok=True)
        logger.error(
            "All capture methods looked blank on attempt %s. Chose %s for audit. "
            "Try disabling WeChat hardware acceleration or run diagnostics.",
            attempt,
            chosen[1],
        )
        return chosen

    raise CaptureAbort("All capture methods failed: " + "; ".join(errors))


def _run_capture_diagnostics(
    pyautogui: Any,
    mss_module: Any,
    Image: Any,
    ImageStat: Any,
    ImageGrab: Any,
    window: Any,
    output_dir: Path,
    logger: logging.Logger,
) -> dict[str, Any]:
    diagnostics_dir = output_dir / DIAGNOSTICS_DIR
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    region = window_region(window)
    results: list[dict[str, Any]] = []

    print("")
    print("Running one-shot capture diagnostics. No scrolling will happen.")
    for method in CAPTURE_METHODS:
        destination = diagnostics_dir / f"诊断图片_{diagnostics_stamp}_{method}.png"
        record: dict[str, Any] = {
            "method": method,
            "relative_path": relative_to_output(destination, output_dir),
            "ok": False,
            "blank_warning": None,
            "mean_luma": None,
            "stddev_luma": None,
            "sha256": None,
            "error": "",
        }
        try:
            capture_using_method(method, pyautogui, mss_module, Image, ImageGrab, region, destination)
            mean_luma, stddev_luma, blank_warning = image_luma_stats(Image, ImageStat, destination)
            record.update(
                {
                    "ok": True,
                    "blank_warning": blank_warning,
                    "mean_luma": round(mean_luma, 2),
                    "stddev_luma": round(stddev_luma, 2),
                    "sha256": hash_file(destination),
                }
            )
            status = "BLACK" if blank_warning else "OK"
            print(f"  {method}: {status} mean={mean_luma:.2f} stddev={stddev_luma:.2f}")
            logger.info("Diagnostic %s: %s", method, record)
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            print(f"  {method}: ERROR {record['error']}")
            logger.warning("Diagnostic method %s failed: %s", method, exc)
        results.append(record)

    payload = {
        "created_at": now_iso(),
        "diagnostics_dir": relative_to_output(diagnostics_dir, output_dir),
        "image_prefix": f"诊断图片_{diagnostics_stamp}",
        "window_title": window.title,
        "region": region,
        "methods": results,
        "next_steps": [
            "If one method is OK, rerun capture with --capture-method METHOD.",
            "If all methods are BLACK, make sure WeChat is visible on the primary display and disable WeChat hardware acceleration.",
            "Avoid running inside a hidden remote desktop session; keep the Windows desktop unlocked and visible.",
        ],
    }
    write_json(records_dir(output_dir) / "diagnostics.json", payload)
    return payload


def relative_to_output(path: Path, output_dir: Path) -> str:
    return path.relative_to(output_dir).as_posix()


def write_manifest(path: Path, rows: list[CaptureRow]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_sha256sums(output_dir: Path) -> Path:
    sums_path = records_dir(output_dir) / "sha256sums.txt"
    candidates = sorted(
        p
        for p in output_dir.rglob("*")
        if p.is_file() and p != sums_path and TMP_DIR not in p.relative_to(output_dir).parts
    )
    with sums_path.open("w", encoding="utf-8") as handle:
        for path in candidates:
            handle.write(f"{hash_file(path)}  {relative_to_output(path, output_dir)}\n")
    return sums_path


def verify_evidence_dir(path: str | Path) -> dict[str, Any]:
    evidence_dir = Path(path).expanduser().resolve()
    sums_path = evidence_dir / "sha256sums.txt"
    if not sums_path.exists():
        sums_path = evidence_dir / RECORDS_DIR / "sha256sums.txt"
    if not sums_path.exists():
        return {
            "ok": False,
            "checked": 0,
            "failures": [f"Missing {sums_path}"],
            "extras": [],
            "evidence_dir": str(evidence_dir),
        }

    checked = 0
    failures: list[str] = []
    listed_paths: set[Path] = set()
    for line_number, raw_line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "  " not in line:
            failures.append(f"line {line_number}: malformed entry")
            continue
        expected, relpath = line.split("  ", 1)
        target = evidence_dir / relpath
        listed_paths.add(target.resolve())
        if not target.exists():
            failures.append(f"{relpath}: missing")
            continue
        actual = hash_file(target)
        checked += 1
        if actual.lower() != expected.lower():
            failures.append(f"{relpath}: hash mismatch expected={expected} actual={actual}")

    current_files = {
        p.resolve()
        for p in evidence_dir.rglob("*")
        if p.is_file() and p != sums_path and TMP_DIR not in p.relative_to(evidence_dir).parts
    }
    extras = sorted(path.relative_to(evidence_dir).as_posix() for path in current_files - listed_paths)
    return {
        "ok": not failures,
        "checked": checked,
        "failures": failures,
        "extras": extras,
        "evidence_dir": str(evidence_dir),
    }


def install_stop_hotkey(
    hotkey: str,
    stop_event: threading.Event,
    logger: logging.Logger,
    callback: EventCallback | None = None,
) -> Any | None:
    def request_stop_from_hotkey() -> None:
        stop_event.set()
        emit_event(
            callback,
            "stop_requested",
            f"Stop requested by hotkey: {hotkey}",
            source="hotkey",
            hotkey=hotkey,
        )

    try:
        import keyboard
    except Exception as exc:
        logger.warning("Global hotkey disabled because the keyboard package is unavailable: %s", exc)
        return None
    try:
        keyboard.add_hotkey(hotkey, request_stop_from_hotkey)
        logger.info("Installed global stop hotkey: %s", hotkey)
        return keyboard
    except Exception as exc:
        logger.warning("Could not install global hotkey %r: %s", hotkey, exc)
        return None


def print_preflight(window: Any, args: argparse.Namespace, output_dir: Path) -> None:
    print("")
    print("Selected capture window:")
    print(f"  title : {window.title}")
    print(f"  bounds: left={window.left}, top={window.top}, width={window.width}, height={window.height}")
    print("")
    print("Before continuing:")
    print("  1. Confirm the selected window is the target WeChat group chat.")
    print(f"  2. Put the chat at the newest/end position to capture, normally {args.end_date}.")
    print(f"  3. Press {args.hotkey} when visible messages reach the start date {args.start_date}.")
    print("  4. Keep the original WeChat account/device and do not delete the source records.")
    print(f"  5. Capture method: {args.capture_method}.")
    if args.diagnose_capture:
        print("  6. Diagnostic mode is enabled: one image per backend, no scrolling.")
    if args.scroll_test:
        print("  6. Scroll-test mode is enabled: before/after one scroll action, then exit.")
    print("")
    print(f"Output directory: {output_dir}")
    print("")


def require_operator_confirmation(args: argparse.Namespace) -> None:
    if args.no_confirm:
        return
    typed = input("Type CAPTURE to start, or anything else to abort: ").strip()
    if typed != "CAPTURE":
        raise CaptureAbort("Operator did not confirm capture start.")


def countdown(seconds: int, logger: logging.Logger) -> None:
    for remaining in range(max(0, seconds), 0, -1):
        print(f"Capture starts in {remaining} seconds...", end="\r", flush=True)
        time.sleep(1)
    print("Capture starting now.                               ")
    logger.info("Preflight countdown finished.")


def chat_point(region: dict[str, int], args: argparse.Namespace) -> tuple[int, int]:
    x = region["left"] + int(region["width"] * args.scroll_x_ratio)
    y = region["top"] + int(region["height"] * args.scroll_y_ratio)
    return x, y


def scroll_older(
    pyautogui: Any,
    region: dict[str, int],
    args: argparse.Namespace,
    *,
    mode: str | None = None,
    scroll_clicks: int | None = None,
    bursts: int | None = None,
) -> None:
    mode = mode or args.scroll_mode
    if mode == "adaptive":
        mode = "wheel"
    clicks = args.scroll_clicks if scroll_clicks is None else scroll_clicks
    burst_count = max(1, args.scroll_bursts if bursts is None else bursts)
    x, y = chat_point(region, args)
    pyautogui.moveTo(x, y, duration=0.05)
    if not args.no_click_before_scroll:
        pyautogui.click(x, y)
        time.sleep(0.1)
    if mode == "wheel":
        for _ in range(burst_count):
            pyautogui.scroll(clicks)
            time.sleep(0.08)
    elif mode == "pageup":
        presses = max(1, args.pageup_presses) * burst_count
        pyautogui.press("pageup", presses=presses, interval=0.08)
    elif mode == "drag":
        drag_x = region["left"] + int(region["width"] * 0.965)
        drag_y = region["top"] + int(region["height"] * args.scroll_y_ratio)
        for _ in range(burst_count):
            pyautogui.moveTo(drag_x, drag_y, duration=0.05)
            pyautogui.dragRel(0, -abs(args.drag_pixels), duration=0.25, button="left")
            time.sleep(0.1)
    else:
        raise CaptureAbort(f"Unsupported scroll mode: {mode}")


def movement_signature(Image: Any, path: Path, args: argparse.Namespace) -> tuple[bytes, int, int]:
    resample = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
    with Image.open(path) as image:
        width, height = image.size
        left = int(width * args.match_x_start)
        right = int(width * args.match_x_end)
        top = int(height * args.match_y_start)
        bottom = int(height * args.match_y_end)
        if right - left < 64 or bottom - top < 64:
            left, top, right, bottom = 0, 0, width, height
        crop = image.crop((left, top, right, bottom)).convert("L").resize((64, 240), resample)
    return crop.tobytes(), 64, 240


def shifted_difference(
    before_data: bytes,
    after_data: bytes,
    width: int,
    height: int,
    shift: int,
) -> float:
    if shift >= 0:
        before_row = 0
        after_row = shift
        rows = height - shift
    else:
        before_row = -shift
        after_row = 0
        rows = height + shift
    if rows <= 0:
        return float("inf")

    total = 0
    count = 0
    row_step = 2
    col_step = 2
    for row in range(0, rows, row_step):
        before_offset = (before_row + row) * width
        after_offset = (after_row + row) * width
        for col in range(0, width, col_step):
            total += abs(before_data[before_offset + col] - after_data[after_offset + col])
            count += 1
    return total / (count * 255.0) if count else float("inf")


def estimate_vertical_movement(Image: Any, before_path: Path, after_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    before_data, width, height = movement_signature(Image, before_path, args)
    after_data, _, _ = movement_signature(Image, after_path, args)
    max_shift = int(height * 0.90)
    min_overlap_rows = int(height * 0.25)
    step = max(1, int(height * 0.01))
    candidates = list(range(-max_shift, max_shift + 1, step))
    if 0 not in candidates:
        candidates.append(0)

    best_shift = 0
    best_score = float("inf")
    for shift in candidates:
        if height - abs(shift) < min_overlap_rows:
            continue
        score = shifted_difference(before_data, after_data, width, height, shift)
        if score < best_score:
            best_score = score
            best_shift = shift

    return {
        "shift_pixels": best_shift,
        "shift_ratio": abs(best_shift) / height,
        "signed_shift_ratio": best_shift / height,
        "score": best_score,
    }


def advance_to_older(
    pyautogui: Any,
    mss_module: Any,
    Image: Any,
    ImageStat: Any,
    ImageGrab: Any,
    region: dict[str, int],
    args: argparse.Namespace,
    output_dir: Path,
    before_image_path: Path,
    attempt: int,
    logger: logging.Logger,
    fixed_steps: int | None = None,
) -> dict[str, Any]:
    if args.scroll_mode != "adaptive":
        scroll_older(pyautogui, region, args)
        return {
            "mode": args.scroll_mode,
            "steps": 1,
            "shift_ratio": None,
            "score": None,
            "target_reached": None,
        }

    fixed_steps = fixed_steps or (args.adaptive_fixed_steps if args.adaptive_fixed_steps > 0 else None)
    if fixed_steps is not None:
        for _ in range(fixed_steps):
            scroll_older(
                pyautogui,
                region,
                args,
                mode="wheel",
                scroll_clicks=args.adaptive_step_clicks,
                bursts=1,
            )
        return {
            "mode": "adaptive-fixed",
            "steps": fixed_steps,
            "shift_ratio": None,
            "score": None,
            "target_reached": None,
        }

    target_shift_ratio = max(0.05, min(0.95, 1.0 - args.target_overlap))
    last_estimate: dict[str, Any] | None = None
    final_path: Path | None = None
    for step_index in range(1, args.adaptive_max_steps + 1):
        scroll_older(
            pyautogui,
            region,
            args,
            mode="wheel",
            scroll_clicks=args.adaptive_step_clicks,
            bursts=1,
        )
        time.sleep(max(0.0, args.adaptive_settle))
        probe_path, probe_method, _, _, probe_blank = capture_window_with_fallback(
            pyautogui,
            mss_module,
            Image,
            ImageStat,
            ImageGrab,
            region,
            tmp_dir(output_dir),
            attempt * 1000 + step_index,
            args.capture_method,
            logger,
        )
        final_path = probe_path
        last_estimate = estimate_vertical_movement(Image, before_image_path, probe_path, args)
        logger.info(
            "Adaptive scroll attempt=%s step=%s method=%s blank=%s shift_ratio=%.3f signed=%.3f score=%.4f target=%.3f",
            attempt,
            step_index,
            probe_method,
            probe_blank,
            last_estimate["shift_ratio"],
            last_estimate["signed_shift_ratio"],
            last_estimate["score"],
            target_shift_ratio,
        )
        if last_estimate["shift_ratio"] >= target_shift_ratio:
            return {
                "mode": "adaptive",
                "steps": step_index,
                "shift_ratio": last_estimate["shift_ratio"],
                "signed_shift_ratio": last_estimate["signed_shift_ratio"],
                "score": last_estimate["score"],
                "target_reached": True,
            }

    return {
        "mode": "adaptive",
        "steps": args.adaptive_max_steps,
        "shift_ratio": None if last_estimate is None else last_estimate["shift_ratio"],
        "signed_shift_ratio": None if last_estimate is None else last_estimate["signed_shift_ratio"],
        "score": None if last_estimate is None else last_estimate["score"],
        "target_reached": False,
        "final_probe": None if final_path is None else relative_to_output(final_path, output_dir),
    }


def _run_scroll_test_impl(
    pyautogui: Any,
    mss_module: Any,
    Image: Any,
    ImageStat: Any,
    ImageGrab: Any,
    window: Any,
    output_dir: Path,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> dict[str, Any]:
    test_dir = output_dir / SCROLL_TEST_DIR
    test_dir.mkdir(parents=True, exist_ok=True)
    region = window_region(window)
    before_path, before_method, before_mean, before_stddev, before_blank = capture_window_with_fallback(
        pyautogui,
        mss_module,
        Image,
        ImageStat,
        ImageGrab,
        region,
        tmp_dir(output_dir),
        1,
        args.capture_method,
        logger,
    )
    before_dest = test_dir / "before.png"
    before_path.replace(before_dest)

    x, y = chat_point(region, args)
    print("")
    print(
        "Scroll-test will click "
        f"x={x}, y={y}, then scroll mode={args.scroll_mode}, "
        f"clicks={args.scroll_clicks}, bursts={args.scroll_bursts}, pageup={args.pageup_presses}, "
        f"target_overlap={args.target_overlap}."
    )
    logger.info(
        "Scroll-test click point: x=%s y=%s scroll_mode=%s scroll_clicks=%s scroll_bursts=%s pageup_presses=%s drag_pixels=%s",
        x,
        y,
        args.scroll_mode,
        args.scroll_clicks,
        args.scroll_bursts,
        args.pageup_presses,
        args.drag_pixels,
    )
    scroll_result = advance_to_older(
        pyautogui,
        mss_module,
        Image,
        ImageStat,
        ImageGrab,
        region,
        args,
        output_dir,
        before_dest,
        1,
        logger,
    )
    time.sleep(max(args.interval, 1.0))

    after_path, after_method, after_mean, after_stddev, after_blank = capture_window_with_fallback(
        pyautogui,
        mss_module,
        Image,
        ImageStat,
        ImageGrab,
        window_region(window),
        tmp_dir(output_dir),
        2,
        args.capture_method,
        logger,
    )
    after_dest = test_dir / "after.png"
    after_path.replace(after_dest)

    before_size_bytes = before_dest.stat().st_size
    after_size_bytes = after_dest.stat().st_size
    reference_size_bytes = int(round((before_size_bytes + after_size_bytes) / 2))
    disk_space = disk_space_snapshot(output_dir)
    estimated_remaining = estimate_remaining_screenshots(
        int(disk_space["free_bytes"]),
        args.min_free_space_gb,
        reference_size_bytes,
    )

    before_signature = image_signature(Image, before_dest)
    after_signature = image_signature(Image, after_dest)
    diff = signature_difference(before_signature, after_signature)
    movement = estimate_vertical_movement(Image, before_dest, after_dest, args)
    moved = diff is not None and diff > args.duplicate_threshold
    result = {
        "created_at": now_iso(),
        "window_title": window.title,
        "region": region,
        "click_point": {"x": x, "y": y},
        "scroll_mode": args.scroll_mode,
        "scroll_clicks": args.scroll_clicks,
        "scroll_bursts": args.scroll_bursts,
        "pageup_presses": args.pageup_presses,
        "drag_pixels": args.drag_pixels,
        "target_overlap": args.target_overlap,
        "adaptive_step_clicks": args.adaptive_step_clicks,
        "adaptive_max_steps": args.adaptive_max_steps,
        "adaptive_fixed_steps": args.adaptive_fixed_steps,
        "adaptive_lock_after_first": args.adaptive_lock_after_first,
        "min_free_space_gb": args.min_free_space_gb,
        "click_before_scroll": not args.no_click_before_scroll,
        "scroll_result": scroll_result,
        "capture_method_requested": args.capture_method,
        "before": {
            "relative_path": relative_to_output(before_dest, output_dir),
            "size_bytes": before_size_bytes,
            "capture_method": before_method,
            "sha256": hash_file(before_dest),
            "mean_luma": round(before_mean, 2),
            "stddev_luma": round(before_stddev, 2),
            "blank_warning": before_blank,
        },
        "after": {
            "relative_path": relative_to_output(after_dest, output_dir),
            "size_bytes": after_size_bytes,
            "capture_method": after_method,
            "sha256": hash_file(after_dest),
            "mean_luma": round(after_mean, 2),
            "stddev_luma": round(after_stddev, 2),
            "blank_warning": after_blank,
        },
        "diff": None if diff is None else round(diff, 6),
        "estimated_shift_ratio": round(movement["shift_ratio"], 6),
        "estimated_signed_shift_ratio": round(movement["signed_shift_ratio"], 6),
        "estimated_match_score": round(movement["score"], 6),
        "reference_screenshot_size_bytes": reference_size_bytes,
        "reference_screenshot_size_mb": round(reference_size_bytes / BYTES_PER_MB, 3),
        "disk_space": disk_space,
        "estimated_remaining_screenshots": estimated_remaining,
        "capacity_estimate_note": (
            "Reference only. Actual screenshot size changes with chat content, images, stickers, "
            "and window size."
        ),
        "looks_moved": moved,
        "next_steps": [
            "If movement is too small, increase --scroll-clicks to 50 or --scroll-bursts to 5.",
            "If wheel mode still barely moves, try --scroll-mode pageup.",
            "If both wheel and pageup fail, try --scroll-mode drag.",
            "If the direction is wrong, use a negative --scroll-clicks value for wheel mode.",
        ],
    }
    write_json(records_dir(output_dir) / "scroll-test.json", result)
    print(f"Scroll-test diff: {diff:.6f}" if diff is not None else "Scroll-test diff: n/a")
    print(
        "Estimated content movement: "
        f"{movement['shift_ratio']:.1%} of the matched chat area "
        f"(target movement for overlap is {(1.0 - args.target_overlap):.1%})."
    )
    print("Scroll appears to have moved." if moved else "Scroll did not visibly move. Adjust scroll point or focus.")
    return result


def cleanup_tmp(output_dir: Path) -> None:
    temporary_dir = records_dir(output_dir) / TMP_DIR
    if temporary_dir.exists():
        shutil.rmtree(temporary_dir, ignore_errors=True)


def build_run_payload(
    args: argparse.Namespace,
    output_dir: Path,
    started_at: str,
    finished_at: str,
    stop_reason: str,
    rows: list[CaptureRow],
    selected_title: str,
    started_disk_space: dict[str, Any] | None = None,
    finished_disk_space: dict[str, Any] | None = None,
) -> dict[str, Any]:
    saved_count = sum(1 for row in rows if row.saved)
    duplicate_count = sum(1 for row in rows if not row.saved and row.notes.startswith("duplicate"))
    blank_count = sum(1 for row in rows if row.blank_warning)
    return {
        "script": "capture_wechat_group.py",
        "script_version": SCRIPT_VERSION,
        "started_at": started_at,
        "finished_at": finished_at,
        "stop_reason": stop_reason,
        "group_name": args.group_name,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "selected_window_title": selected_title,
        "output_dir": str(output_dir),
        "attempts": len(rows),
        "saved_screenshots": saved_count,
        "duplicate_attempts": duplicate_count,
        "blank_warnings": blank_count,
        "max_screenshots": args.max_screenshots,
        "min_free_space_gb": args.min_free_space_gb,
        "disk_space_start": started_disk_space or {},
        "disk_space_finish": finished_disk_space or {},
        "capture_method": args.capture_method,
        "capture_method_order": list(capture_method_sequence(args.capture_method)),
        "diagnose_capture": args.diagnose_capture,
        "scroll_test": args.scroll_test,
        "scroll_mode": args.scroll_mode,
        "scroll_clicks": args.scroll_clicks,
        "scroll_bursts": args.scroll_bursts,
        "pageup_presses": args.pageup_presses,
        "drag_pixels": args.drag_pixels,
        "target_overlap": args.target_overlap,
        "adaptive_step_clicks": args.adaptive_step_clicks,
        "adaptive_max_steps": args.adaptive_max_steps,
        "adaptive_fixed_steps": args.adaptive_fixed_steps,
        "adaptive_lock_after_first": args.adaptive_lock_after_first,
        "adaptive_settle": args.adaptive_settle,
        "match_region": {
            "x_start": args.match_x_start,
            "x_end": args.match_x_end,
            "y_start": args.match_y_start,
            "y_end": args.match_y_end,
        },
        "click_before_scroll": not args.no_click_before_scroll,
        "scroll_position_ratio": {"x": args.scroll_x_ratio, "y": args.scroll_y_ratio},
        "duplicate_threshold": args.duplicate_threshold,
        "stable_limit": args.stable_limit,
        "hotkey": args.hotkey,
        "machine": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "username": os.environ.get("USERNAME") or os.environ.get("USER") or "",
        },
        "dependency_versions": dependency_versions(
            ["pyautogui", "PyGetWindow", "mss", "Pillow", "keyboard", "pywinauto"]
        ),
        "operator_notes": [
            "This run captures visible screenshots only.",
            "It does not read, export, alter, or decrypt WeChat source data.",
            "Preserve the original WeChat account, device, and chat records for later verification.",
            "For litigation submission, ask counsel whether notarization or forensic preservation is required.",
        ],
    }


def validate_capture_args(args: argparse.Namespace) -> None:
    validate_date(args.start_date, "start-date")
    validate_date(args.end_date, "end-date")
    if validate_date(args.start_date, "start-date") > validate_date(args.end_date, "end-date"):
        raise CaptureAbort("start-date must not be later than end-date.")
    if args.max_screenshots < 0:
        raise CaptureAbort("max-screenshots must be 0 or a positive integer.")
    if args.min_free_space_gb < 0:
        raise CaptureAbort("min-free-space-gb must be 0 or a positive number.")
    if args.interval < 0:
        raise CaptureAbort("interval must be non-negative.")
    if args.stable_limit < 0:
        raise CaptureAbort("stable-limit must be 0 or a positive integer.")
    if args.scroll_bursts < 1:
        raise CaptureAbort("scroll-bursts must be a positive integer.")
    if args.pageup_presses < 1:
        raise CaptureAbort("pageup-presses must be a positive integer.")
    if args.drag_pixels < 1:
        raise CaptureAbort("drag-pixels must be a positive integer.")
    if not (0.05 <= args.target_overlap <= 0.90):
        raise CaptureAbort("target-overlap must be between 0.05 and 0.90.")
    if args.adaptive_step_clicks == 0:
        raise CaptureAbort("adaptive-step-clicks must not be 0.")
    if args.adaptive_max_steps < 1:
        raise CaptureAbort("adaptive-max-steps must be a positive integer.")
    if args.adaptive_fixed_steps < 0:
        raise CaptureAbort("adaptive-fixed-steps must be 0 or a positive integer.")
    if args.adaptive_settle < 0:
        raise CaptureAbort("adaptive-settle must be non-negative.")
    if not (0.0 <= args.match_x_start < args.match_x_end <= 1.0):
        raise CaptureAbort("match-x-start and match-x-end must be valid ratios between 0 and 1.")
    if not (0.0 <= args.match_y_start < args.match_y_end <= 1.0):
        raise CaptureAbort("match-y-start and match-y-end must be valid ratios between 0 and 1.")
    if not args.allow_non_windows and platform.system().lower() != "windows":
        raise CaptureAbort("This capture script is intended for Windows. Use --allow-non-windows only for development checks.")


def run_from_args(
    args: argparse.Namespace,
    *,
    callback: EventCallback | None = None,
    stop_event: threading.Event | None = None,
    require_confirmation: bool | None = None,
) -> CaptureRunResult:
    validate_capture_args(args)
    output_dir = make_output_dir(args.group_name, args.output_dir)
    logger = configure_logging(output_dir)
    callback_handler: CallbackLogHandler | None = None
    if callback is not None:
        callback_handler = CallbackLogHandler(callback)
        callback_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(callback_handler)

    started_at = now_iso()
    started_disk_space = disk_space_snapshot(output_dir)
    rows: list[CaptureRow] = []
    stop_reason = "unknown"
    selected_title = ""
    scroll_test_result: dict[str, Any] | None = None
    diagnostics_result: dict[str, Any] | None = None
    active_stop_event = stop_event or threading.Event()
    should_confirm = (not args.no_confirm) if require_confirmation is None else require_confirmation

    try:
        if not args.diagnose_capture and not args.scroll_test and disk_space_below_limit(
            started_disk_space,
            args.min_free_space_gb,
        ):
            stop_reason = "low_disk_space"
            logger.warning(
                "Stopping before capture because free disk space %.3f GB is below configured reserve %.3f GB.",
                started_disk_space["free_gb"],
                args.min_free_space_gb,
            )
            emit_low_disk_space_event(callback, started_disk_space, args.min_free_space_gb)
            return CaptureRunResult(
                output_dir=str(output_dir),
                stop_reason=stop_reason,
                saved_screenshots=0,
                attempts=0,
                manifest_path=str(records_dir(output_dir) / "manifest.csv"),
                run_json_path=str(records_dir(output_dir) / "run.json"),
                sha256sums_path=str(records_dir(output_dir) / "sha256sums.txt"),
            )

        pyautogui, gw, mss_module, Image, ImageStat, ImageGrab = load_capture_dependencies()
        pyautogui.FAILSAFE = True
        set_windows_dpi_awareness(logger)

        keyboard_module = (
            None
            if (args.diagnose_capture or args.scroll_test)
            else install_stop_hotkey(args.hotkey, active_stop_event, logger, callback)
        )

        window = find_capture_window(gw, args.group_name, logger)
        selected_title = window.title
        emit_event(
            callback,
            "window_selected",
            f"Selected window: {window.title}",
            title=window.title,
            left=int(window.left),
            top=int(window.top),
            width=int(window.width),
            height=int(window.height),
        )
        print_preflight(window, args, output_dir)
        if should_confirm:
            require_operator_confirmation(args)
        activate_window(window, maximize=not args.no_maximize, logger=logger)
        emit_event(callback, "status", "Capture countdown started.", output_dir=str(output_dir))
        countdown(args.preflight_seconds, logger)

        if args.diagnose_capture:
            diagnostics_result = _run_capture_diagnostics(
                pyautogui,
                mss_module,
                Image,
                ImageStat,
                ImageGrab,
                window,
                output_dir,
                logger,
            )
            stop_reason = "diagnose_capture_complete"
            emit_event(callback, "diagnostics_complete", "Diagnostics complete.", result=diagnostics_result)
            return CaptureRunResult(
                output_dir=str(output_dir),
                stop_reason=stop_reason,
                saved_screenshots=0,
                attempts=0,
                manifest_path=str(records_dir(output_dir) / "manifest.csv"),
                run_json_path=str(records_dir(output_dir) / "run.json"),
                sha256sums_path=str(records_dir(output_dir) / "sha256sums.txt"),
                diagnostics_result=diagnostics_result,
            )

        if args.scroll_test:
            scroll_test_result = _run_scroll_test_impl(
                pyautogui,
                mss_module,
                Image,
                ImageStat,
                ImageGrab,
                window,
                output_dir,
                args,
                logger,
            )
            stop_reason = "scroll_test_complete"
            emit_event(callback, "scroll_test_complete", "Scroll test complete.", result=scroll_test_result)
            return CaptureRunResult(
                output_dir=str(output_dir),
                stop_reason=stop_reason,
                saved_screenshots=0,
                attempts=0,
                manifest_path=str(records_dir(output_dir) / "manifest.csv"),
                run_json_path=str(records_dir(output_dir) / "run.json"),
                sha256sums_path=str(records_dir(output_dir) / "sha256sums.txt"),
                scroll_test_result=scroll_test_result,
            )

        previous_signature: bytes | None = None
        previous_saved_relpath = ""
        consecutive_duplicates = 0
        saved_index = 0
        saved_screenshot_bytes = 0
        attempt = 0
        locked_adaptive_steps: int | None = args.adaptive_fixed_steps if args.adaptive_fixed_steps > 0 else None

        while True:
            if active_stop_event.is_set():
                stop_reason = f"operator_hotkey:{args.hotkey}"
                break
            if args.max_screenshots and saved_index >= args.max_screenshots:
                stop_reason = f"max_screenshots:{args.max_screenshots}"
                break

            attempt += 1
            region = window_region(window)
            captured_at = now_iso()
            tmp_path, capture_method, mean_luma, stddev_luma, blank_warning = capture_window_with_fallback(
                pyautogui,
                mss_module,
                Image,
                ImageStat,
                ImageGrab,
                region,
                tmp_dir(output_dir),
                attempt,
                args.capture_method,
                logger,
            )
            digest = hash_file(tmp_path)
            signature = image_signature(Image, tmp_path)
            diff = signature_difference(previous_signature, signature)

            is_duplicate = diff is not None and diff <= args.duplicate_threshold
            current_capture_path: Path
            if is_duplicate:
                consecutive_duplicates += 1
                duplicate_dir = records_dir(output_dir) / DUPLICATES_DIR
                duplicate_dir.mkdir(parents=True, exist_ok=True)
                duplicate_path = duplicate_dir / f"duplicate_attempt_{attempt:06d}.png"
                tmp_path.replace(duplicate_path)
                current_capture_path = duplicate_path
                relpath = relative_to_output(duplicate_path, output_dir)
                row = CaptureRow(
                    attempt=attempt,
                    saved_index="",
                    saved=False,
                    captured_at=captured_at,
                    relative_path=relpath,
                    sha256=digest,
                    capture_method=capture_method,
                    window_title=window.title,
                    window_left=region["left"],
                    window_top=region["top"],
                    window_width=region["width"],
                    window_height=region["height"],
                    diff_from_previous=f"{diff:.6f}",
                    duplicate_of=previous_saved_relpath,
                    blank_warning=blank_warning,
                    mean_luma=f"{mean_luma:.2f}",
                    stddev_luma=f"{stddev_luma:.2f}",
                    scroll_mode_after=args.scroll_mode,
                    scroll_clicks_after=args.scroll_clicks,
                    scroll_bursts_after=args.scroll_bursts,
                    notes=f"duplicate_or_stable_attempt_{consecutive_duplicates}",
                )
                logger.info(
                    "Attempt %s stored as duplicate/stable (%s), diff=%s.",
                    attempt,
                    relpath,
                    row.diff_from_previous,
                )
            else:
                consecutive_duplicates = 0
                saved_index += 1
                capture_dir = output_dir / CAPTURES_DIR
                capture_dir.mkdir(parents=True, exist_ok=True)
                capture_path = capture_dir / f"{saved_index:06d}.png"
                tmp_path.replace(capture_path)
                saved_size_bytes = capture_path.stat().st_size
                saved_screenshot_bytes += saved_size_bytes
                current_capture_path = capture_path
                relpath = relative_to_output(capture_path, output_dir)
                previous_signature = signature
                previous_saved_relpath = relpath
                row = CaptureRow(
                    attempt=attempt,
                    saved_index=saved_index,
                    saved=True,
                    captured_at=captured_at,
                    relative_path=relpath,
                    sha256=digest,
                    capture_method=capture_method,
                    window_title=window.title,
                    window_left=region["left"],
                    window_top=region["top"],
                    window_width=region["width"],
                    window_height=region["height"],
                    diff_from_previous="" if diff is None else f"{diff:.6f}",
                    duplicate_of="",
                    blank_warning=blank_warning,
                    mean_luma=f"{mean_luma:.2f}",
                    stddev_luma=f"{stddev_luma:.2f}",
                    scroll_mode_after=args.scroll_mode,
                    scroll_clicks_after=args.scroll_clicks,
                    scroll_bursts_after=args.scroll_bursts,
                    notes="saved",
                )
                logger.info("Saved screenshot %s (%s).", saved_index, relpath)
                emit_event(
                    callback,
                    "screenshot_saved",
                    f"Saved screenshot {saved_index}.",
                    saved_index=saved_index,
                    saved_size_bytes=saved_size_bytes,
                    total_saved_size_bytes=saved_screenshot_bytes,
                    relative_path=relpath,
                    output_dir=str(output_dir),
                )

            rows.append(row)

            if blank_warning:
                logger.warning(
                    "Attempt %s still looks blank after method %s. Check capture permissions, window visibility, "
                    "remote desktop state, and WeChat hardware acceleration.",
                    attempt,
                    capture_method,
                )
            current_disk_space = disk_space_snapshot(output_dir)
            if disk_space_below_limit(current_disk_space, args.min_free_space_gb):
                stop_reason = "low_disk_space"
                logger.warning(
                    "Stopping because free disk space %.3f GB is below configured reserve %.3f GB.",
                    current_disk_space["free_gb"],
                    args.min_free_space_gb,
                )
                emit_low_disk_space_event(callback, current_disk_space, args.min_free_space_gb)
                break
            if args.stable_limit and consecutive_duplicates >= args.stable_limit:
                stop_reason = f"stable_window_limit:{args.stable_limit}"
                logger.warning("Stopping after %s consecutive duplicate/stable attempts.", consecutive_duplicates)
                break
            if active_stop_event.is_set():
                stop_reason = f"operator_hotkey:{args.hotkey}"
                break

            scroll_result = advance_to_older(
                pyautogui,
                mss_module,
                Image,
                ImageStat,
                ImageGrab,
                region,
                args,
                output_dir,
                current_capture_path,
                attempt,
                logger,
                fixed_steps=locked_adaptive_steps,
            )
            if (
                args.adaptive_lock_after_first
                and locked_adaptive_steps is None
                and scroll_result.get("mode") == "adaptive"
                and scroll_result.get("target_reached") is True
                and isinstance(scroll_result.get("steps"), int)
            ):
                locked_adaptive_steps = int(scroll_result["steps"])
                logger.info("Locked adaptive scrolling to %s fixed steps for the rest of the run.", locked_adaptive_steps)
            logger.info("Scroll result after attempt %s: %s", attempt, scroll_result)
            emit_event(callback, "scroll_result", "Scroll completed.", attempt=attempt, result=scroll_result)
            time.sleep(args.interval)

        if keyboard_module is not None:
            try:
                keyboard_module.unhook_all_hotkeys()
            except Exception:
                pass

    except KeyboardInterrupt:
        stop_reason = "operator_keyboard_interrupt"
        logger.warning("Interrupted by Ctrl+C.")
    except CaptureAbort:
        stop_reason = "aborted"
        raise
    except Exception as exc:
        stop_reason = f"error:{type(exc).__name__}"
        logger.exception("Capture failed: %s", exc)
        raise
    finally:
        finished_at = now_iso()
        finished_disk_space = disk_space_snapshot(output_dir)
        record_dir = records_dir(output_dir)
        manifest_path = record_dir / "manifest.csv"
        run_path = record_dir / "run.json"
        sums_path = record_dir / "sha256sums.txt"
        write_manifest(manifest_path, rows)
        run_payload = build_run_payload(
            args,
            output_dir,
            started_at,
            finished_at,
            stop_reason,
            rows,
            selected_title,
            started_disk_space,
            finished_disk_space,
        )
        write_json(run_path, run_payload)
        cleanup_tmp(output_dir)
        logger.info("Wrote manifest: %s", manifest_path)
        logger.info("Wrote run metadata: %s", run_path)
        logger.info("Final stop reason: %s", stop_reason)
        close_logging(logger)
        sums_path = write_sha256sums(output_dir)
        emit_event(
            callback,
            "finished",
            "Capture run finished.",
            stop_reason=stop_reason,
            saved_screenshots=sum(1 for row in rows if row.saved),
            output_dir=str(output_dir),
        )

    print("")
    print("Capture finished.")
    print(f"Stop reason: {stop_reason}")
    print(f"Saved screenshots: {sum(1 for row in rows if row.saved)}")
    print(f"Output directory: {output_dir}")
    print(f"Review screenshots in {CAPTURES_DIR}/ and records in {RECORDS_DIR}/.")
    return CaptureRunResult(
        output_dir=str(output_dir),
        stop_reason=stop_reason,
        saved_screenshots=sum(1 for row in rows if row.saved),
        attempts=len(rows),
        manifest_path=str(manifest_path),
        run_json_path=str(run_path),
        sha256sums_path=str(sums_path),
        scroll_test_result=scroll_test_result,
        diagnostics_result=diagnostics_result,
    )


def run_capture(
    config: CaptureConfig,
    callback: EventCallback | None = None,
    stop_event: threading.Event | None = None,
) -> CaptureRunResult:
    return run_from_args(config_to_args(config), callback=callback, stop_event=stop_event, require_confirmation=False)


def run_scroll_test(
    config: CaptureConfig,
    callback: EventCallback | None = None,
    stop_event: threading.Event | None = None,
) -> CaptureRunResult:
    return run_from_args(
        config_to_args(config, scroll_test=True),
        callback=callback,
        stop_event=stop_event,
        require_confirmation=False,
    )


def run_diagnostics(
    config: CaptureConfig,
    callback: EventCallback | None = None,
    stop_event: threading.Event | None = None,
) -> CaptureRunResult:
    return run_from_args(
        config_to_args(config, diagnose_capture=True),
        callback=callback,
        stop_event=stop_event,
        require_confirmation=False,
    )


def main() -> int:
    args = parse_args()
    run_from_args(args, require_confirmation=not args.no_confirm)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CaptureAbort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
