from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
NUMERIC_INPUT_PATH = STATIC_ROOT / "numeric-input.js"

def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")

def extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[body_start:index + 1]
    raise AssertionError(f"Unclosed function: {signature}")

def extract_function_declaration(source: str, signature: str) -> str:
    start = source.index(signature)
    body = extract_function(source, signature)
    return source[start : source.index(body, start) + len(body)]
