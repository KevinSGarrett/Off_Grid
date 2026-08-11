from __future__ import annotations

from typing import Any, Mapping, Protocol

from app.ai.types import FunctionCall, OpenAIResponseEnvelope, UsageMetrics


class OpenAITransport(Protocol):
    def create_response(self, request: Mapping[str, Any]) -> OpenAIResponseEnvelope: ...


class OfficialOpenAITransport:
    """Thin adapter around the official OpenAI Python SDK Responses API.

    The import is lazy so the deterministic application remains importable/runnable even when the
    optional provider SDK is unavailable and OPENAI_ENABLED=false.
    """

    def __init__(self, *, api_key: str, max_retries: int = 2, timeout_seconds: int = 45):
        if not api_key:
            raise ValueError("OpenAI API key is required for live transport")
        try:
            from openai import OpenAI
        except (ImportError, AttributeError) as exc:  # pragma: no cover - depends on runtime extras
            raise RuntimeError("Install the official `openai` Python package for live mode") from exc
        self.client = OpenAI(api_key=api_key, max_retries=max_retries, timeout=float(timeout_seconds))

    def create_response(self, request: Mapping[str, Any]) -> OpenAIResponseEnvelope:
        response = self.client.responses.create(**dict(request))
        output_items: list[dict[str, Any]] = []
        calls: list[FunctionCall] = []
        for item in getattr(response, "output", ()) or ():
            dumped = item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else dict(item)
            output_items.append(dumped)
            if dumped.get("type") == "function_call":
                calls.append(
                    FunctionCall(
                        call_id=str(dumped["call_id"]),
                        name=str(dumped["name"]),
                        arguments=str(dumped.get("arguments") or "{}"),
                    )
                )
        usage_obj = getattr(response, "usage", None)
        input_tokens = int(getattr(usage_obj, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage_obj, "output_tokens", 0) or 0)
        details = getattr(usage_obj, "input_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0)
        return OpenAIResponseEnvelope(
            response_id=getattr(response, "id", None),
            model_id=getattr(response, "model", None),
            output_text=str(getattr(response, "output_text", "") or ""),
            output_items=tuple(output_items),
            function_calls=tuple(calls),
            usage=UsageMetrics(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached,
            ),
        )
