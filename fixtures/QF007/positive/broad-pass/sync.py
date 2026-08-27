import shutil


def mirror(src, dst):
    try:
        shutil.copytree(src, dst)
    except Exception:
        pass
