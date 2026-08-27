# quietfail

**A linter for the failures that pass every check you already run.**

Green CI. Exit 0. Output on schedule. Nothing making progress.

```
$ python3 -m quietfail scan ~/projects --by-repo

quietfail 0.2.0
scanned 82 repo(s), 16622 file(s) in 16.1s

  QF001  work-set-from-pattern       clean        [control 3/3 planted, 0/4 lookalikes]
  QF002  empty-scan-serialised       2 findings   [control 3/3 planted, 0/8 lookalikes]
  QF003  unit-drift                  22 findings  [control 2/2 planted, 0/1 lookalikes]
  QF004  dead-front-door-reference   5 findings   [control 1/1 planted, 0/5 lookalikes]
  QF005  green-by-construction       clean        [control 3/3 planted, 0/4 lookalikes]
  QF006  suite-with-no-tests         1 finding    [control 3/3 planted, 0/4 lookalikes]
  QF007  swallowed-error             64 findings  [control 4/4 planted, 0/6 lookalikes]
  QF008  schedule-to-nowhere         clean        [control 2/2 planted, 0/3 lookalikes]

silent-failure surface: 94 findings across 82 repo(s)
```

No install, no dependencies, no config. Python 3.8+ and a directory.

```
git clone https://github.com/benskamps/quietfail && cd quietfail
python3 -m quietfail scan /path/to/your/repos
```

---

## The one thing that makes this different

**quietfail will not print a zero it has not earned.**

Every check ships with fixtures: directories holding a planted instance of
the bug it hunts, and directories holding lookalikes it must not flag. Before
a scan reports anything, each check has to find its own planted bugs and
leave the lookalikes alone. A check that fails its control does not report
`0 findings`. It reports:

```
  QF002  empty-scan-serialised   UNINTERPRETABLE
         positive control failed -- failed to recover planted instance(s):
         walk-accumulate. Count withheld: a check that cannot find a bug it
         was handed is not a check that found none.
```

Every other linter reports "0 findings" identically whether it is working
perfectly or completely broken. That is the same bug it is looking for, and
it ships in the instrument. `quietfail selftest` runs the controls on their
own; `scan` runs them first, every time, and `--no-control` says out loud
that the zero it prints is unverified.

---

## What it looks for

Four classes, each drawn from an outage that actually happened and was
priced. The unifying property: **the failure is invisible in exactly the
surfaces you would check.** A stranger sees green and infers health.

| id | class | the shape |
|---|---|---|
| **QF001** | work set silently empty | `git add 'report-*-r3.json'` matched nothing, `git commit` said nothing to commit, exit 0. The job ran to completion, correctly, on nothing. |
| **QF002** | destructive generator on partial input | A generator scans the world, is run where the world is absent, computes "nothing found", and writes that over the good artifact — then fails on something unrelated, so the traceback points at the wrong file. |
| **QF003** | contract shipped but not in force | The unit on the machine is not the unit in git. The test written to prevent the recurrence asserts against the committed file. |
| **QF004** | claims that were true when written | The first file a stranger opens links to something that no longer exists. |
| **QF005** | a verification whose failure is discarded | `npm test \|\| true`. The badge is green. It was always going to be green. It would be green with the code deleted. |
| **QF006** | coverage silently to zero | `pytest tests/` where `tests/` does not exist; `--passWithNoTests`; a configured test root that was renamed. The suite passes because it is empty. |
| **QF007** | an error caught and dropped | A broad, empty, undocumented handler wrapped around something that *writes* — the change you believe you made never happened and nothing says so. |
| **QF008** | a cadence that outlived its subject | A timer with no unit beside it, or a service whose `ExecStart` is not on disk. It fires on schedule, forever, into nothing. |

`python3 -m quietfail explain QF002` prints the full account of any check:
what it looks for, what it deliberately does not, and what it is known to
miss.

---

## Calibration, and why the numbers above are small

Each of these queries was written twice. The first version of every one of
them returned hundreds of hits and near-zero signal:

| check | naive form | shipped form | what the narrowing was |
|---|---|---|---|
| QF001 | 5 | 0 | shell syntax only in shell files — applied to `.py` it matched the sentence *"git add executes…"* inside a docstring |
| QF002 | 188 | 2 | taint that dies at any unrecognised call, clears on reassignment, and respects a guard extracted into a helper |
| QF003 | 74 | 22 | user units only, and only units that run the operator's own code — a packaged unit's missing source is not their contract to keep |
| QF004 | 808 | 5 | markdown links only, at the repo root |
| QF005 | 3 | 0 | `\|\| echo "…"` prints a verdict, which is the opposite of discarding one — and `\bava` matched the word *"available"* |
| QF006 | 61 | 1 | `[tool.pytest.ini_options]` is not somebody running pytest; `@vitest/expect` in a lockfile is a package name; `testpaths` resolves beside its config, not at the repo root |
| QF007 | 840 | 64 | mirrored copies of other machines' code excluded; `catch (_)` is the language's own idiom for a deliberate discard; and the guarded block must contain something with an **effect** |
| QF008 | 0 | 0 | absolute paths only — resolving a bare command means guessing the unit's PATH |

Total across the eight: **933 on the first pass, 94 shipped.** Every one of those
reductions was a defect in the checker, not a finding being suppressed — with one
exception, stated plainly: QF007's effect gate is a deliberate trade. The 367
findings it dropped were all *true* broad-empty-undocumented handlers. They were
also not worth reading, because they wrapped a `focus()` call or a feature probe.
An error vanishing there costs nothing.

**The narrowing is the product.** A detector that reports 800 things is not a
detector; the eight hours of not-reading-them is the cost it imposes. Each
sharpening above is recorded in the check's own docstring together with the
false-positive families it removed, so the next person starts where this
finished rather than at 200 false positives.

### What it is known to miss

`fixtures/QF004/known-miss/` holds a real instance of Class 5 that quietfail
0.1.0 does not find: a backticked mention of a missing file. Including
backticked mentions gave 40 findings at roughly 40% precision, because a
mention is not a promise — the file may belong to the reader, may be
generated by the tool, may be the old name in a rename table, or may be
named by prose explicitly about its absence. The gap is on the record
instead of being quietly dropped, and `selftest` reports it every run.

**A recall gap you have written down is a different thing from a recall gap
you have not noticed.** Wherever the two directions traded off, this ruleset
chose false negatives.

---

## Verification of the numbers above

**30 of the 94 were checked by hand, one at a time** — every finding from
QF002, QF003, QF004 and QF006. QF007's 64 were verified by sample rather than
exhaustively, and this README says so rather than implying a rigour that was
not applied. The most useful of them:

- **A flag that exists only on the machine.** One installed unit runs its daemon
  with an extra mode argument. The committed unit does not have it — and carries
  a comment explaining how to add it. Someone followed the instructions on the
  live box and stopped there. Every test guarding that file reads the copy in git.
- **A careful guard, and the file three lines below it.** A personal finance
  script refuses, loudly, to overwrite a monthly snapshot — it prints *"this is
  the only memory of that month"* and stops. Three lines later it writes an index
  built from a `glob`, with no guard at all. If that directory is ever missing,
  the index quietly becomes empty.
- **A test step that has never tested anything.** One repository's build workflow
  runs `pytest tests/ --cov=src` on every push. That repository has no `tests/`
  directory. The step has been collecting nothing, reporting coverage on nothing,
  and passing for as long as the file has existed.

Hand-checking also killed a finding: one script looked like a Class 4 instance
and is not — it calls `sys.exit(1)` when its source directory is absent, so it
refuses rather than serialising. The check was right and the first read of it
was wrong.

### The control caught the author

Mid-development, a narrowing to QF007 broke its own promise-catch fixture. The
scan did not report a smaller number. It reported:

```
  QF007  swallowed-error   UNINTERPRETABLE
         positive control failed -- failed to recover planted instance(s):
         promise-catch. Count withheld.
```

Two hundred findings withheld, on a bug that was sixty seconds old. That is the
entire thesis of this tool, and it fired on its own author before it fired on
anyone else.

---

## Exit codes

| code | meaning |
|---|---|
| 0 | every check ran under a passing control and found nothing |
| 1 | findings |
| 2 | at least one check is uninterpretable — **you do not have a number** |

Exit 2 is the one to wire into CI. A check that cannot run is not a check
that passed.

---

## Commands

```
quietfail scan [PATHS...]      # scan and return a number
quietfail scan --by-repo       # rank projects by how many findings each carries
quietfail selftest             # run every check against its planted fixtures
quietfail explain QF007        # what a check looks for, and what it does not
```

`scan` takes `--json` (machine-readable, includes the ruleset hash so a number
is reproducible against a stated ruleset), `--check QF002` to run one, `-v` to
show the triggering line, `--quiet` for the summary alone, `--exclude GLOB` to
skip a tree, and `--no-control` to skip the positive controls, which it will
complain about.

Generated files are skipped without being asked: lockfiles, vendored trees, and
directories whose names mark them as mirrors of code from somewhere else.

---

## Provenance

The eight checks come from a taxonomy written out of real outages in one
autonomous agent estate — 82 repositories, a scheduler, seventeen systemd
timers, and about six weeks of a pipeline re-running finished work while every
surface reported healthy. One class in that taxonomy is still prose: test rot,
where a test encodes a fact that was true when written and keeps passing while
asserting something else. It needs a registry concept that is not yet
mechanical.

MIT licensed. Issues and instances welcome — an instance that breaks a check
is worth more than a feature request.
