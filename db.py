import sqlite3


def db_setup():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # cursor.execute('DROP TABLE IF EXISTS users')
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            timezone TEXT NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


def save_user(user_id: int, name: str, age: int, timezone: str):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, name, age, timezone) VALUES (?, ?, ?, ?)",
        (user_id, name, age, timezone),
    )
    conn.commit()
    conn.close()


def get_all_users():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()
    return users
