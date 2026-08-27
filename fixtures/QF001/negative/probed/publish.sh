#!/usr/bin/env bash
git add "report-*.json"
if git diff --cached --quiet; then
  echo "nothing staged -- pattern matched no reports" >&2
  exit 3
fi
git commit -m receipts
