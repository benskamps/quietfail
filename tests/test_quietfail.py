"""Tests for quietfail.

The most important one asserts the thing the tool exists to enforce: a check
that fails its positive control must report UNINTERPRETABLE, never `clean`.
"""

import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quietfail.checks import ALL_CHECKS, BY_ID          # noqa: E402
from quietfail.cli import EXIT_FINDINGS, EXIT_UNINTERPRETABLE, main  # noqa: E402
from quietfail.context import Context                    # noqa: E402
from quietfail.finding import CLEAN, UNINTERPRETABLE, Result  # noqa: E402
from quietfail.selftest import FIXTURE_ROOT, run_all, run_control  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class TestPositiveControls(unittest.TestCase):
    """Every shipped check must recover its plants and spare its lookalikes."""

    def test_every_check_has_fixtures(self):
        for check in ALL_CHECKS:
            control = run_control(check)
            self.assertTrue(
                control.has_fixtures,
                "%s ships with no fixtures: it has never been shown to detect "
                "anything" % check.id,
            )

    def test_every_control_passes(self):
        for check in ALL_CHECKS:
            control = run_control(check)
            self.assertTrue(control.passed, "%s: %s" % (check.id, control.note()))

    def test_known_misses_never_fail_a_control(self):
        controls = run_all(ALL_CHECKS)
        gaps = [c for c in controls.values() if c.known_misses]
        self.assertTrue(gaps, "the recall gaps should be on the record")
        for control in gaps:
            self.assertTrue(control.passed)


class TestWithheldCounts(unittest.TestCase):
    """A count you cannot interpret must not be reported as zero."""

    def test_uninterpretable_count_is_none_not_zero(self):
        result = Result.withheld("QF999", "cannot see anything here")
        self.assertIsNone(result.count)
        self.assertNotEqual(result.count, 0)
        self.assertEqual(result.status, UNINTERPRETABLE)

    def test_clean_count_is_zero(self):
        result = Result.of("QF999", [])
        self.assertEqual(result.count, 0)
        self.assertEqual(result.status, CLEAN)

    def test_missing_systemd_withholds_rather_than_reporting_clean(self):
        ctx = Context([ROOT])
        ctx.unit_dirs = ["/nonexistent-quietfail-unit-dir"]
        result = BY_ID["QF003"].run(ctx)
        self.assertEqual(result.status, UNINTERPRETABLE)
        self.assertIsNone(result.count)


class TestScanContract(unittest.TestCase):
    def test_fixtures_are_pruned_from_a_scan(self):
        """quietfail's own planted bugs must never appear in someone's estate."""
        ctx = Context([ROOT])
        self.assertTrue(ctx.files, "the scan found nothing at all")
        for path in ctx.files:
            self.assertNotIn(
                os.sep + "fixtures" + os.sep, path,
                "fixture tree leaked into a scan: %s" % path,
            )

    def test_dot_github_is_not_pruned(self):
        """`.git` is pruned; `.github` is not -- they are different trees."""
        from quietfail.context import SKIP_DIRS
        self.assertNotIn(".github", SKIP_DIRS)

    def test_scan_of_fixture_tree_exits_with_findings(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["scan", os.path.join(FIXTURE_ROOT, "QF002", "positive"),
                         "--check", "QF002"])
        self.assertEqual(code, EXIT_FINDINGS)

    def test_no_control_still_scans(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["scan", os.path.join(FIXTURE_ROOT, "QF002", "negative"),
                         "--check", "QF002", "--no-control"])
        self.assertIn(code, (0, EXIT_FINDINGS, EXIT_UNINTERPRETABLE))


class TestChecksAgainstThemselves(unittest.TestCase):
    def test_quietfail_is_clean_under_its_own_checks(self):
        """The tool has to survive its own scan, fixtures excluded."""
        ctx = Context([os.path.join(ROOT, "quietfail")])
        # The machine's real units are not quietfail's source; QF003 goes
        # uninterpretable here on purpose.
        ctx.unit_dirs = ["/nonexistent-quietfail-unit-dir"]
        for check in ALL_CHECKS:
            result = check.run(ctx)
            if result.status == UNINTERPRETABLE:
                continue
            self.assertEqual(
                result.findings, [],
                "%s flags quietfail's own source: %s"
                % (check.id, [f.location() for f in result.findings]),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
