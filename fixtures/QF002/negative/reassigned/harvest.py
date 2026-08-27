"""Taint must not survive across functions that share a local name.

`content` holds a scan in digest() -- guarded there -- and holds a template
in readme(). Flow-insensitive, cross-scope taint reported readme() as a
destructive generator, which it is not.
"""

import glob
from pathlib import Path


def digest(folder):
    found = glob.glob(folder + "/*.md")
    if not found:
        raise SystemExit("empty scan: refusing to write an empty digest")
    content = "\n".join(found)
    Path("digest.md").write_text(content)


def readme(vault, folder, desc):
    # Same local name, different function, no scan behind it.
    content = f"""# {folder}

{desc}
"""
    (Path(vault) / folder / "README.md").write_text(content)
