import glob
import json


def main():
    repos = glob.glob("sources/*/")
    assert repos, "empty scan: refusing to serialise over the real index"
    with open("index.json", "w") as fh:
        json.dump({"repos": repos}, fh)
