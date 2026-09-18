"""List or remove expired unreferenced media while every API instance is stopped."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.settings import ApiSettings
from app.database.maintenance import media_maintenance_snapshot
from app.services.media_cleanup_service import collect_expired_media


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--older-than-days", type=int, default=7)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    settings = ApiSettings.from_environment()
    roots = (
        settings.image_upload_directory,
        settings.image_output_directory,
        settings.video_upload_directory,
        settings.video_output_directory,
    )
    try:
        with media_maintenance_snapshot() as referenced:
            candidates = collect_expired_media(
                roots, referenced, older_than_days=arguments.older_than_days
            )
            total_bytes = sum(path.stat().st_size for path in candidates)
            if arguments.apply:
                for path in candidates:
                    if path.is_symlink():
                        raise RuntimeError(
                            "A cleanup candidate changed; no further files removed."
                        )
                    path.unlink()
            print(
                json.dumps(
                    {
                        "mode": "applied" if arguments.apply else "dry_run",
                        "files": [str(path) for path in candidates],
                        "bytes": total_bytes,
                    },
                    indent=2,
                )
            )
    except Exception:
        print(
            "Cleanup refused or failed. Check database availability, stop all "
            "API instances, and review retention settings. "
            "Saved results are never selected.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
