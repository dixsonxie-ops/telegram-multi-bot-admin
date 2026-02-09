import sqlite3

def main():
    conn = sqlite3.connect('data/bot.db')
    c = conn.cursor()
    # Create contacts table placeholder if needed
    c.execute("""CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        name TEXT
    )""")
    conn.commit()
    conn.close()
    print("migrate_contacts complete")

if __name__ == '__main__':
    main()
