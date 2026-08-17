from contextlib import contextmanager

from app.database.connection import check_database_connection


def test_connection_check_forwards_an_optional_timeout(monkeypatch):
    received_options = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement):
            assert statement == "SELECT 1"

        def fetchone(self):
            return (1,)

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connection_factory(**options):
        received_options.append(options)
        yield Connection()

    monkeypatch.setattr(
        "app.database.connection.open_database_connection", connection_factory
    )

    assert check_database_connection(connect_timeout=3) is True
    assert received_options == [{"connect_timeout": 3}]
