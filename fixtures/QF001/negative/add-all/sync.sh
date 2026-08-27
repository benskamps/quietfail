#!/usr/bin/env bash
# Work set is "everything that changed". Empty genuinely means nothing changed.
git add -A
git commit -m "trail" || true
