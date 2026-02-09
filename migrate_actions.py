import sqlite3

def main():
    conn = sqlite3.connect('data/bot.db')
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS bots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        token TEXT,
        enabled INTEGER DEFAULT 1,
        heartbeat TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()
    print("\u2705 Migration actions completed")

if __name__ == '__main__':
    main()
