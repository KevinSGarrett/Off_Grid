#!/usr/bin/env python3
"""Run the bounded seven-question Commercial Analyst model/prompt comparison.

Live calls are opt-in, operate on a temporary database copy, and can resume an interrupted report.
The quality rubric is deterministic and publishes every check; it does not pretend to be a human
preference score or an empirical measure of business success.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ai.config import load_openai_config
from app.ai.schemas import CommercialAnalystAnswer
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

CONFIGURATIONS = (
    ("terra-medium-v1-baseline", "FAST", "v1"),
    ("sol-medium-v1", "STANDARD", "v1"),
    ("sol-medium-v2", "STANDARD", "v2"),
    ("sol-high-v2-deep", "DEEP", "v2"),
)

EXPECTED_TERMS = {
    QUESTIONS[0]: (("verify",), ("general contractor", "post bid", "data center")),
    QUESTIONS[1]: (("7.5", "estimate", "projection"), ("unknown", "unverified", "not trust")),
    QUESTIONS[2]: (("verify",), ("confirm", "validated", "requirement", "responsibility")),
    QUESTIONS[3]: (("doug meadows",), ("unknown", "not a verified", "investigation")),
    QUESTIONS[4]: (("blocked",), ("dry-run", "no external write", "previewed")),
    QUESTIONS[5]: (("unverified_applicability", "unverified applicability", "unverified"),),
    QUESTIONS[6]: (("responsibility", "authority"), ("lighting", "power", "need")),
}


def _score(score: int, checks: list[str], failures: list[str]) -> dict[str, Any]:
    return {"score_0_to_5": max(0, min(score, 5)), "checks": checks, "failures": failures}


def _rubric(
    *,
    question: str,
    prompt_version: str,
    answer: dict[str, Any] | None,
    status: str,
    grounding: str | None,
    valid_evidence_refs: set[str] | None,
) -> dict[str, Any]:
    """Score only observable answer-contract properties and publish the basis."""
    if not answer:
        failure = f"No structured answer was produced (status={status})."
        return {
            key: _score(0, [], [failure])
            for key in (
                "correctness",
                "completeness",
                "calibration",
                "groundedness",
                "actionability",
                "citation_accuracy",
            )
        }

    claims = list(answer.get("claims") or [])
    full_text = " ".join(
        str(value)
        for value in (
            answer.get("direct_conclusion", ""),
            answer.get("answer", ""),
            answer.get("next_action", ""),
            " ".join(answer.get("unknowns") or []),
            " ".join(str(claim.get("claim_text", "")) for claim in claims),
        )
    ).lower()

    expected_checks: list[str] = []
    expected_failures: list[str] = []
    for alternatives in EXPECTED_TERMS[question]:
        if any(term in full_text for term in alternatives):
            expected_checks.append("Includes expected concept: " + " | ".join(alternatives))
        else:
            expected_failures.append("Missing expected concept: " + " | ".join(alternatives))
    false_authority = bool(
        re.search(r"\b(?:is|has) verified (?:rental|purchasing|buyer|decision)[ -]?(?:authority|maker)?\b", full_text)
        and "not a verified" not in full_text
        and "authority is unknown" not in full_text
    )
    positive_product_claims = [
        claim
        for claim in claims
        if re.search(
            r"\b(?:confirmed_fit|validated product fit|confirmed product need)\b",
            str(claim.get("claim_text") or "").lower(),
        )
        and not re.search(
            r"\b(?:not|never|no|without|cannot|should not|isn't|aren't)\b.{0,50}"
            r"\b(?:confirmed_fit|validated product fit|confirmed product need)\b",
            str(claim.get("claim_text") or "").lower(),
        )
    ]
    false_product = bool(positive_product_claims)
    old_precision = prompt_version == "v2" and bool(
        re.search(r"\b(?:kvt|kv6|kvp)\b.{0,24}\b(?:80|75|59)\b", full_text)
    )
    correctness_failures = list(expected_failures)
    if false_authority:
        correctness_failures.append("Claims verified commercial authority without deterministic support.")
    if false_product:
        correctness_failures.append("Claims confirmed/validated product fit without direct need evidence.")
    if old_precision:
        correctness_failures.append("v2 repeats prohibited historical product-score precision.")
    correctness = _score(
        5 - len(correctness_failures),
        expected_checks + ["No false authority/product claim or prohibited v2 score detected."],
        correctness_failures,
    )

    required = (
        "direct_conclusion",
        "why",
        "supporting_evidence",
        "caveats",
        "decision_changing_unknowns",
        "recommendation_triggers",
        "next_action",
        "claims",
    )
    missing_sections = [name for name in required if not answer.get(name)]
    answer_words = len(str(answer.get("answer") or "").split())
    completeness_failures = [f"Empty required section: {name}" for name in missing_sections]
    if prompt_version == "v2" and answer_words < 180:
        completeness_failures.append(
            f"v2 validated answer has {answer_words} words; evidence-supported adaptive detail is thin."
        )
    completeness = _score(
        5 - min(5, len(completeness_failures)),
        [f"{len(required) - len(missing_sections)}/{len(required)} required sections populated.",
         f"Validated answer word count: {answer_words}."],
        completeness_failures,
    )

    unknowns_present = bool(answer.get("unknowns") or answer.get("decision_changing_unknowns"))
    product_calibrated = not false_product
    probability_calibrated = not re.search(r"\b\d+(?:\.\d+)?% (?:chance|probability|likelihood)\b", full_text)
    authority_calibrated = not false_authority
    calibration_checks = []
    calibration_failures = []
    for ok, label in (
        (unknowns_present, "Preserves explicit unknowns."),
        (product_calibrated, "Does not convert product ordering into confirmed fit."),
        (probability_calibrated, "Does not present deterministic scores as probability."),
        (authority_calibrated, "Keeps authority unverified/unknown."),
    ):
        (calibration_checks if ok else calibration_failures).append(label)
    calibration = _score(1 + len(calibration_checks), calibration_checks, calibration_failures)

    grounding_failures = []
    if status not in {"SUCCEEDED", "PARTIAL_VALIDATED"}:
        grounding_failures.append(f"Run status is {status}.")
    if grounding not in {"VALID", "CONFLICTED"}:
        grounding_failures.append(f"Grounding status is {grounding}.")
    substantive = [claim for claim in claims if claim.get("classification") != "UNKNOWN"]
    uncited = [claim.get("claim_id") for claim in substantive if not claim.get("evidence_ids")]
    if uncited:
        grounding_failures.append(f"Substantive claims without citations: {uncited}")
    grounding_score = _score(
        5 - len(grounding_failures),
        [f"Grounding={grounding}; conflicted evidence remains an accepted disclosed state.",
         f"{len(substantive) - len(uncited)}/{len(substantive)} substantive claims cite evidence."],
        grounding_failures,
    )

    next_action = str(answer.get("next_action") or "")
    action_terms = ("verify", "confirm", "ask", "investigate", "retrieve", "identify", "validate")
    action_checks = []
    action_failures = []
    if any(term in next_action.lower() for term in action_terms):
        action_checks.append("Next action contains a concrete verification/investigation verb.")
    else:
        action_failures.append("Next action is not a concrete verification/investigation step.")
    if answer.get("recommendation_triggers"):
        action_checks.append("Recommendation triggers are populated.")
    else:
        action_failures.append("Recommendation triggers are empty.")
    if answer.get("decision_changing_unknowns"):
        action_checks.append("Decision-changing unknowns are populated.")
    else:
        action_failures.append("Decision-changing unknowns are empty.")
    actionability = _score(2 + len(action_checks) - len(action_failures), action_checks, action_failures)

    all_refs = [str(ref) for claim in claims for ref in claim.get("evidence_ids") or []]
    if valid_evidence_refs is None:
        citation_failures = [] if all_refs and grounding in {"VALID", "CONFLICTED"} else [
            "Provider-time grounding evidence is unavailable or the answer has no citations."
        ]
        citation_accuracy = _score(
            5 if not citation_failures else 0,
            [
                (
                    f"{len(all_refs)} references were accepted by the provider-time deterministic "
                    "grounding validator; IDs belong to the earlier seed instance."
                )
            ],
            citation_failures,
        )
    else:
        bad_refs = sorted({ref for ref in all_refs if ref not in valid_evidence_refs})
        citation_failures = [f"Unknown evidence reference: {ref}" for ref in bad_refs]
        citation_accuracy = _score(
            5 if all_refs and not bad_refs else max(0, 4 - len(citation_failures)),
            [
                (
                    f"{len(all_refs) - len(bad_refs)}/{len(all_refs)} cited references resolve "
                    "in the evaluation catalog."
                )
            ],
            citation_failures + ([] if all_refs else ["No evidence references were returned."]),
        )
    return {
        "correctness": correctness,
        "completeness": completeness,
        "calibration": calibration,
        "groundedness": grounding_score,
        "actionability": actionability,
        "citation_accuracy": citation_accuracy,
    }


def _reproject_answer(answer: dict[str, Any] | None) -> dict[str, Any] | None:
    """Apply the current deterministic display projection to a saved validated answer."""
    if not answer:
        return None
    parsed = CommercialAnalystAnswer.model_validate(answer)
    return OpenAIIntelligenceService._validated_analyst_answer(
        parsed,
        list(parsed.claims),
        withheld=False,
    ).model_dump()


def _valid_refs(service: OpenAIIntelligenceService, project_id) -> set[str]:
    packet = service._commercial_analysis_packet(
        project_id,
        __import__("app.ai.tools", fromlist=["ReadOnlyCommercialToolRegistry"])
        .ReadOnlyCommercialToolRegistry(service.session),
    )
    refs = {
        value["deterministic_evidence_id"]
        for value in packet.values()
        if isinstance(value, dict) and value.get("deterministic_evidence_id")
    }
    for item in service.catalog.project_packet(project_id, limit=1000):
        refs.add(item.evidence_id)
    return refs


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for label, _mode, _prompt in CONFIGURATIONS:
        group = [row for row in rows if row["configuration"] == label]
        completed = [row for row in group if row["status"] in {"SUCCEEDED", "PARTIAL_VALIDATED"}]
        scores = [
            metric["score_0_to_5"]
            for row in completed
            for metric in row.get("deterministic_rubric", {}).values()
        ]
        summary[label] = {
            "completed": len(completed),
            "required": len(QUESTIONS),
            "mean_latency_ms": round(sum(row["latency_ms"] for row in completed) / len(completed))
            if completed else None,
            "total_estimated_cost_usd": str(
                sum((Decimal(row["estimated_cost_usd"]) for row in completed), Decimal(0))
            ),
            "mean_quality_score_0_to_5": round(sum(scores) / len(scores), 3) if scores else None,
            "total_tool_rounds": sum(row.get("tool_rounds", 0) for row in completed),
            "input_tokens": sum((row.get("usage") or {}).get("input_tokens", 0) for row in completed),
            "cached_input_tokens": sum(
                (row.get("usage") or {}).get("cached_input_tokens", 0) for row in completed
            ),
            "output_tokens": sum((row.get("usage") or {}).get("output_tokens", 0) for row in completed),
            "usage_telemetry_rows": sum(bool(row.get("usage_telemetry_available")) for row in completed),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data/demo_seed/offgrid_demo_seed.db")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "research/commercial-analyst-v2-eval.json"
    )
    parser.add_argument("--live", action="store_true", help="Execute authorized provider calls.")
    parser.add_argument("--resume", action="store_true", help="Keep completed rows from a prior report.")
    parser.add_argument(
        "--evaluation-budget-usd",
        type=Decimal,
        default=Decimal("4.00"),
        help="Isolated run ceiling; does not change the production $2 daily guard.",
    )
    args = parser.parse_args()
    if args.evaluation_budget_usd <= 0:
        parser.error("--evaluation-budget-usd must be positive")

    prior_rows: dict[tuple[str, str], dict[str, Any]] = {}
    prior_cache_benchmark: dict[str, Any] | None = None
    if args.resume and args.output.exists():
        prior = json.loads(args.output.read_text(encoding="utf-8"))
        prior_cache_benchmark = prior.get("cache_replay_benchmark")
        prior_rows = {
            (row["configuration"], row["question"]): row
            for row in prior.get("results", [])
            if row.get("status") in {"SUCCEEDED", "PARTIAL_VALIDATED"}
        }

    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="offgrid-analyst-eval-") as temp_dir:
        working_db = Path(temp_dir) / "eval.db"
        shutil.copy2(args.database.resolve(), working_db)
        engine = build_engine(f"sqlite+pysqlite:///{working_db}")
        factory = build_session_factory(engine)
        cache_benchmark = prior_cache_benchmark
        with factory() as session:
            project = session.scalar(sa.select(Project).where(Project.external_id == "1007341663"))
            if project is None:
                raise RuntimeError("Stafford is missing from evaluation seed")
            base = load_openai_config()
            for label, mode, prompt_version in CONFIGURATIONS:
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
                config = replace(
                    base,
                    enabled=args.live,
                    tasks=tasks,
                    daily_budget_usd=args.evaluation_budget_usd,
                )
                for question in QUESTIONS:
                    key = (label, question)
                    service = OpenAIIntelligenceService(session, config=config)
                    valid_refs = _valid_refs(service, project.id)
                    if key in prior_rows:
                        prior_row = dict(prior_rows[key])
                        prior_row["answer"] = _reproject_answer(prior_row.get("answer"))
                        legacy_tool_calls = int(prior_row.get("tool_rounds") or 0)
                        has_usage = bool(prior_row.get("usage_telemetry_available"))
                        prior_row.update(
                            {
                                "mode": mode,
                                "prompt_version": prompt_version,
                                "legacy_tool_calls_recorded": (
                                    None if has_usage else legacy_tool_calls
                                ),
                                "tool_rounds": (
                                    legacy_tool_calls
                                    if has_usage
                                    else (1 if legacy_tool_calls else 0)
                                ),
                                "usage": prior_row.get("usage") if has_usage else None,
                                "usage_telemetry_available": has_usage,
                                "deterministic_rubric": _rubric(
                                    question=question,
                                    prompt_version=prompt_version,
                                    answer=prior_row["answer"],
                                    status=prior_row["status"],
                                    grounding=prior_row.get("grounding"),
                                    valid_evidence_refs=None,
                                ),
                            }
                        )
                        prior_row.pop("human_rubric", None)
                        rows.append(prior_row)
                        continue
                    started = time.perf_counter()
                    result = service.answer_commercial_question(
                        project_id=project.id,
                        question=question,
                        mode=mode,
                    )
                    elapsed = round((time.perf_counter() - started) * 1000)
                    parsed = result.parsed.model_dump() if result.parsed else None
                    grounding = result.grounding.status.value if result.grounding else None
                    rows.append(
                        {
                            "configuration": label,
                            "mode": mode,
                            "prompt_version": prompt_version,
                            "question": question,
                            "status": result.status.value,
                            "model_id": result.model_id,
                            "grounding": grounding,
                            "latency_ms": result.latency_ms or elapsed,
                            "tool_rounds": result.tool_rounds,
                            "estimated_cost_usd": str(result.estimated_cost_usd),
                            "usage": {
                                "input_tokens": result.usage.input_tokens,
                                "cached_input_tokens": result.usage.cached_input_tokens,
                                "output_tokens": result.usage.output_tokens,
                            },
                            "usage_telemetry_available": True,
                            "repair_attempted": result.repair_attempted,
                            "cache_hit": result.cache_hit,
                            "answer": parsed,
                            "deterministic_rubric": _rubric(
                                question=question,
                                prompt_version=prompt_version,
                                answer=parsed,
                                status=result.status.value,
                                grounding=grounding,
                                valid_evidence_refs=valid_refs,
                            ),
                        }
                    )
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(
                        json.dumps(
                            {
                                "eval_version": "commercial-analyst-eval-2.1",
                                "live_provider_calls": args.live,
                                "question_count": len(QUESTIONS),
                                "configuration_count": len(CONFIGURATIONS),
                                "results": rows,
                                "summary": _summary(rows),
                                "rubric_note": (
                                    "Scores cover published deterministic answer-contract checks only; "
                                    "they are not human preference scores, probabilities, or proof of optimality."
                                ),
                            },
                            indent=2,
                            default=str,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    print(json.dumps({"configuration": label, "question": question, "status": result.status.value}))
            if args.live and cache_benchmark is None:
                benchmark_task = base.tasks["commercial_analyst"]
                benchmark_config = replace(
                    base,
                    enabled=True,
                    daily_budget_usd=args.evaluation_budget_usd,
                    tasks={
                        **base.tasks,
                        "commercial_analyst": replace(
                            benchmark_task,
                            prompt_version="v2",
                            output_schema="commercial-analyst-answer-2.0",
                        ),
                    },
                )
                OpenAIIntelligenceService._validated_answer_cache.clear()
                benchmark_service = OpenAIIntelligenceService(session, config=benchmark_config)
                cold = benchmark_service.answer_commercial_question(
                    project_id=project.id,
                    question=QUESTIONS[0],
                    mode="FAST",
                )
                replay_started = time.perf_counter()
                warm = benchmark_service.answer_commercial_question(
                    project_id=project.id,
                    question=QUESTIONS[0],
                    mode="FAST",
                )
                measured_replay_ms = round((time.perf_counter() - replay_started) * 1000, 3)
                cache_benchmark = {
                    "configuration": "terra-medium-v2-representative",
                    "question": QUESTIONS[0],
                    "cold_status": cold.status.value,
                    "cold_latency_ms": cold.latency_ms,
                    "cold_cost_usd": str(cold.estimated_cost_usd),
                    "cold_external_request_executed": cold.external_request_executed,
                    "replay_status": warm.status.value,
                    "replay_latency_ms": warm.latency_ms,
                    "measured_wall_replay_ms": measured_replay_ms,
                    "replay_cache_hit": warm.cache_hit,
                    "replay_cost_usd": str(warm.estimated_cost_usd),
                    "replay_external_request_executed": warm.external_request_executed,
                    "evidence_version_invalidation": (
                        "Cache key includes the compact packet evidence_version and sanitized "
                        "conversation context; changed evidence produces a distinct key."
                    ),
                }
        engine.dispose()

    rows.sort(
        key=lambda row: (
            [item[0] for item in CONFIGURATIONS].index(row["configuration"]),
            QUESTIONS.index(row["question"]),
        )
    )
    report = {
        "eval_version": "commercial-analyst-eval-2.1",
        "live_provider_calls": args.live,
        "question_count": len(QUESTIONS),
        "configuration_count": len(CONFIGURATIONS),
        "evaluation_budget_ceiling_usd": str(args.evaluation_budget_usd),
        "production_budget_unchanged": True,
        "results": rows,
        "summary": _summary(rows),
        "cache_replay_benchmark": cache_benchmark,
        "rubric_note": (
            "Scores cover published deterministic answer-contract checks only; they are not human "
            "preference scores, probabilities, or proof of optimality."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "rows": len(rows), "live": args.live}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
