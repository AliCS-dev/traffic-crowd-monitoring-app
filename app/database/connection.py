import os

import psycopg
from dotenv import load_dotenv


def get_database_url():
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

    return database_url


def open_database_connection():
    return psycopg.connect(get_database_url())


def check_database_connection():
    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

    return result == (1,)
