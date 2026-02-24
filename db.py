import sqlite3
import os
from typing import Optional, Tuple


DB_PATH = os.path.join(os.path.dirname(__file__), 'app.db')


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                preferences_json TEXT,
                is_premium INTEGER NOT NULL DEFAULT 0,
                api_key TEXT,
                api_key_last_generated_at TEXT,
                daily_api_key_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        # Migrations for existing DBs
        try:
            conn.execute("ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'")
        except: pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN preferences_json TEXT")
        except: pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN api_key TEXT")
        except: pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN api_key_last_generated_at TEXT")
        except: pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN daily_api_key_count INTEGER NOT NULL DEFAULT 0")
        except: pass
        
        conn.commit()
    finally:
        conn.close()


def create_user(username: str, password_hash: str, plan: str = 'free', is_premium: bool = False) -> Tuple[bool, Optional[str]]:
    try:
        conn = get_connection()
        with conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, plan, is_premium) VALUES (?, ?, ?, ?)",
                (username, password_hash, plan, 1 if is_premium else 0),
            )
        return True, None
    except sqlite3.IntegrityError as e:
        return False, "username already exists"
    except Exception as e:
        return False, str(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def find_user_by_username(username: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        return row
    finally:
        conn.close()


def find_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return row
    finally:
        conn.close()


def update_user_preferences(user_id: int, preferences_json: str) -> bool:
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE users SET preferences_json = ? WHERE id = ?",
                (preferences_json, user_id)
            )
        return True
    except Exception:
        return False
    finally:
        conn.close()

def update_user_api_key(user_id: int, api_key: str) -> bool:
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE users SET api_key = ? WHERE id = ?",
                (api_key, user_id)
            )
        return True
    except Exception:
        return False
    finally:
        conn.close()

def update_user_api_key_with_quota(user_id: int, api_key: str, last_date: str, count: int) -> bool:
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE users SET api_key = ?, api_key_last_generated_at = ?, daily_api_key_count = ? WHERE id = ?",
                (api_key, last_date, count, user_id)
            )
        return True
    except Exception:
        return False
    finally:
        conn.close()
