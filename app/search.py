import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.nlp import ParsedQuery, clean_text

MIN_SCORE = 0.08        # ignore very weak matches
TOPIC_BOOST = 0.35      # course title/tags match a detected topic
CATEGORY_BOOST = 0.15   # course category matches a detected category
PARENT_BOOST = 0.20     # lesson belongs to a strongly matched course


def _has_term(text: str, term: str) -> bool:
    return bool(re.search(rf"\b{re.escape(term)}\b", text))


class SearchEngine:
    """TF-IDF index over published courses and lessons, plus SQL filtering."""

    def __init__(self, courses, lessons):
        self.courses = [dict(c) for c in courses]
        if not self.courses:
            raise ValueError("No published courses found. Run: python load_data.py")

        course_by_id = {c["course_id"]: c for c in self.courses}
        for c in self.courses:
            c["title_clean"] = clean_text(c["title"])
            c["tag_list"] = [clean_text(t) for t in (c["tags"] or "").split(";") if t.strip()]
            c["doc"] = clean_text(" ".join([
                c["title"], c["title"], c["category"], c["description"],
                (c["tags"] or "").replace(";", " "),
            ]))

        # keep only lessons that belong to a published course
        self.lessons = [dict(l) for l in lessons if l["course_id"] in course_by_id]
        for l in self.lessons:
            parent = course_by_id[l["course_id"]]
            l["course_title"] = parent["title"]
            l["doc"] = clean_text(" ".join([
                l["title"], l["title"], l["summary"], parent["title"],
                (parent["tags"] or "").replace(";", " "),
            ]))

        self.course_vec = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        self.course_matrix = self.course_vec.fit_transform([c["doc"] for c in self.courses])

        self.lesson_vec = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        self.lesson_matrix = (
            self.lesson_vec.fit_transform([l["doc"] for l in self.lessons])
            if self.lessons else None)

    @classmethod
    def from_db(cls, conn):
        courses = conn.execute(
            "SELECT course_id, title, category, level, description, tags "
            "FROM courses WHERE status = 'published'").fetchall()
        lessons = conn.execute(
            "SELECT lesson_id, course_id, title, summary, duration_min, position "
            "FROM lessons WHERE status = 'published'").fetchall()
        return cls(courses, lessons)

    # ------------------------------------------------------------ public API
    def search(self, conn, parsed: ParsedQuery, top_courses=5, top_lessons=5) -> dict:
        qtext = clean_text(" ".join([parsed.expanded_query] + parsed.entities["topics"]))
        levels = parsed.entities["levels"]

        if not qtext:
            return self._result([], [], qtext, levels, relaxed=False)

        allowed = self._allowed_course_ids(conn, levels)
        courses = self._score_courses(qtext, parsed, allowed)
        relaxed = False

        # level filter left nothing: retry without it and tell the caller
        if not courses and levels:
            allowed = self._allowed_course_ids(conn, [])
            courses = self._score_courses(qtext, parsed, allowed)
            relaxed = bool(courses)

        top = courses[:top_courses]
        lessons = self._score_lessons(qtext, allowed, {c["course_id"] for c in top})
        return self._result(top, lessons[:top_lessons], qtext, levels, relaxed)

    # ------------------------------------------------------------ internals
    @staticmethod
    def _allowed_course_ids(conn, levels) -> set:
        """SQL filter step (parameterized to prevent injection)."""
        sql = "SELECT course_id FROM courses WHERE status = 'published'"
        params = []
        if levels:
            sql += f" AND level IN ({','.join('?' * len(levels))})"
            params.extend(levels)
        return {row[0] for row in conn.execute(sql, params)}

    def _score_courses(self, qtext, parsed, allowed) -> list:
        sims = cosine_similarity(self.course_vec.transform([qtext]), self.course_matrix)[0]
        topics = parsed.entities["topics"]
        categories = {clean_text(c) for c in parsed.entities["categories"]}

        results = []
        for course, sim in zip(self.courses, sims):
            if course["course_id"] not in allowed:
                continue
            matched = [t for t in topics
                       if t in course["tag_list"] or _has_term(course["title_clean"], t)]
            score = float(sim)
            if matched:
                score += TOPIC_BOOST
            if clean_text(course["category"]) in categories:
                score += CATEGORY_BOOST
            score = min(round(score, 3), 1.0)
            if score >= MIN_SCORE:
                results.append({
                    "course_id": course["course_id"],
                    "title": course["title"],
                    "category": course["category"],
                    "level": course["level"],
                    "score": score,
                    "matched_topics": matched,
                    "reason": ("Matches your topic: " + ", ".join(matched)) if matched
                              else "Similar wording to your query",
                })
        results.sort(key=lambda r: (-r["score"], r["title"]))
        return results

    def _score_lessons(self, qtext, allowed, top_course_ids) -> list:
        if self.lesson_matrix is None:
            return []
        sims = cosine_similarity(self.lesson_vec.transform([qtext]), self.lesson_matrix)[0]
        results = []
        for lesson, sim in zip(self.lessons, sims):
            if lesson["course_id"] not in allowed:
                continue
            score = float(sim)
            if score < MIN_SCORE:
                continue  # parent boost only helps lessons that already match
            if lesson["course_id"] in top_course_ids:
                score += PARENT_BOOST
            results.append({
                "lesson_id": lesson["lesson_id"],
                "course_id": lesson["course_id"],
                "course_title": lesson["course_title"],
                "title": lesson["title"],
                "summary": lesson["summary"],
                "duration_min": lesson["duration_min"],
                "score": min(round(score, 3), 1.0),
            })
        results.sort(key=lambda r: (-r["score"], r["title"]))
        return results

    @staticmethod
    def _result(courses, lessons, qtext, levels, relaxed) -> dict:
        return {
            "courses": courses,
            "lessons": lessons,
            "no_match": not courses and not lessons,
            "query_text": qtext,
            "filters": {"levels": levels, "level_filter_relaxed": relaxed},
        }