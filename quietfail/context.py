"""Scan context: what files exist, and which repo each one belongs to.

Deliberately dependency-free. A stranger runs this with the python3 they
already have, against a directory they already have, and gets a number.
"""

import fnmatch
import os

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".venv", "venv", "env", ".tox",
    "dist", "build", ".next", ".nuxt", "target", "vendor", ".gradle",
    ".idea", ".vscode", "site-packages", ".terraform", "coverage",
    ".claude", ".cache", "bower_components", ".eggs",
    # Copies of code from elsewhere. Findings here are somebody else's, and
    # 433 of QF007's first 840 came from one mirrored backup of another
    # machine's files.
    "_vendor", "third_party", "third-party", "vendored", "externals",
    "site-packages", "bundled",
}

# Directory NAMES that mean "this is a copy, not a source". Matched on the
# segment, so `vault/skill-mirror-win/` and `archive/2024/` both prune.
COPY_MARKERS = ("skill-mirror", "auto-memory-mirror", "-mirror", "mirror-")

# Generated dependency manifests. Nobody wrote them and nobody can fix a
# finding in one. `@vitest/expect@2.1.9` inside pnpm-lock.yaml accounted for
# 31 of QF006's first 36 findings.
LOCKFILES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
    "poetry.lock", "Cargo.lock", "Gemfile.lock", "composer.lock",
    "uv.lock", "pdm.lock", "go.sum", "flake.lock", "mix.lock",
}

# A file bigger than this is a data artifact, not source we can reason about.
MAX_FILE_BYTES = 1_000_000

# A tree carrying this file holds planted bugs on purpose. Reporting them as
# findings in someone's estate would be a lie, so a scan prunes it.
FIXTURE_MARKER = ".quietfail-fixtures"


class Context:
    """One scan. Walks the roots once; checks share the file list."""

    def __init__(self, roots, follow_symlinks=False, exclude=()):
        self.roots = [os.path.abspath(os.path.expanduser(r)) for r in roots]
        self.follow_symlinks = follow_symlinks
        self.exclude = tuple(exclude)
        self._files = None
        self._repos = None
        self._text_cache = {}

    # -- discovery ---------------------------------------------------------

    def _walk(self):
        files = []
        repos = set()
        seen = set()
        for root in self.roots:
            if os.path.isfile(root):
                files.append(root)
                continue
            for dirpath, dirnames, filenames in os.walk(
                root, followlinks=self.follow_symlinks
            ):
                real = os.path.realpath(dirpath)
                if real in seen:
                    dirnames[:] = []
                    continue
                seen.add(real)
                if os.path.isfile(os.path.join(dirpath, FIXTURE_MARKER)):
                    dirnames[:] = []
                    continue
                if ".git" in dirnames or os.path.isfile(os.path.join(dirpath, ".git")):
                    repos.add(dirpath)
                # Prune `.git` exactly -- NOT everything starting with ".git".
                # The prefix form also pruned `.github`, so every README
                # reference to `ci.yml` resolved against a tree that could not
                # contain it. Four repos' worth of false findings from one
                # character of over-matching.
                dirnames[:] = [
                    d for d in dirnames
                    if d not in SKIP_DIRS and d != ".git"
                    and not any(marker in d for marker in COPY_MARKERS)
                    and not any(
                        fnmatch.fnmatch(os.path.join(dirpath, d), pattern)
                        or fnmatch.fnmatch(d, pattern)
                        for pattern in self.exclude
                    )
                ]
                for name in filenames:
                    if name in LOCKFILES:
                        continue
                    files.append(os.path.join(dirpath, name))
        if not repos:
            repos = set(r for r in self.roots if os.path.isdir(r))
        self._files = files
        self._repos = sorted(repos)

    @property
    def files(self):
        if self._files is None:
            self._walk()
        return self._files

    @property
    def repos(self):
        if self._repos is None:
            self._walk()
        return self._repos

    def files_with_ext(self, *exts):
        exts = tuple(e.lower() for e in exts)
        return [f for f in self.files if f.lower().endswith(exts)]

    def files_named(self, predicate):
        return [f for f in self.files if predicate(os.path.basename(f))]

    # -- reading -----------------------------------------------------------

    def read(self, path):
        """Text of a file, or None if it is binary, huge, or unreadable.

        None means 'not examined'. A check must not treat it as 'clean'.
        """
        if path in self._text_cache:
            return self._text_cache[path]
        text = None
        try:
            if os.path.getsize(path) <= MAX_FILE_BYTES:
                with open(path, "r", encoding="utf-8", errors="strict") as fh:
                    text = fh.read()
        except (OSError, UnicodeDecodeError):
            text = None
        self._text_cache[path] = text
        return text

    def repo_of(self, path):
        """Innermost repo containing path, else the root it came from."""
        best = None
        for repo in self.repos:
            if path.startswith(repo + os.sep) or path == repo:
                if best is None or len(repo) > len(best):
                    best = repo
        if best:
            return best
        for root in self.roots:
            if path.startswith(root + os.sep):
                return root
        return os.path.dirname(path)
