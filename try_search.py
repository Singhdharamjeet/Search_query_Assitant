from app.db import get_connection
from app.nlp import Knowledge, QueryParser
from app.search import SearchEngine
from app.validation import ValidationError, validate_query

TEST_QUERIES = [
    "something to get better at pivot tables",
    "I want to lern pyhton",
    "spreadsheet help",
    "show beginner sql lessons",
    "how do I build dashboards in power bi",
    "advanced python",
    "cooking recipes",
    "issue my certificate",
    "xyz",
]


def main():
    conn = get_connection()
    try:
        parser = QueryParser(Knowledge.from_db(conn))
        engine = SearchEngine.from_db(conn)

        for raw in TEST_QUERIES:
            print("=" * 70)
            print(f"INPUT: {raw!r}")
            try:
                parsed = parser.parse(validate_query(raw))
            except ValidationError as exc:
                print(f"REJECTED: {exc}")
                continue

            print(f"intent={parsed.intent}  confidence={parsed.confidence}")
            if parsed.intent == "unsupported":
                print("-> Not searched (unsupported request).")
                continue

            result = engine.search(conn, parsed)
            print(f"query_text={result['query_text']!r}  filters={result['filters']}")
            if result["no_match"]:
                print("-> NO MATCH in the LMS dataset.")
                continue

            print("Courses:")
            for c in result["courses"]:
                print(f"  [{c['score']:.2f}] #{c['course_id']} {c['title']} "
                      f"({c['level']}) - {c['reason']}")
            print("Lessons:")
            for l in result["lessons"]:
                print(f"  [{l['score']:.2f}] #{l['lesson_id']} {l['title']} "
                      f"(in {l['course_title']})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()