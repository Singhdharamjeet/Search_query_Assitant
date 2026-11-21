import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_DIR = BASE_DIR / "prompts"
PROMPT_VERSION = "v1"
TRANSIENT_CODES = {429, 500, 502, 503, 504}


class LLMConfigError(RuntimeError):
    """Raised when the provider is not configured (for example, missing key)."""


@dataclass
class LLMCallResult:
    status: str                 # success | timeout | error
    provider: str
    model: str
    prompt_version: str
    request_payload: dict
    raw_text: str | None = None
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_message: str | None = None


# ------------------------------------------------------------------ prompts
def load_system_prompt() -> str:
    base = (PROMPT_DIR / f"system_{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    examples = json.loads((PROMPT_DIR / "examples.json").read_text(encoding="utf-8"))
    parts = [base, "\n# Examples\n"]
    for i, ex in enumerate(examples, 1):
        parts.append(
            f"## Example {i}\nINPUT:\n{json.dumps(ex['input'], indent=2)}\n"
            f"OUTPUT:\n{json.dumps(ex['output'], indent=2)}\n"
        )
    return "\n".join(parts)


def build_user_prompt(query: str, parsed: dict, search_result: dict, allowed_values: dict) -> str:
    """Wrap the learner query and the grounded candidates in clear boundaries."""
    safe_query = query.replace("<", "(").replace(">", ")")
    courses = [
        {"course_id": c["course_id"], "title": c["title"],
         "category": c["category"], "level": c["level"]}
        for c in search_result["courses"]
    ]
    lessons = [
        {"lesson_id": l["lesson_id"], "course_id": l["course_id"],
         "title": l["title"], "summary": l["summary"]}
        for l in search_result["lessons"]
    ]
    nlp_hints = {
        "intent": parsed["intent"],
        "topics": parsed["entities"]["topics"],
        "levels": parsed["entities"]["levels"],
        "confidence": parsed["confidence"],
    }
    return (
        f"<learner_query>\n{safe_query}\n</learner_query>\n\n"
        f"<nlp_hints>\n{json.dumps(nlp_hints)}\n</nlp_hints>\n\n"
        f"<candidate_courses>\n{json.dumps(courses, indent=1)}\n</candidate_courses>\n\n"
        f"<candidate_lessons>\n{json.dumps(lessons, indent=1)}\n</candidate_lessons>\n\n"
        f"<allowed_filter_values>\n{json.dumps(allowed_values)}\n</allowed_filter_values>\n\n"
        "Respond with the JSON object only."
    )


# ---------------------------------------------------------------- providers
class LLMProvider:
    name = "base"

    def __init__(self, model: str):
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> LLMCallResult:
        raise NotImplementedError

    def _payload(self, user_prompt: str) -> dict:
        # Never store the API key. Store only what was sent as the prompt.
        return {"model": self.model, "prompt_version": PROMPT_VERSION,
                "user_prompt": user_prompt}


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 timeout_seconds: float | None = None, max_attempts: int = 2):
        super().__init__(model or os.getenv("LLM_MODEL", "gemini-2.5-flash"))
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key or self.api_key == "your_key_here":
            raise LLMConfigError("GEMINI_API_KEY is missing. Add it to your .env file.")
        self.timeout = float(timeout_seconds or os.getenv("LLM_TIMEOUT_SECONDS", "20"))
        self.max_attempts = max_attempts

        from google import genai            # imported here so mock mode needs no SDK
        from google.genai import types
        self._types = types
        self._client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(timeout=int(self.timeout * 1000)),  # ms
        )

    def generate(self, system_prompt: str, user_prompt: str) -> LLMCallResult:
        from google.genai import errors

        result = LLMCallResult(
            status="error", provider=self.name, model=self.model,
            prompt_version=PROMPT_VERSION, request_payload=self._payload(user_prompt))
        config = self._types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.2,
            max_output_tokens=2048,   # room for any internal "thinking" tokens
        )

        started = time.perf_counter()
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=user_prompt, config=config)
                result.raw_text = response.text
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    result.input_tokens = getattr(usage, "prompt_token_count", None)
                    result.output_tokens = getattr(usage, "candidates_token_count", None)
                if not result.raw_text:
                    result.status = "error"
                    result.error_message = "Model returned an empty response."
                else:
                    result.status, result.error_message = "success", None
                break
            except errors.APIError as exc:
                code = getattr(exc, "code", None)
                result.status = "error"
                result.error_message = f"API error {code}: {getattr(exc, 'message', exc)}"
                if code in TRANSIENT_CODES and attempt < self.max_attempts:
                    time.sleep(1.5 * attempt)
                    continue
                break
            except Exception as exc:   # network, timeout, SDK problems
                text = f"{type(exc).__name__}: {exc}"
                is_timeout = "timeout" in text.lower() or "timed out" in text.lower()
                result.status = "timeout" if is_timeout else "error"
                result.error_message = text[:300]
                if is_timeout and attempt < self.max_attempts:
                    continue
                break
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result


class MockProvider(LLMProvider):
    """Offline provider for tests. mode: ok | timeout | error | malformed."""
    name = "mock"

    def __init__(self, mode: str = "ok", response_text: str | None = None):
        super().__init__("mock-model")
        self.mode = mode
        self.response_text = response_text

    def generate(self, system_prompt: str, user_prompt: str) -> LLMCallResult:
        result = LLMCallResult(
            status="success", provider=self.name, model=self.model,
            prompt_version=PROMPT_VERSION, request_payload=self._payload(user_prompt),
            latency_ms=5)
        if self.mode == "timeout":
            result.status, result.error_message = "timeout", "Simulated timeout"
        elif self.mode == "error":
            result.status, result.error_message = "error", "Simulated API error 503"
        elif self.mode == "malformed":
            result.raw_text = "Sure! Here are some courses you might like..."
        else:
            result.raw_text = self.response_text or "{}"
        return result


def get_provider() -> LLMProvider:
    name = os.getenv("LLM_PROVIDER", "gemini").lower()
    if name == "gemini":
        return GeminiProvider()
    if name == "mock":
        return MockProvider()
    raise LLMConfigError(f"Unknown LLM_PROVIDER: {name!r}")