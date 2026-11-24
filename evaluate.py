from datetime import datetime
from pathlib import Path

from sklearn.metrics.pairwise import cosine_similarity

from app.db import get_connection
from app.nlp import NOISE_WORDS, Knowledge, QueryParser, clean_text
from app.search import MIN_SCORE, SearchEngine

EXCEL_F = "Excel Fundamentals"
EXCEL_P = "Excel Pivot Tables and Dashboards"
PY_BEG = "Python for Beginners"
PY_PD = "Python Data Analysis with Pandas"
SQL_B = "SQL Basics"
SQL_A = "Advanced SQL and Query Optimization"
PBI = "Power BI Essentials"
COMM = "Communication Skills at Work"
PM = "Project Management Basics"
ML = "Machine Learning Foundations"
MKT = "Digital Marketing Essentials"
SEC = "Cyber Security Awareness"

# (query, acceptable course titles)
CASES = [
    ("something to get better at pivot tables", {EXCEL_P}),
    ("pivot tabel tutorial", {EXCEL_P}),
    ("I want to lern pyhton", {PY_BEG, PY_PD}),
    ("spreadsheet help", {EXCEL_F, EXCEL_P}),
    ("intro to excel", {EXCEL_F}),
    ("show beginner sql lessons", {SQL_B}),
    ("advanced sql", {SQL_A}),
    ("window functions and indexes", {SQL_A}),
    ("how do I build dashboards in power bi", {PBI}),
    ("make charts and reports", {PBI, EXCEL_F, EXCEL_P}),
    ("clean messy data with pandas", {PY_PD}),
    ("learn coding", {PY_BEG, PY_PD}),
    ("how to write better emails", {COMM}),
    ("plan a project timeline", {PM}),
    ("predict things with ml", {ML}),
    ("what is regression", {ML}),
    ("spot phishing and protect my password", {SEC}),
    ("protect company data online", {SEC}),
]
NO_MATCH = ["cooking recipes", "learn guitar", "football scores"]


# ----------------------------------------------------------------- methods
def keyword_only(engine, query):
    tokens = {t for t in clean_text(query).split() if t not in NOISE_WORDS}
    scored = []
    for course in engine.courses:
        words = set(course["doc"].split())
        score = sum(1 for t in tokens if t in words or t.rstrip("s") in words)
        if score:
            scored.append((score, course["title"]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [title for _, title in scored]


def tfidf_only(engine, query):
    text = clean_text(query)
    if not text:
        return []
    sims = cosine_similarity(engine.course_vec.transform([text]), engine.course_matrix)[0]
    ranked = sorted(
        ((s, c["title"]) for s, c in zip(sims, engine.courses) if s >= MIN_SCORE),
        key=lambda item: (-item[0], item[1]))
    return [title for _, title in ranked]


def full_pipeline(parser, engine, conn, query):
    parsed = parser.parse(query)
    if parsed.intent == "unsupported":
        return []
    return [c["title"] for c in engine.search(conn, parsed)["courses"]]


# ----------------------------------------------------------------- scoring
def first_rank(ranked, expected):
    for position, title in enumerate(ranked, 1):
        if title in expected:
            return position
    return None


def summarize(ranks):
    n = len(ranks)
    hit1 = sum(1 for r in ranks if r == 1) / n
    hit3 = sum(1 for r in ranks if r and r <= 3) / n
    mrr = sum(1 / r for r in ranks if r) / n
    return hit1, hit3, mrr


def main():
    conn = get_connection()
    try:
        parser = QueryParser(Knowledge.from_db(conn))
        engine = SearchEngine.from_db(conn)

        methods = {
            "Keyword-only": lambda q: keyword_only(engine, q),
            "TF-IDF only": lambda q: tfidf_only(engine, q),
            "Full pipeline search": lambda q: full_pipeline(parser, engine, conn, q),
        }

        ranks = {name: [] for name in methods}
        rows = []
        for query, expected in CASES:
            row = [query]
            for name, run in methods.items():
                ranked = run(query)
                rank = first_rank(ranked, expected)
                ranks[name].append(rank)
                top = ranked[0] if ranked else "(none)"
                row.append(("OK " if rank == 1 else "MISS ") + top)
            rows.append(row)

        rejection = {}
        for name, run in methods.items():
            correct = sum(1 for q in NO_MATCH if not run(q))
            rejection[name] = f"{correct}/{len(NO_MATCH)}"
    finally:
        conn.close()

    names = list(methods)
    lines = [
        "# Search quality evaluation", "",
        f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "",
        f"{len(CASES)} labelled queries that should match a course, "
        f"{len(NO_MATCH)} that should match nothing. No API calls are used.", "",
        "## Summary", "",
        "| Method | Hit@1 | Hit@3 | MRR | No-match handled |",
        "|---|---|---|---|---|",
    ]
    for name in names:
        h1, h3, mrr = summarize(ranks[name])
        lines.append(f"| {name} | {h1:.0%} | {h3:.0%} | {mrr:.2f} | {rejection[name]} |")
    lines += ["", "Hit@1: the top result is an acceptable course. "
              "Hit@3: one appears in the top 3. MRR: mean of 1/rank of the first "
              "acceptable course. No-match handled: the method returned nothing.",
              "", "## Top result per query", "",
              "| Query | " + " | ".join(names) + " |",
              "|---|" + "---|" * len(names)]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "/") for cell in row) + " |")
    lines += ["", "## Notes", "",
              "- Small hand-made test set written by the project author; it shows "
              "relative improvement, not a general accuracy claim.",
              "- The NLP rules (typos, synonyms) were built from the same course "
              "catalog, so scores on this set are optimistic."]
    text = "\n".join(lines) + "\n"

    out = Path("docs") / "evaluation.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()