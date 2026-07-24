from __future__ import annotations

from odh_ci_agent import run_statistics


def test_lookup_model_pricing_matches_gemini_35_flash() -> None:
    pricing = run_statistics.lookup_model_pricing("models/gemini-3.5-flash")

    assert pricing is not None
    assert pricing.input_usd_per_million_tokens == 1.50
    assert pricing.output_usd_per_million_tokens == 9.00


def test_lookup_model_pricing_matches_gemini_31_flash_lite() -> None:
    pricing = run_statistics.lookup_model_pricing("gemini-3.1-flash-lite")

    assert pricing is not None
    assert pricing.input_usd_per_million_tokens == 0.25
    assert pricing.output_usd_per_million_tokens == 1.50


def test_lookup_model_pricing_returns_none_for_unknown_model() -> None:
    assert run_statistics.lookup_model_pricing("gemini-unknown-model") is None


def test_estimate_cost_usd_accounts_for_cached_and_output_tokens() -> None:
    pricing = run_statistics.lookup_model_pricing("gemini-3.5-flash")
    assert pricing is not None

    cost = run_statistics.estimate_cost_usd(
        {
            "prompt_token_count": 1_000_000,
            "cached_content_token_count": 200_000,
            "candidates_token_count": 100_000,
            "thoughts_token_count": 50_000,
            "total_token_count": 1_350_000,
        },
        pricing,
    )

    assert cost["billable_input_tokens"] == 800_000.0
    assert cost["cached_input_tokens"] == 200_000.0
    assert cost["output_tokens"] == 150_000.0
    assert cost["input_usd"] == 1.2
    assert cost["cached_input_usd"] == 0.03
    assert cost["output_usd"] == 1.35
    assert cost["total_usd"] == 2.58


def test_build_run_statistics_marks_unknown_model_cost_as_na() -> None:
    report = run_statistics.build_run_statistics(
        run_kind="ci-summary",
        model="gemini-unknown",
        turn_usage=None,
        conversation_usage=None,
        tool_names=["view_file", "view_file"],
        conversation_id="abc123",
        agent_succeeded=True,
    )

    assert report["model"]["pricing_available"] is False
    assert report["cost_usd"]["estimate_available"] is False
    assert report["cost_usd"]["total_usd"] == "n/a"
    assert report["tools"]["total_calls"] == 2
    assert report["tools"]["by_name"] == {"view_file": 2}


def test_write_and_persist_run_statistics(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "agy-run-statistics.json"
    summary_path = tmp_path / "step-summary.md"
    monkeypatch.setenv("AGY_RUN_STATISTICS_PATH", str(output_path))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("GITHUB_RUN_ID", "42")

    report = run_statistics.build_run_statistics(
        run_kind="pr-review",
        model="gemini-3.1-flash-lite",
        turn_usage=None,
        conversation_usage=None,
        tool_names=[],
        conversation_id="deadbeef",
        agent_succeeded=True,
        metadata={"pull_request_number": 99},
    )

    written_path = run_statistics.persist_run_statistics(report)

    assert written_path == str(output_path)
    assert output_path.exists()
    summary = summary_path.read_text(encoding="utf-8")
    assert "Antigravity run statistics" in summary
    assert "gemini-3.1-flash-lite" in summary
