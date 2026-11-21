import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

LEVELS = ["beginner", "intermediate", "advanced"]


class LLMValidationError(ValueError):
    """Raised when the model output is unusable (not JSON, or fails the schema)."""


class SuggestedFilter(BaseModel):
    field: Literal["level", "category"]
    value: str
    reason: str = Field(max_length=300)


class LLMOutput(BaseModel):
    rewritten_query: str = Field(min_length=1, max_length=200)
    intent: Literal["find_course", "find_lesson", "browse_topic", "unsupported", "unknown"]
    suggested_filters: list[SuggestedFilter] = []
    selected_course_ids: list[int] = []
    selected_lesson_ids: list[int] = []
    needs_clarification: bool = False
    clarifying_question: str | None = None
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(max_length=500)


def get_allowed_values(conn) -> dict:
    rows = conn.execute(
        "SELECT DISTINCT category FROM courses WHERE status = 'published' ORDER BY category"
    ).fetchall()
    return {"level": LEVELS, "category": [r[0] for r in rows]}


def _extract_json(raw_text: str) -> dict:
    if not raw_text or not raw_text.strip():
        raise LLMValidationError("Empty model response.")
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)   # strip code fences
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMValidationError("Response is not valid JSON.")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            raise LLMValidationError("Response is not valid JSON.")
    if not isinstance(data, dict):
        raise LLMValidationError("Response JSON must be an object.")
    return data


def validate_llm_output(raw_text: str, search_result: dict, allowed_values: dict):
    """Return (clean_output_dict, issues). Raise LLMValidationError if unusable.

    Anything not present in the candidate records or allowed values is dropped.
    """
    data = _extract_json(raw_text)
    try:
        out = LLMOutput.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise LLMValidationError(f"Schema check failed at '{loc}': {first['msg']}")

    issues = []
    course_ids = {c["course_id"] for c in search_result["courses"]}
    lesson_ids = {l["lesson_id"] for l in search_result["lessons"]}

    kept_courses = [i for i in dict.fromkeys(out.selected_course_ids) if i in course_ids]
    kept_lessons = [i for i in dict.fromkeys(out.selected_lesson_ids) if i in lesson_ids]
    dropped_c = set(out.selected_course_ids) - set(kept_courses)
    dropped_l = set(out.selected_lesson_ids) - set(kept_lessons)
    if dropped_c:
        issues.append(f"Dropped course IDs not in candidates: {sorted(dropped_c)}")
    if dropped_l:
        issues.append(f"Dropped lesson IDs not in candidates: {sorted(dropped_l)}")

    kept_filters = []
    for f in out.suggested_filters:
        valid = {v.lower(): v for v in allowed_values.get(f.field, [])}
        canonical = valid.get(f.value.strip().lower())
        if canonical:
            kept_filters.append({"field": f.field, "value": canonical, "reason": f.reason})
        else:
            issues.append(f"Dropped invalid filter: {f.field}={f.value!r}")

    clean = out.model_dump()
    clean["selected_course_ids"] = kept_courses[:3]
    clean["selected_lesson_ids"] = kept_lessons[:5]
    clean["suggested_filters"] = kept_filters

    if out.intent not in ("unsupported", "unknown") and not kept_courses and not kept_lessons:
        clean["needs_clarification"] = True
        issues.append("No valid records selected; clarification forced.")
    if clean["needs_clarification"] and not clean["clarifying_question"]:
        clean["clarifying_question"] = (
            "Could you tell me which topic or skill you want to learn?")
    return clean, issues