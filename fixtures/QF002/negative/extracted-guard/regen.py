import glob
import json
import sys


def corpus_preflight(repos):
    """Refuse rather than serialise an empty scan over the real index."""
    if not repos:
        sys.stderr.write("empty corpus: refusing to regenerate\n")
        sys.exit(2)


def main():
    repos = glob.glob("sources/*/")
    corpus_preflight(repos)
    with open("index.json", "w") as fh:
        json.dump({"repos": repos}, fh)
