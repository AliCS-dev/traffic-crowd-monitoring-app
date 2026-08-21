from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.database.output_asset_repository import (
    OutputAssetRecord,
    get_output_asset,
)

CONTENT_TYPE_BY_SUFFIX = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
}


class OutputAssetNotFoundError(LookupError):
    """Raised when an output asset identifier is not stored."""


class OutputAssetUnavailableError(LookupError):
    """Raised when a stored output asset cannot be served safely."""


@dataclass(frozen=True)
class ResolvedOutputAsset:
    asset_id: UUID
    file_path: Path
    content_type: str


class OutputAssetService:
    def __init__(
        self,
        *,
        allowed_directories: Iterable[Path],
        asset_reader: Callable[[UUID], OutputAssetRecord | None] = get_output_asset,
    ) -> None:
        self._allowed_directories = tuple(
            Path(directory).resolve() for directory in allowed_directories
        )
        if not self._allowed_directories:
            raise ValueError("At least one output asset directory is required.")
        self._asset_reader = asset_reader

    def resolve(self, asset_id: UUID) -> ResolvedOutputAsset:
        record = self._asset_reader(asset_id)
        if record is None:
            raise OutputAssetNotFoundError("Output asset not found.")

        resolved_path = record.file_path.resolve()
        if not any(
            resolved_path.is_relative_to(directory)
            for directory in self._allowed_directories
        ):
            raise OutputAssetUnavailableError("Output asset is unavailable.")

        content_type = CONTENT_TYPE_BY_SUFFIX.get(resolved_path.suffix.lower())
        if content_type is None or not resolved_path.is_file():
            raise OutputAssetUnavailableError("Output asset is unavailable.")

        return ResolvedOutputAsset(
            asset_id=record.asset_id,
            file_path=resolved_path,
            content_type=content_type,
        )
