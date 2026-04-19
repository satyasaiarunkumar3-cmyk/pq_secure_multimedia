import sqlite3

DB_NAME = "db.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()

    # ---------- USERS ---------- #
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT
    )
    """)

    # ---------- OQS KEYS ---------- #
    db.execute("""
    CREATE TABLE IF NOT EXISTS keys (
        username TEXT PRIMARY KEY,
        public_key TEXT,
        private_key TEXT
    )
    """)

    # ---------- MESSAGES ---------- #
    db.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        receiver TEXT,
        ciphertext TEXT,
        file TEXT,
        timestamp TEXT,
        kem_ct TEXT,
        seen INTEGER DEFAULT 0,
        deleted_for_everyone INTEGER DEFAULT 0
    )
    """)

    db.commit()

    # ---------- SAFE MIGRATION ---------- #
    columns = [row["name"] for row in db.execute("PRAGMA table_info(messages)")]

    def add_column(name, sql):
        if name not in columns:
            print(f"Adding column: {name}")
            db.execute(sql)

    add_column("ciphertext", "ALTER TABLE messages ADD COLUMN ciphertext TEXT")
    add_column("file", "ALTER TABLE messages ADD COLUMN file TEXT")
    add_column("timestamp", "ALTER TABLE messages ADD COLUMN timestamp TEXT")
    add_column("kem_ct", "ALTER TABLE messages ADD COLUMN kem_ct TEXT")
    add_column("seen", "ALTER TABLE messages ADD COLUMN seen INTEGER DEFAULT 0")
    add_column("deleted_for_everyone", "ALTER TABLE messages ADD COLUMN deleted_for_everyone INTEGER DEFAULT 0")

    db.commit()

    # ---------- INDEX (PERFORMANCE BOOST) ---------- #
    db.execute("CREATE INDEX IF NOT EXISTS idx_chat ON messages(sender, receiver)")
    db.commit()

    db.close()
