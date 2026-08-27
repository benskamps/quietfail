import csv
import os


def report(src, out):
    rows = [(name, os.path.getsize(os.path.join(src, name))) for name in os.listdir(src)]
    with open(out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)
