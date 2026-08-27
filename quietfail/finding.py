"""Findings and check results.

A check never returns a bare list. It returns a Result, which carries the
distinction this whole tool exists to preserve:

    CLEAN            — the check ran, its positive control passed, it found nothing
    FINDINGS         — the check ran, its positive control passed, here is what it found
    UNINTERPRETABLE  — the check could not run, or could not recover its own
                       planted instances. Its count is WITHHELD, not zeroed.

Reporting 0 for an instrument you have not demonstrated is the bug this tool
is named after.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional

CLEAN = "clean"
FINDINGS = "findings"
UNINTERPRETABLE = "uninterpretable"


@dataclass(frozen=True)
class Finding:
    check: str          # "QF001"
    path: str           # absolute path
    line: int           # 1-indexed; 0 when the finding is about a file as a whole
    message: str        # what is wrong, in one line
    evidence: str = ""  # the literal text that triggered it

    def as_dict(self):
        return asdict(self)

    def location(self):
        return "%s:%d" % (self.path, self.line) if self.line else self.path


@dataclass
class Result:
    check: str
    status: str = CLEAN
    findings: List[Finding] = field(default_factory=list)
    note: Optional[str] = None      # why uninterpretable, or a scope caveat
    files_examined: int = 0

    @classmethod
    def of(cls, check, findings, files_examined=0):
        findings = list(findings)
        return cls(
            check=check,
            status=FINDINGS if findings else CLEAN,
            findings=findings,
            files_examined=files_examined,
        )

    @classmethod
    def withheld(cls, check, note):
        return cls(check=check, status=UNINTERPRETABLE, note=note)

    @property
    def count(self):
        """None, not 0, when the number is not interpretable."""
        return None if self.status == UNINTERPRETABLE else len(self.findings)

    def as_dict(self):
        return {
            "check": self.check,
            "status": self.status,
            "count": self.count,
            "note": self.note,
            "files_examined": self.files_examined,
            "findings": [f.as_dict() for f in self.findings],
        }
