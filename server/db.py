"""
Lightweight MySQL access helpers built on PyMySQL.
- get_conn(): create a connection using env variables
- query / execute / executemany: convenience wrappers returning dict rows
"""
import os
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv

load_dotenv()


def _cfg():
    return dict(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "bs_user"),
        password=os.getenv("DB_PASSWORD", "bs_pass_123"),
        database=os.getenv("DB_NAME", "bs_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def get_conn():
    return pymysql.connect(**_cfg())


@contextmanager
def dict_cursor():
    """Context manager yielding (conn, cursor) with rollback on error."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql, args=None, many=False):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchall()


def execute(sql, args=None):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.lastrowid


def executemany(sql, rows):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
