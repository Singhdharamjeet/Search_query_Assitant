import re
import unicodedata
from dataclasses import asdict, dataclass, field

from rapidfuzz import fuzz, process

# ---------------------------------------------------------------- word lists
STOPWORDS = {
    "i", "me", "my", "we", "you", "your", "a", "an", "the", "to", "of", "in",
    "on", "for", "with", "and", "or", "at", "by", "from", "about", "into",
    "is", "are", "am", "be", "want", "need", "would", "like", "can", "could",
    "should", "please", "help", "get", "getting", "something", "anything",
    "some", "any", "how", "do", "does", "what", "which", "that", "this", "it",
    "its", "as", "so", "there", "find", "show", "give", "looking", "look",
    "have", "has", "had", "im", "ive", "more", "also", "just", "really",
    "very", "much", "up", "out",
}
INTENT_WORDS = {
    "course", "courses", "lesson", "lessons", "class", "classes", "tutorial",
    "tutorials", "training", "program", "video", "videos", "chapter",
    "chapters", "learn", "learning", "study", "improve", "better", "skill",
    "skills", "know", "knowledge",
}
NOISE_WORDS = STOPWORDS | INTENT_WORDS
EXTRA_KNOWN = {"beginner", "beginners", "intermediate", "advanced", "basic",
               "basics", "starter", "expert"}

# ---------------------------------------------------------------- intent rules
UNSUPPORTED_RULES = [
    (r"\b(ignore|disregard|forget)\b.*\b(instructions|rules|prompt)\b",
     "Looks like a prompt-injection attempt"),
    (r"\b(refund|refunds|chargeback)\b",
     "Refunds are handled by the support team"),
    (r"\b(issue|send|give|generate|download|print)\b.*\b(certificate|certificates|invoice|receipt)\b",
     "Certificates and invoices cannot be issued from search"),
    (r"\b(grade|grades|grading|regrade)\b",
     "Grading is done by trainers"),
    (r"\b(enrol|enroll|enrolled|enrolment|enrollment)\b",
     "Enrolment needs administrator approval"),
    (r"\b(delete|remove)\b.*\b(account|course|learner|data)\b",
     "Changing records is not supported"),
    (r"\b(pay|payment|payments)\b",
     "Payments are not handled here"),
]
UNSUPPORTED_RULES = [(re.compile(p), reason) for p, reason in UNSUPPORTED_RULES]

LESSON_RX = re.compile(
    r"\b(lesson|lessons|video|videos|tutorial|tutorials|chapter|chapters|"
    r"how to|how do i|how can i|steps?)\b")
BROWSE_RX = re.compile(
    r"\b(all|list|browse|available|catalog|what courses|which courses|what topics)\b")
COURSE_RX = re.compile(
    r"\b(course|courses|class|classes|training|program|learn|learning|study|"
    r"improve|better at|get better|upskill)\b")

LEVEL_RULES = {
    "beginner": re.compile(
        r"\b(beginner|beginners|basic|basics|starter|intro|introduction|"
        r"introductory|new to|fundamentals?|from scratch|entry level)\b"),
    "intermediate": re.compile(r"\b(intermediate|some experience|mid level)\b"),
    "advanced": re.compile(r"\b(advanced|expert|deep dive)\b"),
}


# ---------------------------------------------------------------- helpers
def clean_text(text: str) -> str:
    """Lowercase, strip accents/punctuation, collapse spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _singular(term: str) -> str:
    return term[:-1] if term.endswith("s") else term


# ---------------------------------------------------------------- knowledge
class Knowledge:
    """Vocabulary built from the LMS database: titles, categories, tags, synonyms."""

    def __init__(self, synonym_rows, course_rows):
        self.synonyms = {}
        for row in synonym_rows:
            term, canon = clean_text(row["term"]), clean_text(row["canonical_term"])
            if term and canon:
                self.synonyms[term] = canon

        self.courses = [dict(r) for r in course_rows]
        self.category_map = {}
        terms = set()
        for course in self.courses:
            course["title_clean"] = clean_text(course["title"])
            terms.add(course["title_clean"])
            category = clean_text(course["category"])
            self.category_map[category] = course["category"]
            terms.add(category)
            for tag in (course["tags"] or "").split(";"):
                tag = clean_text(tag)
                if tag:
                    terms.add(tag)
        for term, canon in self.synonyms.items():
            terms.add(term)
            terms.add(canon)

        # longest terms first so "power bi" is tried before "bi"
        self.terms = sorted((t for t in terms if len(t) >= 2),
                            key=lambda t: (-len(t), t))
        self.patterns = [(t, re.compile(rf"\b{re.escape(t)}s?\b")) for t in self.terms]

        vocab_words = {w for t in self.terms for w in t.split() if len(w) >= 4}
        self.known_words = vocab_words | NOISE_WORDS | EXTRA_KNOWN
        self.words_by_letter = {}
        for word in sorted(vocab_words | {w for w in INTENT_WORDS if len(w) >= 4}):
            self.words_by_letter.setdefault(word[0], []).append(word)

    @classmethod
    def from_db(cls, conn):
        synonyms = conn.execute("SELECT term, canonical_term FROM synonyms").fetchall()
        courses = conn.execute(
            "SELECT course_id, title, category, level, tags "
            "FROM courses WHERE status = 'published'").fetchall()
        return cls(synonyms, courses)

    def correct(self, token: str) -> str:
        """Fix a likely typo by matching against known vocabulary."""
        if len(token) < 4 or token.isdigit() or token in self.known_words:
            return token
        if token.endswith("s") and token[:-1] in self.known_words:
            return token
        candidates = self.words_by_letter.get(token[0], [])
        if not candidates:
            return token
        match = process.extractOne(token, candidates, scorer=fuzz.ratio,
                                   score_cutoff=80)
        return match[0] if match else token


# ---------------------------------------------------------------- result
@dataclass
class ParsedQuery:
    raw_query: str
    cleaned_query: str
    tokens: list
    content_tokens: list
    corrections: dict
    intent: str
    entities: dict
    synonyms_applied: list
    expanded_terms: list
    expanded_query: str
    confidence: float
    needs_clarification: bool
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- parser
class QueryParser:
    def __init__(self, knowledge: Knowledge):
        self.kb = knowledge

    def parse(self, query: str) -> ParsedQuery:
        notes = []

        # 1. clean, tokenize, fix typos
        cleaned = clean_text(query)
        corrections, fixed = {}, []
        for token in cleaned.split():
            new = self.kb.correct(token)
            if new != token:
                corrections[token] = new
            fixed.append(new)
        text = " ".join(fixed)
        if corrections:
            notes.append("Spelling corrected: " + ", ".join(
                f"{a} -> {b}" for a, b in corrections.items()))
        if not fixed:
            notes.append("No usable words found in the query.")

        # 2. entities
        found = self._find_terms(text)
        topics, applied = [], []
        for term in found:
            canon = self.kb.synonyms.get(term, term)
            if canon not in topics:
                topics.append(canon)
            if canon != term and canon != _singular(term):
                applied.append({"from": term, "to": canon})

        entities = {
            "topics": topics,
            "levels": [lvl for lvl, rx in LEVEL_RULES.items() if rx.search(text)],
            "categories": sorted({self.kb.category_map[t] for t in found
                                  if t in self.kb.category_map}),
            "courses": [
                {"course_id": c["course_id"], "title": c["title"]}
                for c in self.kb.courses
                if re.search(rf"\b{re.escape(c['title_clean'])}\b", text)
            ],
        }

        # 3. intent
        intent, reason = self._detect_intent(text, bool(topics))
        if reason:
            notes.append(reason)

        # 4. expansion
        content_tokens = [t for t in fixed if t not in NOISE_WORDS]
        expanded_terms = [a["to"] for a in applied]
        words, seen = [], set()
        for word in content_tokens + [w for t in topics for w in t.split()]:
            key = _singular(word)
            if key not in seen:
                seen.add(key)
                words.append(word)
        expanded_query = " ".join(words)

        # 5. confidence
        confidence = self._confidence(intent, topics, entities["levels"], content_tokens)
        needs_clarification = intent != "unsupported" and confidence < 0.5

        return ParsedQuery(
            raw_query=query, cleaned_query=text, tokens=fixed,
            content_tokens=content_tokens, corrections=corrections,
            intent=intent, entities=entities, synonyms_applied=applied,
            expanded_terms=expanded_terms, expanded_query=expanded_query,
            confidence=confidence, needs_clarification=needs_clarification,
            notes=notes,
        )

    # -- internals
    def _find_terms(self, text: str) -> list:
        found = [t for t, rx in self.kb.patterns if rx.search(text)]
        # drop terms that are only part of a longer matched term
        return [t for t in found
                if not any(t != o and re.search(rf"\b{re.escape(t)}\b", o)
                           for o in found)]

    @staticmethod
    def _detect_intent(text: str, has_topics: bool):
        for rx, reason in UNSUPPORTED_RULES:
            if rx.search(text):
                return "unsupported", reason
        if LESSON_RX.search(text):
            return "find_lesson", None
        if BROWSE_RX.search(text):
            return "browse_topic", None
        if COURSE_RX.search(text) or has_topics:
            return "find_course", None
        return "unknown", None

    @staticmethod
    def _confidence(intent, topics, levels, content_tokens) -> float:
        if intent == "unsupported":
            return 0.9
        score = 0.0
        if topics:
            score += 0.5 + min(0.1 * (len(topics) - 1), 0.2)
        if intent in ("find_course", "find_lesson", "browse_topic"):
            score += 0.2
        if levels:
            score += 0.1
        if len(content_tokens) >= 2:
            score += 0.1
        return min(round(score, 2), 1.0)