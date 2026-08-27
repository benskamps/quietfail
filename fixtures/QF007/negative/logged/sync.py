import logging
import shutil

log = logging.getLogger(__name__)


def mirror(src, dst):
    try:
        shutil.copytree(src, dst)
    except Exception:
        log.warning("mirror failed: %s -> %s", src, dst, exc_info=True)
