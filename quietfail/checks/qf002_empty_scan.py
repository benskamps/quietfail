"""QF002 -- an empty scan gets serialised over a good artifact.

Class 4, "destructive generator on partial input".

A generator derives its output from a scan of the world. Run somewhere the
world is absent -- a fresh clone, a broken mount, a container without the
volume -- it computes "nothing found" and writes that over the real thing,
and only THEN fails on something unrelated. Data loss precedes the
traceback, so the error message points at the wrong file.

    An index generator, run on a checkout where the sources it scans were
    absent by design, wrote a 0-entry index.json over the real 366-entry one
    -- then crashed on a missing template file, so the traceback named the
    template and never mentioned the index it had just destroyed.

The rule this encodes: **an empty scan should refuse, not serialise.**

Implemented over the AST, because the question is whether a *guard* stands
between the scan and the write, and that is structural.

TAINT IS DELIBERATELY BRITTLE. The first version propagated through any
expression and returned 188 findings on 82 repos, 132 of them from a single
6000-line file where one glob leaked into every local named `text`, `lines`
or `content`. Taint now survives only through operations that keep a
collection whole:

    aliasing              out = repos
    collection literals   {"repos": repos}   [a, b, *repos]
    identity wrappers     sorted/list/set/tuple/reversed(repos)
    whole-set serialisers json.dumps(repos)  yaml.dump(repos)
    joins                 "\\n".join(repos)

and dies at any other call. A value that has been through an arbitrary
function is no longer known to be the scan.

SINKS are whole-file writes only -- json.dump, yaml.dump, pickle.dump,
write_text, writerows, to_json, to_csv. A bare `fh.write(line)` inside a
loop is not this class; it is a line, not the artifact.

GUARDS recognised: `if not xs: return/raise/exit`, `assert xs`, and the
write being lexically inside `if xs:`. Guards are searched across the whole
enclosing scope rather than only on paths that dominate the write. That
direction is deliberate: it yields false NEGATIVES, never false positives.
"""

import ast

from ..finding import Finding, Result

# Calls whose result is "whatever happened to be on disk".
_SCAN_FUNCS = {"glob", "iglob", "glob1", "listdir", "walk", "scandir",
               "rglob", "iterdir"}

# Whole-file writes. `write`/`writelines` are excluded on purpose: a line
# written in a loop is not the artifact being clobbered.
_SINKS = {"dump", "safe_dump", "write_text", "write_bytes", "writerows",
          "to_json", "to_csv"}

# Operations that keep a collection recognisably itself.
_IDENTITY_WRAPPERS = {"sorted", "list", "set", "tuple", "reversed", "dict",
                      "frozenset"}
_SERIALISERS = {"dumps", "dump", "safe_dump", "repr", "join"}

_EXIT_CALLS = {"exit", "_exit", "error", "abort", "die", "fail", "usage"}

# A precondition extracted into a helper is still a precondition. A generator
# that calls corpus_preflight() -- which refuses on an empty corpus and exits --
# from main() is guarded, and an intra-procedural check cannot see it. Recognised by the
# naming convention plus a real exit in the body, which is narrow enough not
# to swallow every function that happens to raise.
_GUARD_NAME = ("preflight", "precheck", "guard", "require", "ensure",
               "validate", "verify_", "assert_", "check_input", "sanity")

# `self` is an object, not a scan result; letting taint reach it poisons a
# whole class.
_NEVER_TAINT = {"self", "cls"}


def _attr(node):
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _is_scan_call(node):
    return isinstance(node, ast.Call) and _attr(node.func) in _SCAN_FUNCS


def _bound(target):
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)} - _NEVER_TAINT


def _scope_nodes(body):
    """Every node in this scope, in source order, without entering nested scopes.

    Source order matters: taint is cleared when a name is reassigned from an
    untainted expression, and out-of-order traversal made that clearing
    meaningless. A harvester that did `content = re.sub(...)` on scanned text
    in one function and `content = f"..."` in another was reported because
    `content` had been tainted once and never recovered.
    """
    collected = []
    stack = list(body)
    while stack:
        node = stack.pop()
        collected.append(node)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef, ast.Lambda)):
                continue
            stack.append(child)
    collected.sort(key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))
    return collected


def _carries_taint(node, tainted):
    """Does this expression still hold the scan's collection?

    Brittle on purpose -- see the module docstring.
    """
    if node is None:
        return False
    if _is_scan_call(node):
        return True
    if isinstance(node, ast.Name):
        return node.id in tainted
    if isinstance(node, ast.Starred):
        return _carries_taint(node.value, tainted)
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return any(_carries_taint(e, tainted) for e in node.elts)
    if isinstance(node, ast.Dict):
        return any(_carries_taint(v, tainted) for v in node.values if v is not None)
    if isinstance(node, ast.Subscript):
        return _carries_taint(node.value, tainted)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        return any(_carries_taint(g.iter, tainted) for g in node.generators)
    if isinstance(node, ast.BinOp):
        return _carries_taint(node.left, tainted) or _carries_taint(node.right, tainted)
    if isinstance(node, ast.Call):
        name = _attr(node.func)
        if name in _IDENTITY_WRAPPERS or name in _SERIALISERS:
            args = list(node.args) + [kw.value for kw in node.keywords]
            # "\n".join(xs) -- the collection is the argument, not the string.
            return any(_carries_taint(a, tainted) for a in args)
        return False
    return False


class _Scope:
    def __init__(self, body, node):
        self.body = body
        self.node = node
        self.tainted = set()
        self._propagate()

    def _propagate(self):
        for _ in range(6):
            before = set(self.tainted)
            for node in _scope_nodes(self.body):
                self._visit(node)
            if self.tainted == before:
                break

    def _visit(self, node):
        if isinstance(node, ast.Assign):
            carries = _carries_taint(node.value, self.tainted)
            for tgt in node.targets:
                if carries:
                    self.tainted |= _bound(tgt)
                else:
                    # Reassigned from something that is not the scan: this name
                    # no longer holds it.
                    self.tainted -= _bound(tgt)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if node.value is not None and _carries_taint(node.value, self.tainted):
                self.tainted |= _bound(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            # for p in glob(...): found.append(p)  -- the accumulator is the scan.
            if not _carries_taint(node.iter, self.tainted):
                return
            for inner in _scope_nodes(node.body):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                    if inner.func.attr in ("append", "extend", "add", "update"):
                        self.tainted |= _bound(inner.func.value)
                elif isinstance(inner, ast.Assign):
                    for tgt in inner.targets:
                        if isinstance(tgt, ast.Subscript):
                            self.tainted |= _bound(tgt.value)

    def guards(self, guard_functions=()):
        guarded = set()
        for node in _scope_nodes(self.body):
            if isinstance(node, ast.Assert):
                guarded |= _names(node.test)
            elif isinstance(node, ast.If):
                if _exits(node.body) or _exits(node.orelse):
                    guarded |= _names(node.test)
            elif isinstance(node, ast.Call) and _attr(node.func) in guard_functions:
                # An extracted precondition covers everything in this scope.
                guarded |= set(self.tainted)
        return guarded


def _exits(body):
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                return True
            if isinstance(node, ast.Call) and _attr(node.func) in _EXIT_CALLS:
                return True
    return False


def _sinks(body):
    for node in _scope_nodes(body):
        if not isinstance(node, ast.Call):
            continue
        if _attr(node.func) not in _SINKS or not node.args:
            continue
        yield node, node.args[0]


def _enclosing_if_tests(root, target):
    tests = []

    def walk(node, stack):
        if node is target:
            tests.extend(stack)
            return True
        for child in ast.iter_child_nodes(node):
            nxt = stack + [node.test] if isinstance(node, ast.If) and child in node.body else stack
            if walk(child, nxt):
                return True
        return False

    walk(root, [])
    return tests


def _guard_functions(tree):
    """Module-level functions that look like, and behave like, preconditions."""
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(token in node.name.lower() for token in _GUARD_NAME):
            continue
        if _exits(node.body):
            found.add(node.name)
    return found


def _scopes(tree):
    yield tree.body, tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.body, node


class QF002:
    id = "QF002"
    name = "empty-scan-serialised"
    bug_class = "Class 4 -- destructive generator on partial input"
    summary = "A file written from a directory scan, with nothing refusing when the scan is empty."

    @staticmethod
    def run(ctx):
        findings = []
        examined = 0
        for path in ctx.files_with_ext(".py"):
            text = ctx.read(path)
            if text is None:
                continue
            if not any(k in text for k in ("glob", "listdir", "walk", "iterdir", "scandir")):
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            examined += 1
            guard_functions = _guard_functions(tree)
            for body, node in _scopes(tree):
                scope = _Scope(body, node)
                if not scope.tainted:
                    continue
                guarded = scope.guards(guard_functions)
                if guarded & scope.tainted:
                    # A refusal on the empty scan ANYWHERE in this scope covers
                    # the scope. `if not plans: raise SystemExit` guards `plans`,
                    # and everything computed from plans inherits it -- demanding
                    # the guard name the derived value reported a function that
                    # refuses on an empty scan in its third line.
                    continue
                for call, value in _sinks(body):
                    used = _names(value) & scope.tainted
                    if not used or not _carries_taint(value, scope.tainted):
                        continue
                    if used & guarded:
                        continue
                    enclosing = set()
                    for test in _enclosing_if_tests(node, call):
                        enclosing |= _names(test)
                    if used & enclosing:
                        continue
                    findings.append(Finding(
                        check=QF002.id,
                        path=path,
                        line=getattr(call, "lineno", 0),
                        message=(
                            "serialises %s -- which comes from a directory scan -- "
                            "over a file, with no guard refusing when the scan is "
                            "empty; run where the source is absent, this writes "
                            "'nothing found' over the previous artifact."
                            % ", ".join(sorted(used))
                        ),
                        evidence=_snippet(text, getattr(call, "lineno", 0)),
                    ))
        return Result.of(QF002.id, _dedupe(findings), files_examined=examined)


def _dedupe(findings):
    """One finding per write site: module and function scope both reach it."""
    seen, out = set(), []
    for finding in findings:
        key = (finding.path, finding.line)
        if key not in seen:
            seen.add(key)
            out.append(finding)
    return out


def _snippet(text, lineno):
    lines = text.splitlines()
    return lines[lineno - 1].strip()[:200] if 0 < lineno <= len(lines) else ""
