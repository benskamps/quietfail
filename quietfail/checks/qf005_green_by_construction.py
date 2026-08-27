"""QF005 -- a check that cannot go red.

Class 1's cousin, and the most expensive kind of silence: a verification step
whose failure is thrown away. The badge is green. It was always going to be
green. It would be green if the code were deleted.

    - run: npm test || true
    - run: mypy src/ ; exit 0
    - run: pytest
      continue-on-error: true

Every one of these reports success to the job, the job reports success to the
branch, and the branch reports success to you. Nothing lied. Nothing ran
either.

THE NARROWING THAT MAKES THIS USABLE: `|| true` is not a bug. It is correct
and common on cleanup -- `docker stop x || true`, `rm -rf tmp || true`, `pkill
foo || true` -- where the failure genuinely does not matter because the thing
was already gone.

The bug is specifically **discarding the failure of a command whose entire
job is to fail when something is wrong.** So this check asks two questions,
not one:

    1. is the exit status discarded?   (|| true, || :, ; exit 0, || exit 0)
    2. is the command a verification?  (test/lint/typecheck/audit/build...)

Both, or it is not reported. A cleanup line with `|| true` is not an
instance and never appears.

`continue-on-error: true` is reported separately and more quietly: it is a
legitimate tool for an experimental matrix leg, so it is only flagged when
the step it covers is itself a verification.
"""

import os
import re

from ..finding import Finding, Result

# Commands whose whole purpose is to fail when something is wrong.
_VERIFY = re.compile(
    r"\b("
    r"pytest|unittest|nose2|tox|"
    r"jest\b|vitest\b|mocha\b|jasmine\b|ava\b|karma\b|playwright\b|cypress\b|"
    r"npm\s+(?:run\s+)?(?:test|lint|typecheck|type-check|audit)|"
    r"(?:pnpm|yarn|bun)\s+(?:run\s+)?(?:test|lint|typecheck|type-check)|"
    r"go\s+test|go\s+vet|cargo\s+test|cargo\s+clippy|"
    r"mvn\s+(?:test|verify)|gradle\s+(?:test|check)|dotnet\s+test|"
    r"phpunit|rspec|bundle\s+exec\s+rspec|"
    r"mypy\b|pyright\b|ruff\b|flake8\b|pylint\b|bandit\b|"
    r"tsc\b|eslint|stylelint|shellcheck|hadolint|"
    r"black\s+--check|prettier\s+--check|isort\s+--check|"
    r"terraform\s+validate|tflint|"
    r"make\s+(?:test|check|lint)|"
    r"quietfail\s+scan"
    r")",
    re.I,
)

# Housekeeping, where a failure genuinely does not matter.
_CLEANUP = re.compile(
    r"^\s*(rm|rmdir|unlink|kill|pkill|killall|docker\s+(?:stop|rm|kill)|"
    r"systemctl\s+(?:stop|disable)|deactivate|umount|"
    r"git\s+worktree\s+remove|npm\s+cache|apt-get\s+remove)\b",
    re.I,
)

# Ways a shell throws an exit status away.
# `|| echo "…"` was in this list for one run and produced two false positives
# out of two findings: `[[ $OK -eq 1 ]] && echo PASS || echo FAIL` is a
# ternary that PRINTS a verdict, and printing a verdict is the opposite of
# discarding one.
_DISCARDS = re.compile(r"(\|\|\s*(?:true|:|exit\s+0)\b|;\s*exit\s+0\b)")

_WORKFLOW_DIRS = (os.sep + ".github" + os.sep + "workflows" + os.sep,)
_SHELLISH = (".sh", ".bash", ".zsh", ".ksh")


def _is_workflow(path):
    return any(marker in path for marker in _WORKFLOW_DIRS) and path.lower().endswith(
        (".yml", ".yaml")
    )


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _run_blocks(text):
    """(lineno, command_text) for every `run:` in a workflow.

    Deliberately line-based rather than YAML-parsed: quietfail ships with no
    dependencies, and the shape being looked for -- a shell command and the
    keys beside it -- survives naive parsing intact.
    """
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)-?\s*run:\s*(\|-?|>-?)?\s*(.*)$", line)
        if not match:
            index += 1
            continue
        base = _indent(line)
        first = match.group(3).strip()
        collected = [(index + 1, first)] if first else []
        cursor = index + 1
        while cursor < len(lines):
            nxt = lines[cursor]
            if nxt.strip() and _indent(nxt) <= base:
                break
            if nxt.strip():
                collected.append((cursor + 1, nxt.strip()))
            cursor += 1
        for lineno, command in collected:
            yield lineno, command
        index = cursor


def _continue_on_error_steps(text):
    """(lineno, nearby_run_text) for steps marked continue-on-error: true."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^\s*continue-on-error:\s*true\s*$", line):
            continue
        base = _indent(line)
        # The step's own run: is a sibling key -- scan out in both directions
        # while the indentation says we are still inside this step.
        neighbourhood = []
        for offset in range(max(0, index - 12), min(len(lines), index + 12)):
            other = lines[offset]
            if other.strip() and _indent(other) >= base:
                neighbourhood.append(other.strip())
        yield index + 1, " ".join(neighbourhood)


class QF005:
    id = "QF005"
    name = "green-by-construction"
    bug_class = "Class 1 -- a verification whose failure is discarded"
    summary = "A check that reports success regardless of what it found."

    @staticmethod
    def run(ctx):
        findings = []
        examined = 0
        candidates = [
            path for path in ctx.files
            if _is_workflow(path) or path.lower().endswith(_SHELLISH)
        ]
        for path in candidates:
            text = ctx.read(path)
            if text is None:
                continue
            examined += 1
            if _is_workflow(path):
                for lineno, command in _run_blocks(text):
                    finding = _judge(path, lineno, command)
                    if finding:
                        findings.append(finding)
                for lineno, neighbourhood in _continue_on_error_steps(text):
                    if _VERIFY.search(neighbourhood):
                        findings.append(Finding(
                            check=QF005.id, path=path, line=lineno,
                            message=(
                                "continue-on-error: true covers a verification step, so "
                                "the job stays green whatever the verification found."
                            ),
                            evidence="continue-on-error: true",
                        ))
            else:
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if line.lstrip().startswith("#"):
                        continue
                    finding = _judge(path, lineno, line.strip())
                    if finding:
                        findings.append(finding)
        return Result.of(QF005.id, findings, files_examined=examined)


def _judge(path, lineno, command):
    if not command or command.startswith("#"):
        return None
    if not _DISCARDS.search(command):
        return None
    if _CLEANUP.match(command):
        return None
    if not _VERIFY.search(command):
        return None
    return Finding(
        check=QF005.id,
        path=path,
        line=lineno,
        message=(
            "the exit status of a verification command is discarded, so this step "
            "reports success whether it passed or failed -- it would stay green "
            "with the code deleted."
        ),
        evidence=command[:200],
    )
