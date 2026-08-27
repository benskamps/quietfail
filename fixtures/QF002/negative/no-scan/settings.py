import json


def write_defaults(path):
    with open(path, "w") as fh:
        json.dump({"theme": "dark", "retries": 3}, fh)
