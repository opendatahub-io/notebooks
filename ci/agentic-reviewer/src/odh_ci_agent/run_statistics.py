"""Build parseable Antigravity run statistics with optional Gemini cost estimates."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from google.antigravity.types import UsageMetadata

SCHEMA_VERSION = 1
DEFAULT_STATISTICS_PATH = "agy-run-statistics.json"

# Standard-tier USD per 1M tokens from https://ai.google.dev/gemini-api/docs/pricing
# (text/image/video input rates; audio-specific tiers are not modeled).
PRICING_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
PRICING_AS_OF = "2026-07-24"


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_usd_per_million_tokens: float
    cached_input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float
    display_name: str


GEMINI_FLASH_MODEL_PRICING: dict[str, ModelPricing] = {
    "gemini-3.5-flash": ModelPricing(
        input_usd_per_million_tokens=1.50,
        cached_input_usd_per_million_tokens=0.15,
        output_usd_per_million_tokens=9.00,
        display_name="Gemini 3.5 Flash",
    ),
    "gemini-3.1-flash-lite": ModelPricing(
        input_usd_per_million_tokens=0.25,
        cached_input_usd_per_million_tokens=0.025,
        output_usd_per_million_tokens=1.50,
        display_name="Gemini 3.1 Flash-Lite",
    ),
    "gemini-2.5-flash": ModelPricing(
        input_usd_per_million_tokens=0.30,
        cached_input_usd_per_million_tokens=0.03,
        output_usd_per_million_tokens=2.50,
        display_name="Gemini 2.5 Flash",
    ),
    "gemini-2.5-flash-lite": ModelPricing(
        input_usd_per_million_tokens=0.10,
        cached_input_usd_per_million_tokens=0.01,
        output_usd_per_million_tokens=0.40,
        display_name="Gemini 2.5 Flash-Lite",
    ),
}


def normalize_model_id(model: str | object | None) -> str | None:
    if model is None:
        return None
    if not isinstance(model, str):
        model = str(model)
    normalized = model.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("models/"):
        normalized = normalized.removeprefix("models/")
    return normalized


def lookup_model_pricing(model: str | object | None) -> ModelPricing | None:
    normalized = normalize_model_id(model)
    if not normalized:
        return None

    if normalized in GEMINI_FLASH_MODEL_PRICING:
        return GEMINI_FLASH_MODEL_PRICING[normalized]

    for model_id, pricing in sorted(GEMINI_FLASH_MODEL_PRICING.items(), key=lambda item: len(item[0]), reverse=True):
        if normalized.startswith(model_id):
            return pricing
    return None


def usage_metadata_to_dict(usage_metadata: UsageMetadata | None) -> dict[str, int | None]:
    if usage_metadata is None:
        return {
            "cached_content_token_count": None,
            "candidates_token_count": None,
            "prompt_token_count": None,
            "thoughts_token_count": None,
            "total_token_count": None,
        }
    dumped = usage_metadata.model_dump()
    return {
        "cached_content_token_count": _int_or_none(dumped.get("cached_content_token_count")),
        "candidates_token_count": _int_or_none(dumped.get("candidates_token_count")),
        "prompt_token_count": _int_or_none(dumped.get("prompt_token_count")),
        "thoughts_token_count": _int_or_none(dumped.get("thoughts_token_count")),
        "total_token_count": _int_or_none(dumped.get("total_token_count")),
    }


def format_usage_metadata(usage_metadata: UsageMetadata | None) -> str:
    if usage_metadata is None:
        return "null"
    return json.dumps(usage_metadata_to_dict(usage_metadata), sort_keys=True)


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _token_counts(usage: Mapping[str, int | None]) -> tuple[int, int, int]:
    prompt_tokens = usage.get("prompt_token_count") or 0
    cached_tokens = usage.get("cached_content_token_count") or 0
    output_tokens = (usage.get("candidates_token_count") or 0) + (usage.get("thoughts_token_count") or 0)
    billable_input_tokens = max(0, prompt_tokens - cached_tokens)
    return billable_input_tokens, cached_tokens, output_tokens


def estimate_cost_usd(usage: Mapping[str, int | None], pricing: ModelPricing) -> dict[str, float | None]:
    billable_input_tokens, cached_tokens, output_tokens = _token_counts(usage)
    if not any((billable_input_tokens, cached_tokens, output_tokens)):
        return {
            "billable_input_tokens": float(billable_input_tokens),
            "cached_input_tokens": float(cached_tokens),
            "output_tokens": float(output_tokens),
            "input_usd": 0.0,
            "cached_input_usd": 0.0,
            "output_usd": 0.0,
            "total_usd": 0.0,
        }

    input_usd = billable_input_tokens * pricing.input_usd_per_million_tokens / 1_000_000
    cached_input_usd = cached_tokens * pricing.cached_input_usd_per_million_tokens / 1_000_000
    output_usd = output_tokens * pricing.output_usd_per_million_tokens / 1_000_000
    total_usd = input_usd + cached_input_usd + output_usd
    return {
        "billable_input_tokens": float(billable_input_tokens),
        "cached_input_tokens": float(cached_tokens),
        "output_tokens": float(output_tokens),
        "input_usd": round(input_usd, 6),
        "cached_input_usd": round(cached_input_usd, 6),
        "output_usd": round(output_usd, 6),
        "total_usd": round(total_usd, 6),
    }


def summarize_tool_calls(tool_names: Sequence[str]) -> dict[str, Any]:
    counts = Counter(tool_names)
    return {
        "total_calls": len(tool_names),
        "unique_tools": len(counts),
        "by_name": dict(sorted(counts.items())),
    }


def build_run_statistics(
    *,
    run_kind: str,
    model: str | object | None,
    turn_usage: UsageMetadata | None,
    conversation_usage: UsageMetadata | None,
    tool_names: Iterable[str],
    conversation_id: str | None,
    agent_succeeded: bool,
    failure_reason: str | None = None,
    metadata: Mapping[str, object] | None = None,
    review_outcome: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    normalized_model = normalize_model_id(model)
    pricing = lookup_model_pricing(model)
    turn_usage_dict = usage_metadata_to_dict(turn_usage)
    conversation_usage_dict = usage_metadata_to_dict(conversation_usage)
    tool_summary = summarize_tool_calls(list(tool_names))

    cost_block: dict[str, Any] = {
        "estimate_available": pricing is not None,
        "pricing_source": PRICING_SOURCE if pricing is not None else None,
        "pricing_as_of": PRICING_AS_OF if pricing is not None else None,
        "turn": estimate_cost_usd(turn_usage_dict, pricing) if pricing is not None else None,
        "conversation_total": estimate_cost_usd(conversation_usage_dict, pricing) if pricing is not None else None,
        "total_usd": None,
    }
    if pricing is not None and cost_block["conversation_total"] is not None:
        cost_block["total_usd"] = cost_block["conversation_total"]["total_usd"]
    elif pricing is None:
        cost_block["total_usd"] = "n/a"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "run_kind": run_kind,
        "agent_succeeded": agent_succeeded,
        "failure_reason": failure_reason,
        "conversation_id": conversation_id,
        "model": {
            "configured_id": model,
            "normalized_id": normalized_model,
            "pricing_available": pricing is not None,
            "display_name": pricing.display_name if pricing is not None else None,
            "input_usd_per_million_tokens": pricing.input_usd_per_million_tokens if pricing is not None else None,
            "cached_input_usd_per_million_tokens": (
                pricing.cached_input_usd_per_million_tokens if pricing is not None else None
            ),
            "output_usd_per_million_tokens": pricing.output_usd_per_million_tokens if pricing is not None else None,
        },
        "usage": {
            "turn": turn_usage_dict,
            "conversation_total": conversation_usage_dict,
        },
        "cost_usd": cost_block,
        "tools": tool_summary,
        "github": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "github_run_id": _positive_int_env("GITHUB_RUN_ID"),
            "workflow_run_id": _positive_int_env("WORKFLOW_RUN_ID"),
        },
        "metadata": dict(metadata or {}),
    }
    if review_outcome is not None:
        report["review"] = dict(review_outcome)
    return report


def write_run_statistics(path: str, report: Mapping[str, object]) -> None:
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(report, file_handle, indent=2, sort_keys=True)
        file_handle.write("\n")


def persist_run_statistics(report: Mapping[str, object]) -> str:
    path = os.environ.get("AGY_RUN_STATISTICS_PATH", DEFAULT_STATISTICS_PATH).strip() or DEFAULT_STATISTICS_PATH
    write_run_statistics(path, report)
    append_github_step_summary(report)
    return path


def append_github_step_summary(report: Mapping[str, object]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return

    model = report.get("model")
    cost = report.get("cost_usd")
    tools = report.get("tools")
    usage = report.get("usage")
    if (
        not isinstance(model, dict)
        or not isinstance(cost, dict)
        or not isinstance(tools, dict)
        or not isinstance(usage, dict)
    ):
        return

    conversation_usage = usage.get("conversation_total")
    total_usd = cost.get("total_usd")
    total_usd_display = "n/a" if total_usd == "n/a" or total_usd is None else f"${total_usd:.6f}"

    lines = [
        "## Antigravity run statistics",
        "",
        f"- **Run kind:** `{report.get('run_kind', 'unknown')}`",
        f"- **Model:** `{model.get('configured_id') or 'unknown'}`",
        f"- **Estimated cost (USD):** {total_usd_display}",
        f"- **Tool calls:** {tools.get('total_calls', 0)}",
    ]
    if isinstance(conversation_usage, dict):
        lines.append(f"- **Conversation tokens:** {conversation_usage.get('total_token_count', 'n/a')}")
    if report.get("conversation_id"):
        lines.append(f"- **Conversation id:** `{report['conversation_id']}`")
    if isinstance(cost, dict) and cost.get("estimate_available") is False:
        lines.append("- **Cost note:** pricing table has no entry for this model")
    review = report.get("review")
    if isinstance(review, dict):
        lines.append(f"- **Inline comments staged:** {review.get('inline_comments_staged', 'n/a')}")
        lines.append(f"- **Inline comments posted:** {review.get('inline_comments_posted', 'n/a')}")
    lines.append("")
    artifact_name = f"antigravity-run-statistics-{os.environ.get('GITHUB_RUN_ID', 'local')}.json"
    lines.append(f"Full JSON report uploaded as artifact `{artifact_name}` (`agy-run-statistics.json`).")
    lines.append("")

    with open(summary_path, "a", encoding="utf-8") as file_handle:
        file_handle.write("\n".join(lines))


def print_run_statistics(report: Mapping[str, object]) -> None:
    print("--- run_statistics ---")
    print(json.dumps(report, indent=2, sort_keys=True))


def record_agent_run(
    *,
    run_kind: str,
    model: str | object | None,
    turn_usage: UsageMetadata | None,
    conversation_usage: UsageMetadata | None,
    tool_names: Iterable[str],
    conversation_id: str | None,
    agent_succeeded: bool,
    failure_reason: str | None = None,
    metadata: Mapping[str, object] | None = None,
    review_outcome: Mapping[str, object] | None = None,
) -> str:
    report = build_run_statistics(
        run_kind=run_kind,
        model=model,
        turn_usage=turn_usage,
        conversation_usage=conversation_usage,
        tool_names=tool_names,
        conversation_id=conversation_id,
        agent_succeeded=agent_succeeded,
        failure_reason=failure_reason,
        metadata=metadata,
        review_outcome=review_outcome,
    )
    path = persist_run_statistics(report)
    print_run_statistics(report)
    return path


def _positive_int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return None
