#!/bin/sh
git rm --cached 'tmp-*.log'
git commit -m prune || true
