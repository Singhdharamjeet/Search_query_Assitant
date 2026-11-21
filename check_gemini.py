import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=30000),   # 30 seconds, in ms
)

MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
]

for model in MODELS:
    start = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model, contents="Reply with the single word: ready")
        outcome = f"OK -> {response.text.strip()[:30]!r}"
    except Exception as exc:
        outcome = f"FAILED -> {type(exc).__name__}: {str(exc)[:90]}"
    print(f"{model:<24} {time.perf_counter() - start:5.1f}s  {outcome}")