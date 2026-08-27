"""QF007 -- an error caught and dropped on the floor.

The failure happened. Something noticed. Nothing recorded it, nothing
re-raised it, and the function returned as though the work had been done.
This is the smallest unit of silence in the taxonomy and the most widely
distributed: it does not need a scheduler or a pipeline, only a try block.

    except Exception:
        pass

    } catch (e) {}

    Remove-Item $tmp -ErrorAction SilentlyContinue

THE NARROWING. A handler that does nothing is not automatically a bug --
`except FileNotFoundError: pass` around an optional cache file is a decision,
written down in the exception type. What makes it a defect is doing nothing
about an error you did not name:

    * the caught type is broad -- bare `except`, `Exception`, `BaseException`,
      an untyped `catch (e)`, or `catch` with no binding at all; AND
    * the body is empty -- `pass` alone or `{}` -- AND
    * nothing marks it as deliberate. A comment in the handler is treated as
      content, and so is an underscore binding -- `catch (_)` is the
      language's own idiom for a discard someone chose:
      `catch (e) { /* Safari throws when not user-initiated */ }` is a
      decision someone made and wrote down, which is a different object from
      a failure nobody noticed.

Narrow types are never reported, however empty the body.

THE FOURTH CONDITION, added after measuring. Those three rules alone returned
367 findings on an 82-repo estate, and they were *true* -- every one really
was a broad, empty, undocumented handler. They were also not worth reading,
because most of them wrapped something cosmetic: a fullscreen request, a
focus() call, a feature probe. An error vanishing there costs nothing.

So the try block must contain **an operation with an effect** -- a write, a
network call, a database mutation, a subprocess, an `await`. That is the
difference between "an error disappeared" and "a change you believe you made
never happened, and nothing anywhere says so." The second one is worth
waking up for.

Python is read through the AST, so the body is known exactly rather than
guessed. JavaScript and TypeScript are matched textually, with brace
balancing to confirm the block really is empty.
"""

import ast
import os
import re

from ..finding import Finding, Result

_BROAD_PY = {"Exception", "BaseException", "StandardError"}

# catch (e) { }  |  catch { }  |  catch (e: any) { }
_CATCH = re.compile(r"\bcatch\s*(?:\(\s*([A-Za-z_$][\w$]*)?[^)]*\)\s*)?\{")
# .catch(() => {})  and  .catch(function () {})
_PROMISE_CATCH = re.compile(r"\.catch\s*\(\s*(?:\([^)]*\)|function\s*\([^)]*\))\s*=?>?\s*\{\s*\}\s*\)")

_PS_SILENT = re.compile(r"-ErrorAction\s+SilentlyContinue", re.I)
# Same rule as everywhere else: only when the suppressed command changes
# something. `Get-WinEvent -ErrorAction SilentlyContinue` is a query that came
# back empty; `Remove-Item -ErrorAction SilentlyContinue` is a deletion that
# may never have happened.
_PS_MUTATION = re.compile(
    r"\b(Remove-|Set-|New-|Copy-|Move-|Rename-|Add-|Clear-|Stop-|Start-|"
    r"Restart-|Out-File|Export-|Import-|Install-|Uninstall-|Register-|"
    r"Unregister-|Write-)", re.I
)

_COMMENT_LINE = re.compile(r"^\s*(//|/\*|\*|#)")

# Operations whose silent failure changes what is true in the world.
_EFFECT_PY = re.compile(
    r"\b(open\s*\(|\.write|\.writelines|\.dump|shutil\.|os\.(?:remove|unlink|"
    r"rename|replace|makedirs|mkdir|rmdir|chmod|symlink)|subprocess\.|"
    r"\.execute|\.commit|\.insert|\.save|\.delete|\.update|"
    r"requests\.|urlopen|urlretrieve|httpx\.|\.post|\.put|\.patch|\.send|"
    r"\.publish|\.upload|Path\(.*\)\.(?:write|unlink|rename))"
)
_EFFECT_JS = re.compile(
    r"(\bawait\b|\bfetch\s*\(|\.write|writeFile|\.insert|\.save|\.update|"
    r"\.delete|\.commit|\.exec|spawn|\.send|\.publish|\.upload|"
    r"localStorage\.setItem|sessionStorage\.setItem|\.mutate|\.rpc\s*\(|"
    # camelCase verb prefixes: sendPush(), uploadAvatar(), persistDraft().
    # Narrow on purpose -- the capital letter is what keeps `push(` (arrays)
    # and `post` (nouns) out of it.
    r"\b(?:send|post|upload|persist|save|write|insert|delete|update|sync|"
    r"publish|submit|record|commit|flush)[A-Z]\w*\s*\()"
)


def _empty_block(text, open_brace_index):
    """Is the {...} starting at open_brace_index empty but for comments?"""
    depth = 0
    for index in range(open_brace_index, min(len(text), open_brace_index + 4000)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                inner = text[open_brace_index + 1:index]
                # A comment counts as content: it is the author saying why.
                return inner.strip() == ""
    return False


def _python_findings(path, text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out = []
    for try_node in ast.walk(tree):
        if not isinstance(try_node, ast.Try):
            continue
        guarded = "\n".join(_segment(text, stmt) for stmt in try_node.body)
        if not _EFFECT_PY.search(guarded):
            continue
        for node in try_node.handlers:
            if not _is_broad(node.type):
                continue
            body = [stmt for stmt in node.body if not _is_docstring(stmt)]
            if len(body) != 1 or not isinstance(body[0], ast.Pass):
                continue
            if _explained(text, node, body[0]):
                continue
            out.append(_py_finding(path, text, node))
    return out


def _segment(text, stmt):
    lines = text.splitlines()
    start = getattr(stmt, "lineno", 1) - 1
    end = getattr(stmt, "end_lineno", getattr(stmt, "lineno", 1))
    return "\n".join(lines[start:end])


def _py_finding(path, text, node):
    if True:
        return Finding(
            check=QF007.id, path=path, line=node.lineno,
            message=(
                "catches %s and does nothing -- an unknown failure here leaves no "
                "trace, and the caller cannot tell the work was skipped."
                % (_type_name(node.type) or "every exception"),
            )[0],
            evidence=_line(text, node.lineno),
        )


def _explained(text, handler, pass_stmt):
    """Is there a comment on or just above the `pass`, or on the except line?

    An explanation is a decision. This check is looking for the failures
    nobody noticed, not the ones somebody chose.
    """
    lines = text.splitlines()
    for lineno in (handler.lineno, pass_stmt.lineno, pass_stmt.lineno - 1):
        if 0 < lineno <= len(lines) and "#" in lines[lineno - 1]:
            return True
    return False


def _is_docstring(stmt):
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
        and isinstance(stmt.value.value, str)


def _type_name(node):
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_broad(node):
    if node is None:
        return True  # bare except
    if isinstance(node, ast.Tuple):
        return any(_is_broad(element) for element in node.elts)
    return _type_name(node) in _BROAD_PY


def _js_findings(path, text):
    out = []
    for match in _CATCH.finditer(text):
        binding = match.group(1)
        if not _EFFECT_JS.search(_try_block(text, match.start())):
            continue
        if binding and binding.lstrip("_") == "" or (binding or "").startswith("_"):
            # `catch (_)` / `catch (_err)` is the established way of writing
            # "I know, and I mean it" -- the same decision a comment records.
            continue
        # `catch (NotFoundError)` is not a thing in JS -- the binding is a
        # variable, so every catch here is broad by construction. What varies
        # is whether the body does anything.
        brace = text.index("{", match.end() - 1)
        if not _empty_block(text, brace):
            continue
        lineno = text[: match.start()].count("\n") + 1
        out.append(Finding(
            check=QF007.id, path=path, line=lineno,
            message=(
                "catch block is empty, so any failure inside the try is discarded "
                "without a log line, a rethrow, or a return value that says so."
            ),
            evidence=(("catch (%s) {}" % binding) if binding else "catch {}"),
        ))
    for match in _PROMISE_CATCH.finditer(text):
        # The effect is the call being caught: fetch(...).catch(() => {}) is a
        # dropped request; el.play().catch(() => {}) is a browser being fussy.
        if not _EFFECT_JS.search(_statement_before(text, match.start())):
            continue
        lineno = text[: match.start()].count("\n") + 1
        out.append(Finding(
            check=QF007.id, path=path, line=lineno,
            message=(
                "a rejected promise is caught by an empty handler -- the operation "
                "reports success to everything downstream."
            ),
            evidence=match.group(0)[:120],
        ))
    return out


def _statement_before(text, index, span=240):
    """The chained expression a `.catch()` is attached to."""
    start = max(0, index - span)
    window = text[start:index]
    cut = max(window.rfind(";"), window.rfind("{"), window.rfind("}"))
    return window[cut + 1:] if cut != -1 else window


def _try_block(text, catch_index, span=1600):
    """The source of the try block this catch belongs to.

    Walks back from `catch` to its `try`; if the pairing cannot be found the
    preceding window is used, which is the conservative direction -- a wider
    window can only make an effect MORE likely to be seen, and this check is
    trying not to over-report.
    """
    window_start = max(0, catch_index - span)
    window = text[window_start:catch_index]
    marker = window.rfind("try")
    return window[marker:] if marker != -1 else window


def _line(text, lineno):
    lines = text.splitlines()
    return lines[lineno - 1].strip()[:200] if 0 < lineno <= len(lines) else ""


class QF007:
    id = "QF007"
    name = "swallowed-error"
    bug_class = "Class 1 -- silence that reads as health, at statement scale"
    summary = "A broad exception caught and discarded without a trace."

    @staticmethod
    def run(ctx):
        findings = []
        examined = 0
        for path in ctx.files_with_ext(".py", ".js", ".jsx", ".ts", ".tsx", ".mjs",
                                       ".cjs", ".ps1"):
            text = ctx.read(path)
            if text is None:
                continue
            lower = path.lower()
            if lower.endswith(".py"):
                if "except" not in text:
                    continue
                examined += 1
                findings.extend(_python_findings(path, text))
            elif lower.endswith(".ps1"):
                if "SilentlyContinue" not in text:
                    continue
                examined += 1
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if (_PS_SILENT.search(line) and _PS_MUTATION.search(line)
                            and not line.lstrip().startswith("#")):
                        findings.append(Finding(
                            check=QF007.id, path=path, line=lineno,
                            message=(
                                "-ErrorAction SilentlyContinue discards the error and "
                                "continues, so the next line runs on state that may "
                                "never have been created."
                            ),
                            evidence=line.strip()[:200],
                        ))
            else:
                if "catch" not in text:
                    continue
                examined += 1
                findings.extend(_js_findings(path, text))
        return Result.of(QF007.id, findings, files_examined=examined)
