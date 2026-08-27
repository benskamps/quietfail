import json


def read_cache(path):
    try:
        return json.load(open(path))
    except FileNotFoundError:
        pass
    return None
