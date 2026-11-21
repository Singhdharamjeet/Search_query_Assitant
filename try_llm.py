import json
import os

from app.db import get_connection
from app.guardrails import LLMValidationError, get_allowed_values, validate_llm_output
from app.llm_client import (GeminiProvider, LLMConfigError, MockProvider,
                            build_user_prompt, load_system_prompt)
from app.nlp import Knowledge, QueryParser
from app.search import SearchEngine
from app.validation import validate_query

QUERY = "something to get better at pivot tables"


def run(provider, system_prompt, user_prompt, search_result, allowed):
    call = provider.generate(system_prompt, user_prompt)
    print(f"  provider={call.provider} model={call.model} status={call.status} "
          f"latency={call.latency_ms}ms tokens={call.input_tokens}/{call.output_tokens}")
    if call.status != "success":
        print(f"  -> API problem: {call.error_message}  => FALL BACK to NLP-only results")
        return
    try:
        clean, issues = validate_llm_output(call.raw_text, search_result, allowed)
    except LLMValidationError as exc:
        print(f"  -> INVALID RESPONSE: {exc}  => FALL BACK to NLP-only results")
        return
    print(f"  issues={issues}")
    print("  validated output:")
    print("  " + json.dumps(clean, indent=2).replace("\n", "\n  "))


def main():
    conn = get_connection()
    try:
        parser = QueryParser(Knowledge.from_db(conn))
        engine = SearchEngine.from_db(conn)
        parsed = parser.parse(validate_query(QUERY))
        result = engine.search(conn, parsed)
        allowed = get_allowed_values(conn)
    finally:
        conn.close()

    system_prompt = load_system_prompt()
    user_prompt = build_user_prompt(QUERY, parsed.to_dict(), result, allowed)

    top_course = result["courses"][0]["course_id"]
    top_lesson = result["lessons"][0]["lesson_id"]
    good = json.dumps({
        "rewritten_query": "learn pivot tables in Excel",
        "intent": "find_course",
        "suggested_filters": [
            {"field": "category", "value": "spreadsheets", "reason": "Pivot tables are a spreadsheet feature."},
            {"field": "level", "value": "expert", "reason": "Invented level."}],
        "selected_course_ids": [top_course, 999],
        "selected_lesson_ids": [top_lesson],
        "needs_clarification": False, "clarifying_question": None,
        "confidence": 0.9, "explanation": "Direct topic match."})

    print("\n[1] MOCK: good response with one invented ID and one invalid filter")
    run(MockProvider("ok", good), system_prompt, user_prompt, result, allowed)
    print("\n[2] MOCK: malformed (non-JSON) response")
    run(MockProvider("malformed"), system_prompt, user_prompt, result, allowed)
    print("\n[3] MOCK: simulated timeout")
    run(MockProvider("timeout"), system_prompt, user_prompt, result, allowed)

    print("\n[4] REAL API CALL")
    if os.getenv("LLM_PROVIDER", "gemini").lower() != "gemini":
        print("  Skipped: LLM_PROVIDER is not 'gemini'.")
        return
    try:
        run(GeminiProvider(), system_prompt, user_prompt, result, allowed)
    except LLMConfigError as exc:
        print(f"  Skipped: {exc}")


if __name__ == "__main__":
    main()