from __future__ import annotations

import datetime as dt
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from capture_core import (
    BYTES_PER_GB,
    BYTES_PER_MB,
    CaptureConfig,
    config_to_args,
    default_end_date,
    default_start_date,
    disk_space_snapshot,
    estimate_remaining_screenshots,
    run_capture,
    verify_evidence_dir,
    write_sha256sums,
)


class CaptureCoreTest(unittest.TestCase):
    def test_default_dates_use_three_calendar_months(self) -> None:
        self.assertEqual(default_end_date(dt.date(2026, 6, 10)), "2026-06-10")
        self.assertEqual(default_start_date(dt.date(2026, 6, 10)), "2026-03-10")
        self.assertEqual(default_start_date(dt.date(2026, 5, 31)), "2026-02-28")

    def test_config_to_args_sets_gui_defaults(self) -> None:
        args = config_to_args(
            CaptureConfig(group_name="测试群", start_date="2026-03-10", end_date="2026-06-10"),
            scroll_test=True,
        )
        self.assertEqual(args.group_name, "测试群")
        self.assertEqual(args.target_overlap, 0.35)
        self.assertEqual(args.adaptive_fixed_steps, 8)
        self.assertEqual(args.adaptive_step_clicks, 100)
        self.assertEqual(args.interval, 0.2)
        self.assertEqual(args.min_free_space_gb, 10.0)
        self.assertTrue(args.scroll_test)
        self.assertTrue(args.no_confirm)

    def test_disk_space_snapshot_and_capacity_estimate(self) -> None:
        with TemporaryDirectory() as tmp:
            snapshot = disk_space_snapshot(tmp)
            self.assertIn("free_bytes", snapshot)
            self.assertGreaterEqual(snapshot["free_bytes"], 0)

        remaining = estimate_remaining_screenshots(
            free_bytes=12 * BYTES_PER_GB,
            min_free_space_gb=10.0,
            reference_screenshot_size_bytes=2 * BYTES_PER_MB,
        )
        self.assertEqual(remaining, 1024)

    def test_low_disk_space_precheck_writes_run_records(self) -> None:
        with TemporaryDirectory() as tmp:
            result = run_capture(
                CaptureConfig(
                    group_name="测试群",
                    start_date="2026-03-10",
                    end_date="2026-06-10",
                    output_dir=tmp,
                    min_free_space_gb=1_000_000_000.0,
                    allow_non_windows=True,
                )
            )

            run_path = Path(result.run_json_path)
            self.assertEqual(result.stop_reason, "low_disk_space")
            self.assertTrue(Path(result.manifest_path).exists())
            self.assertTrue(run_path.exists())
            self.assertTrue(Path(result.sha256sums_path).exists())

            payload = json.loads(run_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["stop_reason"], "low_disk_space")
            self.assertEqual(payload["min_free_space_gb"], 1_000_000_000.0)
            self.assertIn("disk_space_start", payload)
            self.assertIn("disk_space_finish", payload)

    def test_verify_evidence_dir_detects_ok_and_modified_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "captures" / "000001.png"
            evidence.parent.mkdir()
            evidence.write_bytes(b"original")
            digest = hashlib.sha256(b"original").hexdigest()
            (root / "sha256sums.txt").write_text(f"{digest}  captures/000001.png\n", encoding="utf-8")

            ok_result = verify_evidence_dir(root)
            self.assertTrue(ok_result["ok"])
            self.assertEqual(ok_result["checked"], 1)

            evidence.write_bytes(b"changed")
            failed_result = verify_evidence_dir(root)
            self.assertFalse(failed_result["ok"])
            self.assertEqual(len(failed_result["failures"]), 1)

    def test_write_sha256sums_uses_records_folder(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "截图" / "000001.png"
            evidence.parent.mkdir()
            evidence.write_bytes(b"original")

            sums_path = write_sha256sums(root)
            self.assertEqual(sums_path, root / "运行记录" / "sha256sums.txt")
            self.assertTrue(sums_path.exists())
            self.assertIn("截图/000001.png", sums_path.read_text(encoding="utf-8"))

            ok_result = verify_evidence_dir(root)
            self.assertTrue(ok_result["ok"])
            self.assertEqual(ok_result["checked"], 1)


if __name__ == "__main__":
    unittest.main()
