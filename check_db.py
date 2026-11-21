import sqlite3

conn = sqlite3.connect("data/lms.db")
rows = conn.execute(
    "SELECT name FROM sqlite_master "
    "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
).fetchall()
for (name,) in rows:
    print(name)
conn.close()