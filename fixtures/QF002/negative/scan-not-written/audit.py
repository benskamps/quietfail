import glob
import json


def main():
    found = glob.glob("*.log")
    for path in found:
        print(path)
    with open("config.json", "w") as fh:
        json.dump({"version": 3, "mode": "audit"}, fh)
