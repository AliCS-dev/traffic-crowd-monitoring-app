import math
from pathlib import Path
from time import time
from uuid import UUID

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".mp4", ".avi", ".mov", ".mkv", ".part"}


def collect_expired_media(roots, referenced_paths, *, older_than_days=7, now=None):
    if not math.isfinite(older_than_days) or older_than_days < 1:
        raise ValueError("Retention must be at least one day.")
    cutoff = (time() if now is None else now) - older_than_days * 86400
    # Protect IDs as well as full paths when a database came from a container backup.
    retained_ids = {Path(path).stem.lstrip(".") for path in referenced_paths}
    candidates = []
    for root in roots:
        root = Path(root).absolute()
        if root.resolve() != root:
            raise ValueError("Cleanup roots must not contain symbolic links.")
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            stem = path.stem.lstrip(".")
            if (
                path.is_symlink()
                or not path.is_file()
                or path.suffix not in ALLOWED_SUFFIXES
            ):
                continue
            try:
                if str(UUID(stem)) != stem:
                    continue
            except ValueError:
                continue
            if stem not in retained_ids and path.stat().st_mtime < cutoff:
                candidates.append(path)
    return candidates
