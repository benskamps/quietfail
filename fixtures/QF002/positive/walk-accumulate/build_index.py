import json
import os
from pathlib import Path


def build(root):
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            entries.append(os.path.join(dirpath, name))
    Path("index.json").write_text(json.dumps({"files": entries}))
