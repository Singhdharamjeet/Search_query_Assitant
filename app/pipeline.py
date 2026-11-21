import json
import os

from app import repository as repo
from app.db import get_connection
from app.guardrails import LLMValidationError, get_allowed_values, validate_llm_output
from app.llm_client import (PROMPT_VERSION, LLMCallResult, LLMConfigError,
                            build_user_prompt, get_provider, load_system_prompt)
from app.nlp import Knowledge, QueryParser
from app.search import SearchEngine
from app.validation import ValidationError, validate_learner_id, validate_query

REVIEW_CONFIDENCE = 0.5     # below this, a human should look at the query
FALLBACK_COURSES = 3
FALLBACK_LESSONS = 5


class SearchAssistant:
    """Receive query -> NLP -> SQL + similarity -> LLM -> validate -> log."""

    def __init__(self, provider=None):
        conn = get_connection()
        try:
            self.parser = QueryParser(Knowledge.from_db(conn))
            self.engine = SearchEngine.from_db(conn)
            self.allowed = get_allowed_values(conn)
        finally:
            conn.close()
        self.system_prompt = load_system_prompt()

        self.provider = provider
        self.provider_error = None
        if provider is None:
            try:
                self.provider = get_provider()
            except (LLMConfigError, ImportError) as exc:
                self.provider_error = str(exc)    # app still works in fallback mode

    # ------------------------------------------------------------ public
    def run(self, query, learner_id=None) -> dict:
        conn = get_connection()          # one connection per request (thread-safe)
        try:
            return self._run(conn, query, learner_id)
        finally:
            conn.close()

    # ------------------------------------------------------------ pipeline
    def _run(self, conn, query, learner_id) -> dict:
        # 1. validate input
        try:
            clean = validate_query(query)
            learner = validate_learner_id(learner_id)
            if learner is not None and not repo.learner_exists(conn, learner):
                raise ValidationError("Learner not found or inactive.")
        except ValidationError as exc:
            raw = "" if query is None else str(query)[:500]
            qid = repo.create_query(conn, None, raw)
            repo.update_query(conn, qid, status="rejected")
            repo.add_audit(conn, "search_query", qid, "query_rejected", details=str(exc))
            return self._respond(qid, raw, "rejected", "rejected", str(exc))

        qid = repo.create_query(conn, learner, clean)
        repo.add_audit(conn, "search_query", qid, "query_received",
                       actor=f"learner:{learner}" if learner else "anonymous")

        # 2. NLP parsing and expansion
        parsed = self.parser.parse(clean)
        repo.update_query(
            conn, qid, cleaned_query=parsed.cleaned_query, intent=parsed.intent,
            entities_json=json.dumps(parsed.entities), confidence=parsed.confidence,
            status="parsed")
        summary = self._parsed_summary(parsed)

        # 3. unsupported / consequential request -> human review, no action
        if parsed.intent == "unsupported":
            repo.update_query(conn, qid, status="needs_review")
            repo.add_audit(conn, "search_query", qid, "unsupported_request_flagged",
                           details=" ".join(parsed.notes))
            return self._respond(
                qid, clean, "needs_review", "unsupported",
                "This request needs a trainer or administrator. It has been logged "
                "for review and nothing was changed.",
                parsed=summary, notes=parsed.notes)

        # 4. SQL filter + TF-IDF similarity search
        result = self.engine.search(conn, parsed)
        repo.save_results(conn, qid, result["courses"], result["lessons"], "tfidf")
        repo.update_query(conn, qid, status="searched")
        notes = list(parsed.notes)
        if result["filters"]["level_filter_relaxed"]:
            notes.append("No course matched that level, so the level filter was relaxed.")

        # 5. LLM rewrite / explanation / clarification
        call, validated, issues, final_status, error = self._call_llm(
            conn, qid, clean, parsed, result)
        llm_info = {
            "provider": call.provider, "model": call.model, "status": final_status,
            "latency_ms": call.latency_ms, "tokens_in": call.input_tokens,
            "tokens_out": call.output_tokens, "issues": issues, "error": error,
        }

        # 6a. validated LLM answer
        if validated:
            cmap = {c["course_id"]: c for c in result["courses"]}
            lmap = {l["lesson_id"]: l for l in result["lessons"]}
            courses = [cmap[i] for i in validated["selected_course_ids"]]
            lessons = [lmap[i] for i in validated["selected_lesson_ids"]]
            repo.update_query(conn, qid, status="llm_done")
            repo.save_results(conn, qid, courses, lessons, "llm")

            low = validated["confidence"] < REVIEW_CONFIDENCE
            status = "needs_review" if low else "completed"
            repo.update_query(conn, qid, status=status)
            if low:
                repo.add_audit(conn, "search_query", qid, "review_requested",
                               details=f"LLM confidence {validated['confidence']}")
            asking = validated["needs_clarification"] and validated["clarifying_question"]
            return self._respond(
                qid, clean, status, "llm",
                validated["clarifying_question"] if asking else validated["explanation"],
                parsed=summary, rewritten_query=validated["rewritten_query"],
                suggested_filters=validated["suggested_filters"],
                explanation=validated["explanation"],
                clarifying_question=validated["clarifying_question"],
                courses=courses, lessons=lessons, llm=llm_info, notes=notes)

        # 6b. fallback: NLP-only results
        courses = result["courses"][:FALLBACK_COURSES]
        lessons = result["lessons"][:FALLBACK_LESSONS]
        repo.save_results(conn, qid, courses, lessons, "fallback")
        repo.update_query(conn, qid, status="llm_failed")
        repo.add_audit(conn, "search_query", qid, "llm_fallback", details=error)
        if result["no_match"]:
            message = ("No matching courses or lessons were found in the LMS. "
                       "Try a topic such as Excel, Python or SQL.")
            clarifying = "Which topic would you like to learn?"
        else:
            message = ("The AI assistant is unavailable, so these are "
                       "keyword-based matches from the LMS.")
            clarifying = None
        return self._respond(
            qid, clean, "llm_failed", "fallback", message, parsed=summary,
            rewritten_query=parsed.expanded_query or None,
            clarifying_question=clarifying, courses=courses, lessons=lessons,
            llm=llm_info, notes=notes)

    # ------------------------------------------------------------ helpers
    def _call_llm(self, conn, qid, clean, parsed, result):
        user_prompt = build_user_prompt(clean, parsed.to_dict(), result, self.allowed)

        if self.provider is None:       # no key / SDK: log it and fall back
            call = LLMCallResult(
                status="error", provider=os.getenv("LLM_PROVIDER", "gemini"),
                model=os.getenv("LLM_MODEL", "unknown"), prompt_version=PROMPT_VERSION,
                request_payload={"user_prompt": user_prompt},
                error_message=self.provider_error)
        else:
            call = self.provider.generate(self.system_prompt, user_prompt)

        validated, issues = None, []
        final_status, error = call.status, call.error_message
        if call.status == "success":
            try:
                validated, issues = validate_llm_output(call.raw_text, result, self.allowed)
            except LLMValidationError as exc:
                final_status, error = "invalid_response", str(exc)

        repo.save_llm_call(conn, qid, call, final_status, error)
        return call, validated, issues, final_status, error

    @staticmethod
    def _parsed_summary(parsed) -> dict:
        return {
            "intent": parsed.intent, "confidence": parsed.confidence,
            "topics": parsed.entities["topics"], "levels": parsed.entities["levels"],
            "corrections": parsed.corrections,
            "synonyms_applied": parsed.synonyms_applied,
            "expanded_query": parsed.expanded_query,
        }

    @staticmethod
    def _respond(query_id, query, status, mode, message, **extra) -> dict:
        base = {
            "query_id": query_id, "query": query, "status": status, "mode": mode,
            "message": message, "needs_review": status == "needs_review",
            "parsed": None, "rewritten_query": None, "suggested_filters": [],
            "explanation": None, "clarifying_question": None,
            "courses": [], "lessons": [], "llm": None, "notes": [],
        }
        base.update(extra)
        return base
        