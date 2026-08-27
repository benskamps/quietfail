from .qf001_glob_workset import QF001
from .qf002_empty_scan import QF002
from .qf003_unit_drift import QF003
from .qf004_front_door import QF004
from .qf005_green_by_construction import QF005
from .qf006_suite_with_no_tests import QF006
from .qf007_swallowed_error import QF007
from .qf008_schedule_to_nowhere import QF008

ALL_CHECKS = [QF001, QF002, QF003, QF004, QF005, QF006, QF007, QF008]
BY_ID = {c.id: c for c in ALL_CHECKS}
