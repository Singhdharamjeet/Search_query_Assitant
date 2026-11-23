from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RECORDS = {}     
OUTCOMES = {}    
DOCS = {}        


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def test_db(tmp_path_factory):
    """A fresh database built from schema.sql and the CSV files."""
    import init_db
    import load_data

    db_path = tmp_path_factory.mktemp("db") / "test_lms.db"
    patch = pytest.MonkeyPatch()
    patch.setenv("DB_PATH", str(db_path))
    patch.setattr(load_data, "DB_PATH", db_path)
    init_db.init_db(db_path)
    load_data.load_all()
    yield db_path
    patch.undo()


@pytest.fixture
def conn(test_db):
    from app.db import get_connection
    connection = get_connection()
    yield connection
    connection.close()


@pytest.fixture
def make_assistant(test_db):
    from app.pipeline import SearchAssistant
    return lambda provider: SearchAssistant(provider=provider)


@pytest.fixture
def parser(conn):
    from app.nlp import Knowledge, QueryParser
    return QueryParser(Knowledge.from_db(conn))


@pytest.fixture
def engine(conn):
    from app.search import SearchEngine
    return SearchEngine.from_db(conn)


@pytest.fixture
def record(request):
    """Call record(input, expected, actual) so the report shows the evidence."""
    def _record(input_, expected, actual):
        RECORDS[request.node.name] = {
            "input": input_, "expected": expected, "actual": actual}
    return _record


# ---------------------------------------------------------------- report
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    doc = (getattr(item.function, "__doc__", "") or "").strip().splitlines()
    DOCS[item.name] = doc[0] if doc else item.name
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        OUTCOMES[item.name] = "PASS" if report.outcome == "passed" else "FAIL"


def _cell(value, limit=140):
    text = str(value).replace("|", "/").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit - 3] + "..."


def pytest_sessionfinish(session, exitstatus):
    if not OUTCOMES:
        return
    passed = sum(1 for v in OUTCOMES.values() if v == "PASS")
    failed = len(OUTCOMES) - passed
    lines = [
        "# Test report", "",
        f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "",
        f"**Result: {passed} passed, {failed} failed ({len(OUTCOMES)} total)**", "",
        "All tests use the offline MockProvider and a temporary SQLite database.", "",
        "| ID | Scenario | Input | Expected | Actual | Result |",
        "|---|---|---|---|---|---|",
    ]
    for name in sorted(OUTCOMES):
        parts = name.split("_")
        tc = parts[1].upper() if len(parts) > 1 else name
        if "[" in name:
            tc += name[name.index("["):]
        rec = RECORDS.get(name, {})
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            tc, _cell(DOCS.get(name, "")), _cell(rec.get("input", "")),
            _cell(rec.get("expected", "")), _cell(rec.get("actual", "")),
            OUTCOMES[name]))
    out = ROOT / "docs" / "test_report.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")