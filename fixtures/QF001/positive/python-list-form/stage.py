import subprocess

def stage(sector):
    subprocess.run(["git", "add", "report-*.json"], check=True)
    subprocess.run(["git", "commit", "-m", "reports"], check=False)
