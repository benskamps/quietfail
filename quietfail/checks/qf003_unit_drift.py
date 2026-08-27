"""QF003 -- the unit on disk is not the unit in git.

Class 2, "contract shipped but not in force".

The design is documented. The code implementing it is correct and merged.
Nothing sets the variable that switches it on, so the system runs an older
behaviour -- and reading the repo confirms the intended one.

    nightly-report.service, committed:  REPORT_INTERVAL=21600
    nightly-report.service, installed:  REPORT_INTERVAL=14400
                                        Restart=on-failure -> always

The test written to prevent the recurrence asserted against the COMMITTED
unit. The machine runs the other one.

Two findings live here, and the second is the one people forget:
  * DRIFT      -- installed and committed disagree, key by key.
  * UNVERSIONED-- an installed unit with no committed source at all, which
                  no diff can ever catch because there is nothing to diff.

This check is systemd-specific. Where systemd is absent it returns
UNINTERPRETABLE, never CLEAN -- a check reporting zero for a thing it
cannot see is Class 7, and this tool does not get to commit the bugs it
names.
"""

import os

from ..finding import Finding, Result

UNIT_EXTS = (".service", ".timer", ".socket", ".path", ".mount", ".slice")

# User units only. /etc/systemd/system is mostly package-installed and its
# "no committed source" answer is 60-odd true-but-useless findings about
# software the operator did not write. What this class is about is the unit
# an operator hand-installed and then edited in place.
DEFAULT_INSTALLED_DIRS = ("~/.config/systemd/user",)

# Keys whose value legitimately differs between a template and its install.
_VOLATILE_KEYS = {"x-quietfail-ignore"}


def _parse_unit(text):
    """[(section, key, value)] with comments and blank lines dropped."""
    entries = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        entries.append((section, key.strip(), value.strip()))
    return entries


_HOME = os.path.expanduser("~")


def _operator_authored(text):
    """Does this unit execute something the operator wrote?

    Proxy: an Exec* line pointing inside $HOME. A unit running /usr/bin/foo
    came from a package; a unit running ~/projects/x/run.sh did not.
    """
    for section, key, value in _parse_unit(text):
        if key.startswith("Exec") or key in ("WorkingDirectory", "EnvironmentFile"):
            if _HOME in value or value.startswith("%h") or "~/" in value:
                return True
    return False


def _authored(ctx, unit_dir, name, text):
    """Operator-authored, following timers to the service they start.

    A .timer has no Exec* line of its own. The pair this rule was written
    from -- a timer and the service it started -- ran four times a day for
    four days with no versioned copy of either. Judging the timer alone
    would skip exactly that instance.
    """
    if _operator_authored(text):
        return True
    stem, ext = os.path.splitext(name)
    if ext.lower() in (".timer", ".path", ".socket"):
        companion = os.path.join(unit_dir, stem + ".service")
        if os.path.isfile(companion):
            companion_text = ctx.read(companion)
            if companion_text and _operator_authored(companion_text):
                return True
    return False


def _diff_keys(installed, committed):
    """Human-readable list of the entries that disagree."""
    a = set(installed)
    b = set(committed)
    only_installed = a - b
    only_committed = b - a
    keys = sorted({(s, k) for s, k, _ in only_installed} |
                  {(s, k) for s, k, _ in only_committed})
    out = []
    for section, key in keys:
        if key.lower() in _VOLATILE_KEYS:
            continue
        got = [v for s, k, v in installed if (s, k) == (section, key)]
        want = [v for s, k, v in committed if (s, k) == (section, key)]
        out.append("%s/%s: installed=%s committed=%s" % (
            section, key,
            ",".join(got) or "<absent>",
            ",".join(want) or "<absent>",
        ))
    return out


class QF003:
    id = "QF003"
    name = "unit-drift"
    bug_class = "Class 2 -- contract shipped but not in force"
    summary = "The systemd unit running on the machine is not the one in the repo."

    @staticmethod
    def installed_dirs(ctx):
        override = getattr(ctx, "unit_dirs", None)
        if override:
            return [os.path.abspath(os.path.expanduser(d)) for d in override]
        return [
            os.path.abspath(os.path.expanduser(d))
            for d in DEFAULT_INSTALLED_DIRS
        ]

    @staticmethod
    def run(ctx):
        dirs = [d for d in QF003.installed_dirs(ctx) if os.path.isdir(d)]
        if not dirs:
            return Result.withheld(
                QF003.id,
                "no systemd unit directory found (looked in %s) -- this check "
                "cannot see anything here, which is not the same as finding "
                "nothing" % ", ".join(QF003.installed_dirs(ctx)),
            )

        committed = {}
        for path in ctx.files:
            if path.lower().endswith(UNIT_EXTS) and not any(
                path.startswith(d + os.sep) for d in dirs
            ):
                committed.setdefault(os.path.basename(path), []).append(path)

        findings = []
        examined = 0
        for d in dirs:
            for name in sorted(os.listdir(d)):
                installed_path = os.path.join(d, name)
                if not name.lower().endswith(UNIT_EXTS):
                    continue
                if os.path.islink(installed_path) or not os.path.isfile(installed_path):
                    continue
                examined += 1
                text = ctx.read(installed_path)
                if text is None:
                    continue
                sources = committed.get(name, [])
                if not sources and not _authored(ctx, d, name, text):
                    # A packaged unit with no source in the operator's tree is
                    # not their contract to keep. Only flag units that run the
                    # operator's own code.
                    continue
                if not sources:
                    findings.append(
                        Finding(
                            check=QF003.id,
                            path=installed_path,
                            line=0,
                            message=(
                                "installed unit has no committed source anywhere in "
                                "the scanned tree; no diff can ever catch it drifting, "
                                "because there is nothing to diff it against."
                            ),
                            evidence="unversioned",
                        )
                    )
                    continue
                inst = _parse_unit(text)
                for src in sources:
                    src_text = ctx.read(src)
                    if src_text is None:
                        continue
                    diffs = _diff_keys(inst, _parse_unit(src_text))
                    if diffs:
                        findings.append(
                            Finding(
                                check=QF003.id,
                                path=installed_path,
                                line=0,
                                message=(
                                    "installed unit differs from its committed source "
                                    "%s: %s -- a test asserting against the committed "
                                    "file cannot see this."
                                    % (src, "; ".join(diffs))
                                ),
                                evidence="; ".join(diffs)[:300],
                            )
                        )
        return Result.of(QF003.id, findings, files_examined=examined)
