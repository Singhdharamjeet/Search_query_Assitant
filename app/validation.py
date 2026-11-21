import re
import unicodedata

MIN_LENGTH = 2
MAX_LENGTH = 200


class ValidationError(ValueError):
    """Raised when user input is not acceptable."""


def validate_query(raw) -> str:
    """Return a cleaned query string or raise ValidationError."""
    if raw is None:
        raise ValidationError("Query is missing.")
    if not isinstance(raw, str):
        raise ValidationError("Query must be text.")

    text = unicodedata.normalize("NFKC", raw)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)   # remove control characters
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        raise ValidationError("Query cannot be empty.")
    if len(text) < MIN_LENGTH:
        raise ValidationError(f"Query is too short (minimum {MIN_LENGTH} characters).")
    if len(text) > MAX_LENGTH:
        raise ValidationError(f"Query is too long (maximum {MAX_LENGTH} characters).")
    if not re.search(r"\w", text):
        raise ValidationError("Query must contain letters or numbers.")
    return text


def validate_learner_id(value):
    """Return an int learner id, or None if not provided."""
    if value is None or value == "":
        return None
    try:
        learner_id = int(value)
    except (TypeError, ValueError):
        raise ValidationError("Learner id must be a whole number.")
    if learner_id <= 0:
        raise ValidationError("Learner id must be positive.")
    return learner_id