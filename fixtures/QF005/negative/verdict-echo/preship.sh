#!/usr/bin/env bash
# Printing a verdict is the opposite of discarding one. Also: the word
# "available" contains "ava", which is a test runner.
[[ "$PYTEST_OK" -eq 1 ]] && echo "  pytest   PASS" || echo "  pytest   FAIL"
python3 -m venv venv 2>/dev/null || echo "  (venv not available, using system python)"
