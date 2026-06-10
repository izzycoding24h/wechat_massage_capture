from __future__ import annotations

import datetime as dt
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from capture_core import CaptureConfig, config_to_args, default_end_date, default_start_date, verify_evidence_dir


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
        self.assertTrue(args.scroll_test)
        self.assertTrue(args.no_confirm)

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


if __name__ == "__main__":
    unittest.main()
