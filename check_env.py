import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(".env")
print(".env file exists in this folder:", env_path.exists())
print("Current folder:", Path.cwd())

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
print("LLM_PROVIDER:", os.getenv("LLM_PROVIDER"))
print("LLM_MODEL:", os.getenv("LLM_MODEL"))

if not key:
    print("GEMINI_API_KEY: NOT FOUND")
elif key == "your_key_here":
    print("GEMINI_API_KEY: still the placeholder text")
else:
    print(f"GEMINI_API_KEY: found, length {len(key)}, starts with {key[:4]}...")
    if key != key.strip() or '"' in key or "'" in key:
        print("WARNING: key has spaces or quotes. Remove them.")