import sqlite3

def main():
    conn = sqlite3.connect('data/bot.db')
    c = conn.cursor()
    # Create tg_users and tg_groups tables if not exist
    c.execute("""CREATE TABLE IF NOT EXISTS tg_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT UNIQUE,
        name TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tg_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id TEXT UNIQUE,
        name TEXT
    )""")
    # Create rules table if not exist
    c.execute("""CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER,
        action_type TEXT,
        source_group_id TEXT,
        target_group_id TEXT,
        user_id TEXT,
        user_ids TEXT,
        keyword TEXT,
        enabled INTEGER DEFAULT 1,
        append_text TEXT,
        merchant_regex TEXT,
        lookup_url TEXT,
        replace_template TEXT,
        reply_text TEXT
    )""")
    # Create logs table
    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        bot_id INTEGER,
        rule_id INTEGER,
        message_type TEXT,
        message_text TEXT
    )""")
    conn.commit()
    conn.close()
    print("migrate_v3 complete")

if __name__ == '__main__':
    main()
