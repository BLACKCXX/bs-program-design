"""
超轻量 MySQL 访问层：不使用 ORM，只用 PyMySQL。
- get_conn(): 每次请求时创建连接（pool 可后续替换）
- dict_cursor: 返回 dict 行，便于 jsonify
"""
import os
import pymysql
from contextlib import contextmanager

def _cfg():
    return dict(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "bs_user"),
        password=os.getenv("DB_PASSWORD", "bs_pass_123"),
        database=os.getenv("DB_NAME", "bs_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,  # 显式提交，保证事务性
    )

def get_conn():
    return pymysql.connect(**_cfg())

@contextmanager
def dict_cursor():
    """with dict_cursor() as cur: 既拿 cursor 也拿 conn，出错自动回滚"""
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
