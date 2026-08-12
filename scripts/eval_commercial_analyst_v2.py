#!/usr/bin/env python3
"""Run the bounded seven-question Commercial Analyst model/prompt comparison.

The evaluator records provider telemetry and deterministic safety checks. Human rubric fields remain
explicitly unscored until a reviewer inspects the answer; it never manufactures quality ratings.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ai.config import load_openai_config
from app.ai.service import OpenAIIntelligenceService
from app.models import Project
from app.persistence.database import build_engine, build_session_factory

QUESTIONS = (
    "Why pursue Stafford?",
    "What data should I not trust?",
    "What would change the recommendation?",
    "Who should we investigate first?",
    "What is blocking Pipedrive?",
    "Which product appears strongest?",
    "What should I ask on the first call?",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data/demo_seed/offgrid_demo_seed.db")
    parser.add_argument("--output", type=Path, default=ROOT / "research/commercial-analyst-v2-eval.json")
    parser.add_argument("--live", action="store_true", help="Execute authorized provider calls.")
    args = parser.parse_args()
    engine = build_engine(f"sqlite+pysqlite:///{args.database.resolve()}")
    factory = build_session_factory(engine)
    rows = []
    with factory() as session:
        project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
        if project is None:
            raise RuntimeError("Stafford is missing from evaluation seed")
        base = load_openai_config()
        configurations = (
            ("terra-medium-v1-baseline", "FAST", "v1"),
            ("sol-medium-v1", "STANDARD", "v1"),
            ("sol-medium-v2", "STANDARD", "v2"),
            ("sol-high-v2-deep", "DEEP", "v2"),
        )
        for label, mode, prompt_version in configurations:
            task = base.tasks["commercial_analyst"]
            tasks = dict(base.tasks)
            tasks["commercial_analyst"] = replace(
                task,
                prompt_version=prompt_version,
                output_schema=(
                    "commercial-analyst-answer-1.0"
                    if prompt_version == "v1"
                    else "commercial-analyst-answer-2.0"
                ),
            )
            config = replace(base, enabled=args.live, tasks=tasks)
            for question in QUESTIONS:
                started = time.perf_counter()
                result = OpenAIIntelligenceService(session, config=config).answer_commercial_question(
                    project_id=project.id,
                    question=question,
                    mode=mode,
                )
                elapsed = round((time.perf_counter() - started) * 1000)
                rows.append(
                    {
                        "configuration": label,
                        "question": question,
                        "status": result.status.value,
                        "model_id": result.model_id,
                        "grounding": result.grounding.status.value if result.grounding else None,
                        "latency_ms": result.latency_ms or elapsed,
                        "tool_rounds": result.tool_rounds,
                        "estimated_cost_usd": str(result.estimated_cost_usd),
                        "repair_attempted": result.repair_attempted,
                        "cache_hit": result.cache_hit,
                        "answer": result.parsed.model_dump() if result.parsed else None,
                        "human_rubric": {
                            key: None
                            for key in (
                                "correctness",
                                "completeness",
                                "calibration",
                                "groundedness",
                                "actionability",
                                "citation_accuracy",
                            )
                        },
                    }
                )
    engine.dispose()
    report = {
        "eval_version": "commercial-analyst-eval-2.0",
        "live_provider_calls": args.live,
        "question_count": len(QUESTIONS),
        "configuration_count": 4,
        "results": rows,
        "claim": "Quality ratings require evidence-backed human review and are intentionally not fabricated.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "rows": len(rows), "live": args.live}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
