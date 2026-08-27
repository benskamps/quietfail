"""QF001 — work set derived from a pattern instead of from the producer.

Class 8, "work set silently empty".

    git add 'report-*-r3.json'  matched nothing
    git commit                 said "nothing to commit"
    exit 0

Nothing loops, nothing stalls. The job runs to completion, correctly, on
nothing -- and an empty work set is indistinguishable from "there was
nothing to do".

The bug is specifically a mutation whose input set is RE-DERIVED from a
pattern that encodes a guess about some other program's naming. When the
producer's naming drifts, the guess stops matching and every command still
succeeds.

NOT an instance, and deliberately not flagged:
  * `git add -A` / `git add .` / `git add -u` -- the work set is "everything
    that changed", and empty there genuinely means nothing changed.
  * a glob mutation in a file that afterwards asks whether the work set was
    empty (`git diff --cached --quiet` and friends).

Calibration (82-repository estate): the broad form of this query
returned 5 hits, 4 of them the legitimate `-A` form. The narrowed form
below returned 1, and it was real.
"""

import re

from ..finding import Finding, Result

GLOB_CHARS = ("*", "?", "[")

# `git add ...`, `git rm ...`, `git stage ...` -- shell form.
_SHELL_MUTATION = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?(add|stage|rm)\b([^\n;&|]*)"
)

# ["git", "add", "report-*.json"] -- python/subprocess list form.
_LIST_MUTATION = re.compile(
    r"""["']git["']\s*,\s*["'](?:add|stage|rm)["']\s*,(?P<args>[^\]]*)"""
)

# A file that asks whether the staged set was empty has mitigated the class.
_EMPTINESS_PROBE = re.compile(
    r"git\s+diff\s+--(?:cached|staged)|--cached\s+--exit-code|"
    r"git\s+status\s+--porcelain|diff-index\s+--quiet|"
    r"diff\s+--quiet\s+--cached"
)

_SAFE_ARGS = {"-a", "-a.", "-a", "--all", "-u", "--update", ".", ":/", "-p",
              "--patch", "-n", "--dry-run", "-f", "--force", "-v", "-i",
              "--", "-r", "--cached", "-A"}

# The shell form is only searched in shell files. Applied to .py it matched
# the sentence "git add executes ..." inside a docstring -- prose, not a
# mutation. Python reaches git through a list, so it gets the list form only.
_SHELL_EXTS = (".sh", ".bash", ".zsh", ".ksh", ".ps1")
_LIST_EXTS = (".py", ".rb", ".pl", ".js", ".ts", ".mjs")
_EXTS = _SHELL_EXTS + _LIST_EXTS

# A work-set pattern names files. It has an extension or a path separator.
_PATHLIKE = re.compile(r"(/|\.[A-Za-z0-9]{1,6}$|\.[A-Za-z0-9]{1,6}[\"\']?$)")


def _globby_args(argstring):
    """Args in `argstring` that carry a glob metacharacter and are not flags."""
    hits = []
    for raw in argstring.split():
        arg = raw.strip("\"'")
        if not arg or arg in _SAFE_ARGS or arg.startswith("$") or arg.startswith("%"):
            continue
        if arg.startswith("-"):
            continue
        if not any(ch in arg for ch in GLOB_CHARS):
            continue
        if not _PATHLIKE.search(arg):
            continue
        hits.append(arg)
    return hits


def _is_comment(line, path):
    stripped = line.lstrip()
    if path.endswith(".py") or path.endswith(".sh") or path.endswith(".bash"):
        return stripped.startswith("#")
    if path.endswith(".ps1"):
        return stripped.startswith("#")
    return False


class QF001:
    id = "QF001"
    name = "work-set-from-pattern"
    bug_class = "Class 8 -- work set silently empty"
    summary = "A mutation whose input set is a guess about another program's naming."

    @staticmethod
    def run(ctx):
        findings = []
        files = ctx.files_with_ext(*_EXTS)
        examined = 0
        for path in files:
            text = ctx.read(path)
            if text is None:
                continue
            if "git" not in text:
                continue
            examined += 1
            if _EMPTINESS_PROBE.search(text):
                # The empty case is detectable in this file. Class mitigated.
                continue
            shell_form = path.lower().endswith(_SHELL_EXTS)
            for lineno, line in enumerate(text.splitlines(), start=1):
                if _is_comment(line, path):
                    continue
                if shell_form:
                    for match in _SHELL_MUTATION.finditer(line):
                        for arg in _globby_args(match.group(2)):
                            findings.append(_finding(path, lineno, match.group(1), arg, line))
                for match in _LIST_MUTATION.finditer(line):
                    for arg in _globby_args(match.group("args").replace(",", " ")):
                        findings.append(_finding(path, lineno, "add", arg, line))
        return Result.of(QF001.id, findings, files_examined=examined)


def _finding(path, lineno, verb, arg, line):
    return Finding(
        check=QF001.id,
        path=path,
        line=lineno,
        message=(
            "`git %s` takes its work set from the pattern %r rather than from "
            "the producer that created the work; if the pattern stops matching, "
            "the command succeeds on nothing and the file reports no error."
            % (verb, arg)
        ),
        evidence=line.strip()[:200],
    )
