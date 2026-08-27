"""QF006 -- a suite that passes because there is nothing in it.

Class 7, "coverage silently to zero". The distinguishing feature versus a
broken check is that this check is **alive, honest, and correct**. It runs, it
reports truthfully, and what it truthfully reports is that it examined
nothing. `0 tests` never costs a score, so it never surfaces as a problem.

    - run: pytest evals/          # evals/ contains no tests
    "test": "jest --passWithNoTests"
    testpaths = tests             # tests/ was renamed in March

Three shapes, all mechanical:

  * **an explicit opt-in** -- `--passWithNoTests` and its spellings. A flag
    that exists precisely to make an empty run green. Sometimes deliberate in
    a monorepo leaf; always worth knowing about.
  * **a runner pointed at a directory with no tests in it** -- resolved and
    counted, not guessed. Missing directory or present-but-empty both count,
    because both produce the same green.
  * **a configured test root that does not exist** -- `testpaths`, jest
    `roots`. The config is read, the path is not there, the collection is
    empty.

NOT flagged: a runner invoked with no path at all (it uses its own discovery,
and this check does not attempt to replicate that), and a directory holding
only fixtures or helpers alongside a real test elsewhere in the same run.
"""

import os
import re

from ..finding import Finding, Result

_PASS_EMPTY = re.compile(
    r"--pass[-_]?with[-_]?no[-_]?tests|--allow[-_]?no[-_]?tests|"
    r"--passWithNoTests", re.I
)

# runner -> what one of its test files looks like
_RUNNERS = {
    "pytest": ("test_*.py", "*_test.py", "conftest.py"),
    "py.test": ("test_*.py", "*_test.py", "conftest.py"),
    "jest": ("*.test.*", "*.spec.*"),
    "vitest": ("*.test.*", "*.spec.*"),
    "mocha": ("*.test.*", "*.spec.*", "*.js", "*.ts"),
    "go test": ("*_test.go",),
}

# The runner name must not be preceded by a dot or a dash. Without that,
# `[tool.pytest.ini_options]` in a pyproject.toml parsed as the command
# `pytest .ini_options]`, and every Python project in the estate reported a
# test run pointed at a directory that has never existed. `@` and `/` joined
# the lookbehind for the same reason: `@vitest/expect@2.1.9` in a lockfile is
# a package name, not somebody running vitest.
_RUNNER_RE = re.compile(
    r"(?<![.\-\w@/])(pytest|py\.test|jest|vitest|mocha|go\s+test)\b(?P<rest>[^\n;&|]*)",
    re.I,
)

_TESTPATHS = re.compile(r"^\s*testpaths\s*=\s*(?P<paths>.+?)\s*$", re.M)
# testpaths is a plain list in ini and a TOML array in pyproject.toml.
_TOML_ITEM = re.compile(r"[\"']([^\"']+)[\"']")

_SCRIPT_LINE = re.compile(r'"(?:test|test:[\w-]+)"\s*:\s*"(?P<cmd>[^"]+)"')

_CONFIG_NAMES = ("pytest.ini", "setup.cfg", "tox.ini", "pyproject.toml")

_SKIP_ARG = re.compile(r"^-|^\$|^%|^\{|::|=")


def _fnmatch_any(name, patterns):
    import fnmatch
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def _count_tests(root, patterns, limit=4000):
    """How many files under `root` look like tests to this runner."""
    seen = 0
    found = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in ("node_modules", ".git", "__pycache__", ".venv", "dist", "build")
        ]
        if os.path.basename(dirpath) == "__tests__" and filenames:
            found += len(filenames)
        for name in filenames:
            seen += 1
            if _fnmatch_any(name, patterns):
                found += 1
            if seen > limit:
                return found
    return found


def _commands(path, text):
    """(lineno, command) for anything that runs a test suite."""
    base = os.path.basename(path).lower()
    if base == "package.json":
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _SCRIPT_LINE.finditer(line):
                yield lineno, match.group("cmd")
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        yield lineno, stripped


class QF006:
    id = "QF006"
    name = "suite-with-no-tests"
    bug_class = "Class 7 -- coverage silently to zero"
    summary = "A test run that is green because it collected nothing."

    @staticmethod
    def run(ctx):
        findings = []
        examined = 0
        interesting = [
            path for path in ctx.files
            if os.path.basename(path).lower() in ("package.json",) + _CONFIG_NAMES
            or path.lower().endswith((".yml", ".yaml", ".sh", ".bash", ".mk"))
            or os.path.basename(path) == "Makefile"
        ]
        for path in interesting:
            text = ctx.read(path)
            if text is None:
                continue
            examined += 1
            repo = ctx.repo_of(path)
            here = os.path.dirname(path)

            config_file = os.path.basename(path).lower() in _CONFIG_NAMES
            for lineno, command in ([] if config_file else _commands(path, text)):
                if _PASS_EMPTY.search(command):
                    findings.append(Finding(
                        check=QF006.id, path=path, line=lineno,
                        message=(
                            "the test runner is told to pass when it collects no "
                            "tests, so an empty or mis-pointed suite is "
                            "indistinguishable from a passing one."
                        ),
                        evidence=command[:200],
                    ))
                for match in _RUNNER_RE.finditer(command):
                    runner = re.sub(r"\s+", " ", match.group(1).lower())
                    patterns = _RUNNERS.get(runner)
                    if patterns is None:
                        continue
                    for target in _targets(match.group("rest")):
                        finding = _judge_target(path, lineno, runner, target,
                                                patterns, here, repo, command)
                        if finding:
                            findings.append(finding)

            if os.path.basename(path).lower() in _CONFIG_NAMES:
                for match in _TESTPATHS.finditer(text):
                    lineno = text[: match.start()].count("\n") + 1
                    blob = match.group("paths")
                    items = _TOML_ITEM.findall(blob) or blob.split()
                    for raw in items:
                        # testpaths is relative to the config file's own
                        # directory -- rootdir, in pytest's terms -- not to the
                        # repository root. Resolving against the repo reported
                        # four of five findings against test suites that were
                        # sitting right next to their pyproject.toml.
                        cleaned = raw.strip("\"'[],")
                        resolved = os.path.join(here, cleaned)
                        if not os.path.exists(resolved):
                            findings.append(Finding(
                                check=QF006.id, path=path, line=lineno,
                                message=(
                                    "configured test root %r does not exist, so "
                                    "collection starts from nothing." % raw
                                ),
                                evidence=match.group(0).strip()[:200],
                            ))
        return Result.of(QF006.id, _dedupe(findings), files_examined=examined)


def _targets(rest):
    for raw in rest.split():
        arg = raw.strip("\"'")
        if not arg or _SKIP_ARG.match(arg):
            continue
        if arg in ("run", "watch", "--"):
            continue
        yield arg


def _judge_target(path, lineno, runner, target, patterns, here, repo, command):
    candidates = [os.path.normpath(os.path.join(base, target)) for base in (here, repo)]
    resolved = next((c for c in candidates if os.path.exists(c)), None)
    if resolved is None:
        # Only claim a miss for something that really looks like a path.
        if "/" not in target and not target.startswith("."):
            return None
        return Finding(
            check=QF006.id, path=path, line=lineno,
            message=(
                "%s is pointed at %r, which does not exist -- the run collects "
                "nothing and says so quietly." % (runner, target)
            ),
            evidence=command[:200],
        )
    if os.path.isfile(resolved):
        return None
    if _count_tests(resolved, patterns) == 0:
        return Finding(
            check=QF006.id, path=path, line=lineno,
            message=(
                "%s is pointed at %r, which contains no files this runner would "
                "collect -- the suite is green because it is empty."
                % (runner, target)
            ),
            evidence=command[:200],
        )
    return None


def _dedupe(findings):
    seen, out = set(), []
    for finding in findings:
        key = (finding.path, finding.line, finding.message)
        if key not in seen:
            seen.add(key)
            out.append(finding)
    return out
