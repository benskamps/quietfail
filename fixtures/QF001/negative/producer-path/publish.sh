#!/usr/bin/env bash
# Takes the path the producer PRINTS, so it cannot drift out of sync.
REPORT="$(python3 run_report.py --print-path)"
git add "$REPORT"
git commit -m "report: $REPORT"
