import sqlite3

conn = sqlite3.connect("data/lms.db")

print("Row counts:")
for table in ["learners", "courses", "lessons", "synonyms", "audit_log"]:
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {count}")

print("\nLessons per course:")
rows = conn.execute(
    "SELECT c.course_id, c.title, COUNT(l.lesson_id) "
    "FROM courses c LEFT JOIN lessons l ON l.course_id = c.course_id "
    "GROUP BY c.course_id ORDER BY c.course_id"
).fetchall()
for course_id, title, n in rows:
    print(f"  {course_id}. {title} -> {n} lessons")

conn.close()