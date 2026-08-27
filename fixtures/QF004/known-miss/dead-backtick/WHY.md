A backticked mention of a missing file IS a real instance of Class 5, and
quietfail 0.1.0 does not find it.

Measured on 82 repos: including backticked mentions gave 40 findings at
roughly 40% precision, because a mention is not a promise that the file
lives in this repo. Four false-positive families, all the same mistake --
reader-owned files, tool-generated files, rename tables naming the old
name, and prose explicitly about a file's absence.

This case stays here so the gap is on the record. If a future ruleset can
separate a mention-that-promises from a mention-that-describes, promote it
back to positive/.
