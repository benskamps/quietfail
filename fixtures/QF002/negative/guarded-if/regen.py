import glob
import json


def main():
    repos = glob.glob("sources/*/")
    if repos:
        with open("index.json", "w") as fh:
            json.dump({"repos": repos}, fh)
