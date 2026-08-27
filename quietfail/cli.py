"""quietfail command line."""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter

from . import __version__
from .checks import ALL_CHECKS, BY_ID
from .context import Context
from .finding import CLEAN, FINDINGS, UNINTERPRETABLE, Result
from .selftest import run_all, run_control

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_UNINTERPRETABLE = 2


def ruleset_hash(checks):
    """A number is only reproducible against a stated ruleset."""
    digest = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    for check in sorted(checks, key=lambda c: c.id):
        module = sys.modules[check.__module__].__file__
        with open(module, "rb") as fh:
            digest.update(fh.read())
    return digest.hexdigest()[:12]


def _select(names):
    if not names:
        return list(ALL_CHECKS)
    chosen = []
    for name in names:
        key = name.upper()
        if key not in BY_ID:
            raise SystemExit("unknown check %r; known: %s" % (name, ", ".join(sorted(BY_ID))))
        chosen.append(BY_ID[key])
    return chosen


def cmd_scan(args):
    checks = _select(args.check)
    ctx = Context(args.paths or ["."], follow_symlinks=args.follow_symlinks,
                  exclude=args.exclude)

    controls = {} if args.no_control else run_all(checks)

    started = time.time()
    results = {}
    for check in checks:
        control = controls.get(check.id)
        if control is not None and not control.passed:
            results[check.id] = Result.withheld(
                check.id,
                "positive control failed -- %s. Count withheld: a check that "
                "cannot find a bug it was handed is not a check that found none."
                % control.note(),
            )
            continue
        try:
            results[check.id] = check.run(ctx)
        except Exception as exc:  # a crashed check is uninterpretable, not clean
            results[check.id] = Result.withheld(
                check.id, "check raised %s: %s" % (type(exc).__name__, exc)
            )
    elapsed = time.time() - started

    payload = {
        "tool": "quietfail",
        "version": __version__,
        "ruleset": ruleset_hash(checks),
        "roots": ctx.roots,
        "repos": len(ctx.repos),
        "files": len(ctx.files),
        "elapsed_seconds": round(elapsed, 2),
        "control_run": not args.no_control,
        "checks": {cid: r.as_dict() for cid, r in results.items()},
        "controls": {
            cid: {
                "passed": c.passed,
                "positives": len(c.positives),
                "recovered": c.recovered,
                "negatives": len(c.negatives),
                "false_positives": c.false_positives,
                "note": c.note(),
            }
            for cid, c in controls.items()
        },
    }
    by_repo = _group_by_repo(ctx, results)
    payload["by_repo"] = [
        {"repo": name, "total": sum(counts.values()), "checks": dict(counts)}
        for name, counts in by_repo
    ]
    total = sum(r.count for r in results.values() if r.count is not None)
    withheld = [cid for cid, r in results.items() if r.status == UNINTERPRETABLE]
    payload["silent_failure_surface"] = total
    payload["withheld_checks"] = withheld

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_scan(payload, results, controls, checks, args)
        if args.by_repo:
            _print_by_repo(by_repo, checks)

    if total:
        return EXIT_FINDINGS
    if withheld:
        return EXIT_UNINTERPRETABLE
    return EXIT_CLEAN


INSTALLED_LABEL = "(installed units)"


def _group_by_repo(ctx, results):
    """Findings per repository, most-affected first.

    Findings about installed system state do not belong to any repository --
    that is the whole point of the class they come from -- so they get their
    own row rather than being attributed to whichever checkout they were
    found next to.
    """
    config_root = os.path.abspath(os.path.expanduser("~/.config"))
    table = {}
    for check_id, result in results.items():
        for finding in result.findings:
            if finding.path.startswith(config_root + os.sep):
                label = INSTALLED_LABEL
            else:
                repo = ctx.repo_of(finding.path)
                label = os.path.basename(repo.rstrip(os.sep)) or repo
            table.setdefault(label, Counter())[check_id] += 1
    return sorted(table.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))


def _print_by_repo(by_repo, checks):
    w = sys.stdout.write
    if not by_repo:
        w("no findings to attribute.\n\n")
        return
    ids = [c.id for c in checks]
    name_width = max(len(name) for name, _ in by_repo)
    name_width = max(name_width, 12)
    w("findings by project\n")
    w("  %-*s  %5s   %s\n" % (name_width, "project", "total",
                               " ".join("%5s" % i[2:] for i in ids)))
    w("  %s\n" % ("-" * (name_width + 9 + 6 * len(ids))))
    for name, counts in by_repo:
        cells = " ".join("%5s" % (counts.get(i) or ".") for i in ids)
        w("  %-*s  %5d   %s\n" % (name_width, name, sum(counts.values()), cells))
    w("\n  columns are check numbers (01..%s); a dot means that check found "
      "nothing there.\n\n" % ids[-1][2:])


def _print_scan(payload, results, controls, checks, args):
    w = sys.stdout.write
    w("\nquietfail %s  ruleset %s\n" % (payload["version"], payload["ruleset"]))
    w("scanned %d repo(s), %d file(s) in %.1fs\n" % (
        payload["repos"], payload["files"], payload["elapsed_seconds"]))
    if not payload["control_run"]:
        w("\n  !! positive controls SKIPPED (--no-control). Any zero below is\n"
          "     an unverified zero, which is the bug this tool is named after.\n")
    w("\n")

    width = max(len(c.name) for c in checks) + 2
    for check in checks:
        result = results[check.id]
        if result.status == UNINTERPRETABLE:
            count = "UNINTERPRETABLE"
        elif result.status == CLEAN:
            count = "clean"
        else:
            count = "%d finding%s" % (len(result.findings), "" if len(result.findings) == 1 else "s")
        control = controls.get(check.id)
        ctrl = ""
        if control is not None:
            ctrl = "  [control %d/%d planted, %d/%d lookalikes]" % (
                control.recovered, len(control.positives),
                control.false_positives, len(control.negatives),
            )
        w("  %-6s %-*s %-16s%s\n" % (check.id, width, check.name, count, ctrl))
        if result.note:
            w("         %s\n" % _wrap(result.note, 9))
    w("\n")

    any_findings = any(r.findings for r in results.values())
    for check in checks:
        result = results[check.id]
        if not result.findings or args.quiet:
            continue
        w("%s  %s\n" % (check.id, check.bug_class))
        for finding in result.findings:
            w("  %s\n" % _rel(finding.location(), payload["roots"]))
            w("      %s\n" % _wrap(finding.message, 6))
            if finding.evidence and args.verbose:
                w("      > %s\n" % finding.evidence)
        w("\n")

    total = payload["silent_failure_surface"]
    w("silent-failure surface: %d finding%s across %d repo(s)\n" % (
        total, "" if total == 1 else "s", payload["repos"]))
    if payload["withheld_checks"]:
        w("withheld: %s -- no number is claimed for %s\n" % (
            ", ".join(payload["withheld_checks"]),
            "them" if len(payload["withheld_checks"]) > 1 else "it",
        ))
    if not any_findings and not payload["withheld_checks"]:
        w("every check ran under a passing positive control and found nothing.\n")
    w("\n")


def _rel(path, roots):
    for root in sorted(roots, key=len, reverse=True):
        if path.startswith(root + os.sep):
            return os.path.relpath(path, root)
    return path


def _wrap(text, indent, width=88):
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 > width - indent:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    pad = "\n" + " " * indent
    return pad.join(lines)


def cmd_selftest(args):
    checks = _select(args.check)
    controls = run_all(checks)
    if args.json:
        print(json.dumps({
            "tool": "quietfail",
            "version": __version__,
            "ruleset": ruleset_hash(checks),
            "controls": {
                cid: {
                    "passed": c.passed,
                    "cases": [
                        {"kind": o.kind, "name": o.name, "count": o.count, "passed": o.passed}
                        for o in c.cases
                    ],
                    "note": c.note(),
                }
                for cid, c in controls.items()
            },
        }, indent=2))
    else:
        w = sys.stdout.write
        w("\nquietfail %s selftest  ruleset %s\n\n" % (__version__, ruleset_hash(checks)))
        for check in checks:
            control = controls[check.id]
            w("  %s %s -- %s\n" % (
                check.id, check.name, "PASS" if control.passed else "FAIL"))
            for outcome in control.cases:
                if outcome.kind == "known-miss":
                    mark = "gap " if not outcome.count else "NEW "
                else:
                    mark = "ok  " if outcome.passed else "FAIL"
                w("      %s %-9s %-22s findings=%s\n" % (
                    mark, outcome.kind, outcome.name,
                    "n/a" if outcome.count is None else outcome.count))
            w("      %s\n\n" % _wrap(control.note(), 6))
        recovered = sum(c.recovered for c in controls.values())
        planted = sum(len(c.positives) for c in controls.values())
        fps = sum(c.false_positives for c in controls.values())
        looks = sum(len(c.negatives) for c in controls.values())
        gaps = sum(len(c.known_misses) for c in controls.values())
        w("%d/%d planted instances recovered, %d/%d lookalikes flagged, "
          "%d known recall gap(s) recorded\n\n" % (recovered, planted, fps, looks, gaps))
    return EXIT_CLEAN if all(c.passed for c in controls.values()) else EXIT_FINDINGS


def cmd_explain(args):
    check = BY_ID.get(args.check.upper())
    if check is None:
        raise SystemExit("unknown check %r; known: %s" % (args.check, ", ".join(sorted(BY_ID))))
    module = sys.modules[check.__module__]
    print("\n%s  %s\n%s\n" % (check.id, check.name, check.bug_class))
    print((module.__doc__ or "").strip())
    print()
    return EXIT_CLEAN


def build_parser():
    parser = argparse.ArgumentParser(
        prog="quietfail",
        description=(
            "Find the failures that pass every check you already run: green CI, "
            "exit 0, output on schedule, and nothing making progress."
        ),
    )
    parser.add_argument("--version", action="version", version="quietfail " + __version__)
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="scan a tree and return a number")
    scan.add_argument("paths", nargs="*", help="directories to scan (default: .)")
    scan.add_argument("--check", action="append", default=[], help="limit to a check id")
    scan.add_argument("--json", action="store_true")
    scan.add_argument("-v", "--verbose", action="store_true", help="show the triggering line")
    scan.add_argument("--by-repo", action="store_true",
                      help="rank projects by how many findings each carries")
    scan.add_argument("--quiet", action="store_true",
                      help="summary only -- suppress the per-finding detail")
    scan.add_argument("--follow-symlinks", action="store_true")
    scan.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                      help="skip directories matching this glob (repeatable)")
    scan.add_argument(
        "--no-control", action="store_true",
        help="skip positive controls (any zero it prints is unverified)",
    )
    scan.set_defaults(func=cmd_scan)

    st = sub.add_parser("selftest", help="run every check against its planted fixtures")
    st.add_argument("--check", action="append", default=[])
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_selftest)

    ex = sub.add_parser("explain", help="what a check looks for, and what it deliberately does not")
    ex.add_argument("check")
    ex.set_defaults(func=cmd_explain)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_CLEAN
    return args.func(args)
