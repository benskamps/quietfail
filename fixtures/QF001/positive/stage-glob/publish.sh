#!/usr/bin/env bash
# Stages the day's receipts. The producer names them; this rebuilds the name.
set -euo pipefail
cd "$REPO"
git add "report-*-${REGION}.json"
git commit -m "receipts for sector ${REGION}" || true
git push
