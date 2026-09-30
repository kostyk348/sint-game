"""Runtime cache directory (intent/prose caches). Gitignored. Override with SINTGAME_CACHE."""
import os


def dir_():
    d = os.environ.get("SINTGAME_CACHE") or os.path.join(os.getcwd(), ".sintgame")
    os.makedirs(d, exist_ok=True)
    return d


def path(name):
    return os.path.join(dir_(), name)
