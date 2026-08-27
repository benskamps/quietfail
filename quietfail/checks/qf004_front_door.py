"""QF004 -- a front-door doc points at something that is not there.

Class 5, "claims that were true when written".

Prose that described reality accurately at authoring time and quietly
stopped. Nothing breaks. The repo just lies to its next reader -- including
its next agent.

    A README linked ../companion-derivation/, a sibling experiment that
    existed neither on disk nor on the remote. A 404 for every reader who
    followed it, in the first file anyone opens.

Scoped to front doors on purpose. Resolving every backticked path across all
markdown in an estate gives ~300 hits and is mostly noise. Two narrowings
make it precise, both learned by running the broad version first:

  1. front-door docs only -- README, CONTRIBUTING, DEVELOPING, QUICKSTART,
     INSTALL. That is what a stranger follows.
  2. resolve bare basenames anywhere in the repo before calling a reference
     dead.

SCOPED TO MARKDOWN LINKS, and that narrowing was bought with a measurement.

Including backticked mentions -- `docs/DEPLOYMENT.md`, `config.json` --
gave 40 findings over 82 repos at roughly 40% precision. The false
positives were not random; they were four coherent families, and all four
are the same mistake on this check's part:

    a mention is not a promise that the file is in THIS repo.

  * files the READER owns          `claude_desktop_config.json`, `.mcp.json`
  * files the TOOL creates         `report.md`, `latest.json`, `CONTENT_PLAN.md`
  * files that USED to exist, in a rename table that says so
                                   `resonance-engine/` -> `phase-coordination/`
  * prose about ABSENCE            "there is no runner, and a `.github/workflows/`..."

A markdown link is different in kind. `[the guide](NO_REDDIT_GUIDE.md)` is a
click that either works or 404s, and no amount of surrounding prose changes
that. Restricting to links costs recall -- a stale `D:/OneDrive/...` path in
a README on a replanted Linux box is a genuine instance this version will
not find -- and that gap is recorded in fixtures/QF004/known-miss/ rather
than quietly dropped.

Calibration (by hand, 82-repository estate): broad form ~300 hits, near-zero
signal. Backtick+link form: 40 findings, ~40% precision.
Link-only form: see README for the measured number.
"""

import fnmatch
import os
import re

from ..finding import Finding, Result

FRONT_DOOR = (
    "readme", "contributing", "developing", "quickstart", "install",
    "getting-started", "getting_started", "setup", "usage",
)
DOC_EXTS = (".md", ".rst", ".txt", "")

_BACKTICK = re.compile(r"`([^`\n]{2,120})`")
_MDLINK = re.compile(r"\[[^\]]*\]\(([^)\s]{2,200})\)")

# A token qualifies as a path only if its extension is one a file actually
# has. Accepting "any dot plus 1-6 chars" also accepted version strings
# (0.3.x, vX.Y.Z), hostnames (www.thelongway.ai), addresses (127.0.0.1),
# emails, and attribute access (observer.watch) -- 4 distinct false-positive
# families, all removed by naming the extensions instead of guessing them.
KNOWN_EXTS = set("""
py pyi js ts tsx jsx mjs cjs json jsonl yml yaml toml ini cfg conf md mdx rst
txt sh bash zsh ps1 rb pl go rs java kt swift c h cpp hpp cs php sql html htm
css scss less svg png jpg jpeg gif webp ico pdf csv tsv xml lock service timer
socket path mount gd tscn tres godot plist gradle properties mk cmake jl lua
vim el exs ex erl hs ml scala clj dart vue svelte astro ipynb bat cmd nix tf
tfvars proto graphql gql prisma bicep zip tar gz whl sqlite db log tmpl j2
""".split())

_EXT = re.compile(r"\.([A-Za-z0-9]{1,8})$")
_BARE_EXT = re.compile(r"^\.[A-Za-z0-9]{1,8}$")
_BARE_DOMAIN = re.compile(r"^[\w-]+\.(com|dev|io|org|net|ai|sh|app|co|me|xyz|page)(/|$)")
_GIT_REF = re.compile(r"^(origin|upstream|refs|HEAD|main|master)/")

# A doc naming a file the tool will CREATE is not a doc naming a missing file.
# Deliberately prefix-matched, not word-bounded: the first version used \b
# after each stem, so "generates" did not match "generat" and the check
# flagged its own recorded non-instance. Biased toward false NEGATIVES --
# suppressing a real dead link is cheaper than crying wolf in a front door.
_GENERATED = re.compile(
    r"\b(generat|creat|produc|write|written|emit|output|will be|"
    r"scaffold|template for|placed in|saved to)", re.I
)

# `~/...` and `/...` name things outside the repo on purpose -- the reader's
# own config, an absolute install path. A repo cannot be expected to contain
# them and their absence is not a broken promise.
_SKIP_PREFIX = ("http", "mailto:", "#", "<", "{", "$", "%", "@", "!", "-",
                "~", "/")
_SKIP_CHARS = (" ", "|", ",", "\t", "(", ")", "'", '"', "=", "*", "<", ">",
               "@", "\\")


def _is_front_door(path, repo_root):
    """The front door is the door, not every door.

    Scoped to docs at the repo ROOT. Nested READMEs are internal notes for
    people already inside; including them turned 1 finding into 191, almost
    all of them deliberate references to paths outside the repo.
    """
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(repo_root):
        return False
    stem, ext = os.path.splitext(os.path.basename(path))
    return stem.lower() in FRONT_DOOR and ext.lower() in DOC_EXTS


def _gitignore_patterns(repo_root):
    path = os.path.join(repo_root, ".gitignore")
    patterns = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or line.startswith("!"):
                    continue
                patterns.append(line.rstrip("/"))
    except OSError:
        pass
    return patterns


def _is_ignored(token, patterns):
    """A doc naming a gitignored artifact is not naming a missing file.

    `.env.local`, `creds/cloud-login-raw.json`, `data/` -- the README is
    telling the reader what will exist after they run setup.
    """
    target = token.rstrip("/")
    parts = target.split("/")
    candidates = [target, os.path.basename(target)] + parts
    for pattern in patterns:
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, pattern):
                return True
    return False


def _candidates(text):
    """(candidate, lineno, line) for links a reader can click.

    Backticked mentions were measured and dropped -- see the module
    docstring. What survives is the link target, which is a promise.
    """
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _MDLINK.finditer(line):
            target = match.group(1).strip()
            # [text](path#anchor) and [text](path "title")
            target = target.split("#", 1)[0].strip()
            if target:
                yield target, lineno, line


def _plausible_path(token):
    if not token or token.startswith(_SKIP_PREFIX):
        return False
    if any(ch in token for ch in _SKIP_CHARS):
        return False
    if "://" in token or _BARE_DOMAIN.match(token) or _GIT_REF.match(token):
        return False
    if _BARE_EXT.match(token):
        # "files ending in `.md`" is a claim about a suffix, not about a file.
        return False
    if token.endswith("/"):
        return True
    match = _EXT.search(token)
    return bool(match) and match.group(1).lower() in KNOWN_EXTS


def _resolves(token, doc_dir, repo_root, basenames):
    target = token.rstrip("/")
    for base in (doc_dir, repo_root):
        candidate = os.path.normpath(os.path.join(base, target))
        if os.path.exists(candidate):
            return True
    # Bare basename anywhere in the repo counts -- docs move, files do not.
    # `basenames` carries directory names as well as file names, or every
    # reference to a directory would be unresolvable by construction.
    if os.path.basename(target) in basenames:
        return True
    return False


class QF004:
    id = "QF004"
    name = "dead-front-door-reference"
    bug_class = "Class 5 -- claims that were true when written"
    summary = "The first file a stranger opens points at something that no longer exists."

    @staticmethod
    def run(ctx):
        by_repo = {}
        for path in ctx.files:
            by_repo.setdefault(ctx.repo_of(path), []).append(path)

        findings = []
        examined = 0
        for repo_root, paths in by_repo.items():
            # The repo's own directory name resolves: "this project is rooted
            # at `road-trip/`" is a true statement about the repo, not a
            # reference to a missing subdirectory.
            basenames = {os.path.basename(repo_root)}
            for candidate in paths:
                basenames.add(os.path.basename(candidate))
                parent = os.path.dirname(candidate)
                while parent.startswith(repo_root) and parent != repo_root:
                    basenames.add(os.path.basename(parent))
                    parent = os.path.dirname(parent)
            ignored = _gitignore_patterns(repo_root)
            for path in paths:
                if not _is_front_door(path, repo_root):
                    continue
                text = ctx.read(path)
                if text is None:
                    continue
                examined += 1
                doc_dir = os.path.dirname(path)
                for token, lineno, line in _candidates(text):
                    if not _plausible_path(token):
                        continue
                    if _GENERATED.search(line):
                        continue
                    if _is_ignored(token, ignored):
                        continue
                    if _resolves(token, doc_dir, repo_root, basenames):
                        continue
                    findings.append(
                        Finding(
                            check=QF004.id,
                            path=path,
                            line=lineno,
                            message=(
                                "front-door doc references %r, which does not resolve "
                                "relative to the doc, relative to the repo root, or by "
                                "basename anywhere in the repo -- a dead end for every "
                                "reader who follows it." % token
                            ),
                            evidence=line.strip()[:200],
                        )
                    )
        return Result.of(QF004.id, findings, files_examined=examined)
