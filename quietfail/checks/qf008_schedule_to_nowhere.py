"""QF008 -- a schedule pointing at something that is not there.

The timer fires on time, forever. The thing it fires is missing, renamed, or
was never installed. systemd records the failure in the journal and moves on;
nothing else in your life mentions it. This is the shape where the *cadence*
survives its own subject -- the most convincing kind of liveness, because
something really is happening on schedule.

Two questions:

  * **does the timer have a unit to start?** A `.timer` with no `Unit=` starts
    `<same-name>.service` by convention. If that file is not beside it, every
    activation fails.
  * **does the service have a program to run?** An absolute `ExecStart` path
    that does not exist on disk is a unit that can only ever fail, and a unit
    that has only ever failed looks identical to one that has not run yet.

Only absolute paths are resolved. A bare command name is left alone, because
resolving it means guessing the unit's PATH, and a guess belongs in a
different tool than this one.

Returns UNINTERPRETABLE when there are no units in scope at all: zero units
examined is not the same finding as zero problems found.
"""

import os
import re

from ..finding import Finding, Result

UNIT_EXTS = (".service", ".timer", ".socket", ".path", ".mount")
_EXEC = re.compile(r"^\s*(Exec(?:Start|StartPre|StartPost|Stop|Reload))\s*=\s*(?P<cmd>.+?)\s*$")
_UNIT_KEY = re.compile(r"^\s*Unit\s*=\s*(?P<unit>\S+)\s*$", re.M)

# Prefixes systemd allows before the executable: -, @, +, !, !!
_EXEC_PREFIX = re.compile(r"^[-@+!]+")


def _executable(command):
    """The program an Exec= line actually runs, or None if not resolvable."""
    command = command.strip()
    if not command:
        return None
    first = command.split()[0]
    first = _EXEC_PREFIX.sub("", first)
    if not first.startswith("/"):
        return None                      # PATH lookup or a specifier; not ours to guess
    if "%" in first or "$" in first:
        return None                      # systemd specifier or variable
    # /bin/sh -c '...' runs the string, not a file we can check cheaply.
    if os.path.basename(first) in ("sh", "bash", "dash", "zsh", "env"):
        return None
    return first


class QF008:
    id = "QF008"
    name = "schedule-to-nowhere"
    bug_class = "Class 1 -- a cadence that outlived its subject"
    summary = "A timer or service whose target does not exist."

    @staticmethod
    def run(ctx):
        unit_dirs = getattr(ctx, "unit_dirs", None)
        if unit_dirs is None:
            unit_dirs = ["~/.config/systemd/user"]
        dirs = [os.path.abspath(os.path.expanduser(d)) for d in unit_dirs]

        units = {}
        for path in ctx.files:
            if path.lower().endswith(UNIT_EXTS):
                units.setdefault(os.path.dirname(path), []).append(path)
        for directory in dirs:
            if not os.path.isdir(directory):
                continue
            for name in sorted(os.listdir(directory)):
                if name.lower().endswith(UNIT_EXTS):
                    units.setdefault(directory, []).append(os.path.join(directory, name))

        total = sum(len(paths) for paths in units.values())
        if total == 0:
            return Result.withheld(
                QF008.id,
                "no systemd units in scope (searched the tree and %s) -- zero units "
                "examined is not zero problems found" % ", ".join(dirs),
            )

        findings = []
        for directory, paths in units.items():
            present = {os.path.basename(p) for p in paths}
            for path in sorted(set(paths)):
                text = ctx.read(path)
                if text is None:
                    continue
                name = os.path.basename(path)

                if name.lower().endswith(".timer"):
                    match = _UNIT_KEY.search(text)
                    wanted = match.group("unit") if match else \
                        os.path.splitext(name)[0] + ".service"
                    if wanted not in present:
                        findings.append(Finding(
                            check=QF008.id, path=path, line=0,
                            message=(
                                "timer activates %r, which is not beside it -- the "
                                "timer stays enabled and every activation fails."
                                % wanted
                            ),
                            evidence="Unit=%s" % wanted,
                        ))

                for lineno, line in enumerate(text.splitlines(), start=1):
                    match = _EXEC.match(line)
                    if not match:
                        continue
                    program = _executable(match.group("cmd"))
                    if program and not os.path.exists(program):
                        findings.append(Finding(
                            check=QF008.id, path=path, line=lineno,
                            message=(
                                "%s runs %s, which does not exist on disk -- this "
                                "unit can only fail, and a unit that has only ever "
                                "failed looks the same as one that has not run yet."
                                % (match.group(1), program)
                            ),
                            evidence=line.strip()[:200],
                        ))
        return Result.of(QF008.id, findings, files_examined=total)
