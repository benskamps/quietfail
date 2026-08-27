import json
from pathlib import Path


def main(plans_dir, out):
    plans = sorted(Path(plans_dir).glob("plan-*.pdf"))
    if not plans:
        raise SystemExit("no plans found: refusing to write a result set")
    results = [evaluate(p) for p in plans]
    with open(out, "w") as fh:
        json.dump({"results": results, "total": len(results)}, fh)


def evaluate(path):
    return {"path": str(path), "score": 1.0}
