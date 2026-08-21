from uuid import UUID

import pytest

from app.database.output_asset_repository import OutputAssetRecord
from app.services.output_asset_service import (
    OutputAssetNotFoundError,
    OutputAssetService,
    OutputAssetUnavailableError,
)

ASSET_ID = UUID("12345678-1234-5678-1234-567812345678")


def create_service(output_directory, record):
    return OutputAssetService(
        allowed_directories=(output_directory,),
        asset_reader=lambda _asset_id: record,
    )


def test_stored_jpeg_inside_output_directory_is_resolved(tmp_path):
    output_directory = tmp_path / "outputs"
    output_directory.mkdir()
    output_path = output_directory / f"{ASSET_ID}.jpg"
    output_path.write_bytes(b"jpeg content")
    service = create_service(
        output_directory,
        OutputAssetRecord(asset_id=ASSET_ID, file_path=output_path),
    )

    result = service.resolve(ASSET_ID)

    assert result.asset_id == ASSET_ID
    assert result.file_path == output_path.resolve()
    assert result.content_type == "image/jpeg"


def test_unknown_asset_identifier_is_reported(tmp_path):
    service = create_service(tmp_path, None)

    with pytest.raises(OutputAssetNotFoundError, match="not found"):
        service.resolve(ASSET_ID)


@pytest.mark.parametrize("failure", ["outside", "missing", "unsupported", "symlink"])
def test_uncontrolled_or_unavailable_file_is_not_exposed(tmp_path, failure):
    output_directory = tmp_path / "outputs"
    output_directory.mkdir()
    outside_file = tmp_path / "private.jpg"
    outside_file.write_bytes(b"private")

    if failure == "outside":
        stored_path = outside_file
    elif failure == "missing":
        stored_path = output_directory / "missing.jpg"
    elif failure == "unsupported":
        stored_path = output_directory / "result.png"
        stored_path.write_bytes(b"unsupported result type")
    else:
        stored_path = output_directory / "linked.jpg"
        stored_path.symlink_to(outside_file)

    service = create_service(
        output_directory,
        OutputAssetRecord(asset_id=ASSET_ID, file_path=stored_path),
    )

    with pytest.raises(OutputAssetUnavailableError, match="unavailable"):
        service.resolve(ASSET_ID)
