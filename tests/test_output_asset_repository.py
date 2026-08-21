from uuid import UUID

from app.database.output_asset_repository import get_output_asset

ASSET_ID = UUID("12345678-1234-5678-1234-567812345678")


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.execute_call = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, parameters):
        self.execute_call = (" ".join(query.split()), parameters)

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor):
        self.query_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self, **_options):
        return self.query_cursor


def test_output_asset_is_read_by_opaque_identifier():
    cursor = FakeCursor(
        {
            "output_asset_id": ASSET_ID,
            "output_file_path": "data/output/analyses/result.jpg",
        }
    )

    result = get_output_asset(
        ASSET_ID,
        connection_factory=lambda: FakeConnection(cursor),
    )

    assert result.asset_id == ASSET_ID
    assert str(result.file_path) == "data/output/analyses/result.jpg"
    assert "WHERE output_asset_id = %s" in cursor.execute_call[0]
    assert cursor.execute_call[1] == (ASSET_ID,)
