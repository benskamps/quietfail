"""The positive control.

Class 6 in the estate taxonomy: *an estimator with no positive control*. A
measurement pipeline returns a confident, plausible, precise number, and
nothing in it ever demonstrates it can recover a KNOWN answer -- so there is
no way to distinguish a measurement from a fit to noise.

Every linter on earth reports "0 findings" identically whether it is working
perfectly or completely broken. That is the same bug, shipped by everyone.

So: each check carries fixtures. Every directory under
`fixtures/<CHECK>/positive/` contains a planted instance the check MUST
find. Every directory under `fixtures/<CHECK>/negative/` contains a
lookalike it must NOT flag -- the recorded non-instances, the shapes that
made the naive version of the query return 200 hits.

If a check cannot recover its own planted instances, `quietfail scan`
refuses to print a number for it. It reports UNINTERPRETABLE. A broken
instrument must never read as an empty sky.
"""

import os

from .context import Context
from .finding import UNINTERPRETABLE

FIXTURE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


class CaseOutcome:
    def __init__(self, check, kind, name, count, passed, note=""):
        self.check = check
        self.kind = kind        # "positive" | "negative"
        self.name = name
        self.count = count
        self.passed = passed
        self.note = note

    def __repr__(self):
        return "<%s %s/%s count=%s %s>" % (
            self.check, self.kind, self.name, self.count,
            "PASS" if self.passed else "FAIL",
        )


class CheckControl:
    def __init__(self, check_id):
        self.check_id = check_id
        self.cases = []

    @property
    def positives(self):
        return [c for c in self.cases if c.kind == "positive"]

    @property
    def negatives(self):
        return [c for c in self.cases if c.kind == "negative"]

    @property
    def known_misses(self):
        """Instances the check is KNOWN not to find, kept on the record.

        A recall gap you have written down is a different thing from a recall
        gap you have not noticed. These never fail the control -- they are
        the honest half of the number.
        """
        return [c for c in self.cases if c.kind == "known-miss"]

    @property
    def newly_detected(self):
        return [c for c in self.known_misses if c.count]

    @property
    def recovered(self):
        return sum(1 for c in self.positives if c.passed)

    @property
    def false_positives(self):
        return sum(1 for c in self.negatives if not c.passed)

    @property
    def has_fixtures(self):
        return bool(self.positives or self.negatives)

    @property
    def passed(self):
        """A check is trustworthy only if it recovers ALL plants and flags no lookalikes."""
        if not self.has_fixtures:
            return False
        return self.recovered == len(self.positives) and self.false_positives == 0

    def note(self):
        if not self.has_fixtures:
            return "no fixtures: this check has never been shown to detect anything"
        bits = []
        missed = [c.name for c in self.positives if not c.passed]
        if missed:
            bits.append("failed to recover planted instance(s): " + ", ".join(missed))
        flagged = [c.name for c in self.negatives if not c.passed]
        if flagged:
            bits.append("flagged known non-instance(s): " + ", ".join(flagged))
        if bits:
            return "; ".join(bits)
        note = "%d/%d planted instances recovered, 0/%d lookalikes flagged" % (
            self.recovered, len(self.positives), len(self.negatives)
        )
        if self.known_misses:
            note += "; %d known recall gap(s) on the record" % len(self.known_misses)
        if self.newly_detected:
            note += " -- %s now DETECTED, promote to positive/" % ", ".join(
                c.name for c in self.newly_detected
            )
        return note


def _case_context(case_dir):
    """Build a Context isolated to one fixture case."""
    installed = os.path.join(case_dir, "installed")
    repo = os.path.join(case_dir, "repo")
    if os.path.isdir(installed):
        roots = [repo] if os.path.isdir(repo) else [case_dir]
        ctx = Context(roots)
        ctx.unit_dirs = [installed]
        return ctx
    ctx = Context([case_dir])
    ctx.unit_dirs = ["/nonexistent-quietfail-unit-dir"]
    return ctx


def run_control(check, fixture_root=FIXTURE_ROOT):
    """Run one check against its fixtures."""
    control = CheckControl(check.id)
    base = os.path.join(fixture_root, check.id)
    for kind in ("positive", "negative", "known-miss"):
        kind_dir = os.path.join(base, kind)
        if not os.path.isdir(kind_dir):
            continue
        for name in sorted(os.listdir(kind_dir)):
            case_dir = os.path.join(kind_dir, name)
            if not os.path.isdir(case_dir):
                continue
            ctx = _case_context(case_dir)
            result = check.run(ctx)
            if result.status == UNINTERPRETABLE:
                control.cases.append(
                    CaseOutcome(check.id, kind, name, None, False, result.note or "")
                )
                continue
            count = len(result.findings)
            if kind == "positive":
                passed = count >= 1
            elif kind == "negative":
                passed = count == 0
            else:
                passed = True  # a documented gap never fails the control
            control.cases.append(CaseOutcome(check.id, kind, name, count, passed))
    return control


def run_all(checks, fixture_root=FIXTURE_ROOT):
    return {c.id: run_control(c, fixture_root) for c in checks}
