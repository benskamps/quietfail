import json


def load(path):
    data = {}
    try:
        data = json.load(open(path))
    except:
        pass
    return data
