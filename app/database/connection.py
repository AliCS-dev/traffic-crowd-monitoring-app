import os

import psycopg
from dotenv import load_dotenv


def get_database_url():
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

    return database_url


def open_database_connection(**connection_options):
    return psycopg.connect(get_database_url(), **connection_options)


def check_database_connection(*, connect_timeout=None):
    options = {}
    if connect_timeout is not None:
        options["connect_timeout"] = connect_timeout
    with open_database_connection(**options) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

    return result == (1,)
