import glob
import json


def main():
    repos = glob.glob("sources/*/")
    index = {"repos": [{"path": r} for r in repos], "count": len(repos)}
    with open("index.json", "w") as fh:
        json.dump(index, fh)
    with open("sources/index.html") as fh:
        return fh.read()
