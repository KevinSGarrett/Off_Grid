from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PROMPT_ROOT = ROOT / "prompts"


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str
    version: str
    text: str
    sha256: str
    path: Path


def load_prompt(name: str, version: str) -> PromptTemplate:
    path = PROMPT_ROOT / name / f"{version}.md"
    text = path.read_text(encoding="utf-8")
    return PromptTemplate(
        name=name,
        version=version,
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        path=path,
    )
