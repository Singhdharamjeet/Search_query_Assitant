# Sample end-to-end trace

Generated: 2026-11-28 14:27. One real query followed through every layer.

## 1. Input

- Query id: `1` (table `search_queries`)
- Raw query: `something to get better at pivot tables`
- Learner id: `1`

## 2. NLP result

- Cleaned query: `something to get better at pivot tables`
- Intent: `find_course`, confidence `0.8`
- Entities (`search_queries.entities_json`):

```json
{
  "topics": [
    "pivot table"
  ],
  "levels": [],
  "categories": [],
  "courses": []
}
```

## 3. LLM request

- Provider / model: `gemini` / `gemini-3.5-flash-lite`
- Prompt version: `v1`
- Latency: 2321 ms, tokens in/out: 1709 / 183
- User prompt sent (candidates come from the SQL + TF-IDF search; the system prompt is in `prompts/system_v1.md`):

```text
<learner_query>
something to get better at pivot tables
</learner_query>

<nlp_hints>
{"intent": "find_course", "topics": ["pivot table"], "levels": [], "confidence": 0.8}
</nlp_hints>

<candidate_courses>
[
 {
  "course_id": 2,
  "title": "Excel Pivot Tables and Dashboards",
  "category": "Spreadsheets",
  "level": "intermediate"
 }
]
</candidate_courses>

<candidate_lessons>
[
 {
  "lesson_id": 4,
  "course_id": 2,
  "title": "Introduction to pivot tables",
  "summary": "Summarize large datasets quickly by dragging fields into a pivot table"
 },
 {
  "lesson_id": 6,
  "course_id": 2,
  "title": "Building an Excel dashboard",
  "summary": "Combine pivot tables and charts into an interactive dashboard"
 },
 {
  "lesson_id": 5,
  "course_id": 2,
  "title": "Grouping filtering and slicers",
  "summary": "Group data by date and category and filter with slicers"
 },
 {
  "lesson_id": 12,
  "course_id": 4,
  "title": "Grouping and aggregating",
  "summary": "Summarize data with groupby and pivot tables in pandas"
 }
]
</candidate_lessons>

<allowed_filter_values>
{"level": ["beginner", "intermediate", "advanced"], "category": ["Data Analysis", "Data Science", "Data Visualization", "Databases", "Management", "Marketing", "Programming", "Security", "Soft Skills", "Spreadsheets"]}
</allowed_filter_values>

Respond with the JSON object only.
```

## 4. LLM raw response (`llm_calls.response_json`)

```json
{
  "rewritten_query": "learn and improve pivot table skills",
  "intent": "find_course",
  "suggested_filters": [
    {
      "field": "category",
      "value": "Spreadsheets",
      "reason": "Pivot tables are a spreadsheet tool typically found in Excel."
    }
  ],
  "selected_course_ids": [
    2
  ],
  "selected_lesson_ids": [
    4,
    5,
    6
  ],
  "needs_clarification": false,
  "clarifying_question": null,
  "confidence": 0.95,
  "explanation": "The course on Excel Pivot Tables and Dashboards directly matches the query, along with its relevant lessons on pivot tables and filtering."
}
```

## 5. Stored results (`search_results`)

| Source | Rank | Score | Course | Lesson |
|---|---|---|---|---|
| llm | 1 | 0.89 | Excel Pivot Tables and Dashboards | - |
| llm | 1 | 0.75 | Excel Pivot Tables and Dashboards | Introduction to pivot tables |
| llm | 2 | 0.52 | Excel Pivot Tables and Dashboards | Grouping filtering and slicers |
| llm | 3 | 0.64 | Excel Pivot Tables and Dashboards | Building an Excel dashboard |
| tfidf | 1 | 0.89 | Excel Pivot Tables and Dashboards | - |
| tfidf | 1 | 0.75 | Excel Pivot Tables and Dashboards | Introduction to pivot tables |
| tfidf | 2 | 0.64 | Excel Pivot Tables and Dashboards | Building an Excel dashboard |
| tfidf | 3 | 0.52 | Excel Pivot Tables and Dashboards | Grouping filtering and slicers |
| tfidf | 4 | 0.18 | Python Data Analysis with Pandas | Grouping and aggregating |

`tfidf` rows are the candidates found by search. `llm` rows are the records the model selected after validation (invented ids would be dropped).

## 6. Audit log

| Action | Actor | Time |
|---|---|---|
| query_received | learner:1 | 2026-11-28 08:57:08 |
| feedback_saved | learner | 2026-11-28 08:57:52 |

Final status of the query: `completed`.
