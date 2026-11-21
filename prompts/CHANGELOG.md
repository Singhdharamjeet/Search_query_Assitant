# Prompt version notes

## v1
- First version: role, hard rules, untrusted-input boundary, strict JSON output.
- Three few-shot examples: normal match, vague query, injection/unsupported request.
- Grounding: model may only choose from supplied candidate records.
- Output validated by app/guardrails.py (schema + ID + filter checks).