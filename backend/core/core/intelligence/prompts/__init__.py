from __future__ import annotations

import re


def strip_fences(raw: str) -> str:
    """Strip markdown code fences that LLMs sometimes wrap JSON responses in."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    return match.group(1).strip() if match else raw.strip()