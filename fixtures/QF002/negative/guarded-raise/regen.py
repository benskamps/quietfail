import glob
import json
import sys


def main(allow_partial=False):
    repos = glob.glob("sources/*/")
    if not repos and not allow_partial:
        sys.exit(2)
    with open("index.json", "w") as fh:
        json.dump({"repos": repos}, fh)
