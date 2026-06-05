#!/usr/bin/env python3
"""Generate the Antigravity CI summary comment body."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping

from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig

from google.antigravity.types import UsageMetadata
from scripts.ci import mcp_github
from scripts.ci.ci_summary import (
    string_list,
    int_value,
    marker_for_run,
    render_failure_comment,
    render_final_success_comment,
    render_progress_comment,
)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_context(path: str) -> dict[str, object]:
    with open(path, encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    if not isinstance(data, dict):
        raise SystemExit("CI run context must be a JSON object")
    return data


def format_usage_metadata(usage_metadata: UsageMetadata | None) -> str:
    if usage_metadata is None:
        return "null"
    return json.dumps(usage_metadata.model_dump(), sort_keys=True)


def should_enable_actions_fallback(context: Mapping[str, object]) -> bool:
    if bool_env("GITHUB_ACTIONS_MCP_FALLBACK"):
        return True
    failed_jobs = context.get("failed_jobs", [])
    if not isinstance(failed_jobs, list):
        return False

    def has_grounding(failed_job: Mapping[str, object]) -> bool:
        # Keep this explicit rather than relying on generic truthiness so it is clear
        # which local evidence sources suppress the MCP fallback.
        has_excerpt = bool(failed_job.get("log_excerpt") or failed_job.get("log_tail"))
        has_error_contexts = len(string_list(failed_job.get("error_contexts"))) > 0
        return has_excerpt or has_error_contexts

    return any(
        not has_grounding(failed_job)
        for failed_job in failed_jobs
        if isinstance(failed_job, dict)
    )


def build_config(context: Mapping[str, object]) -> LocalAgentConfig:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    mcp_servers = []
    policies = []
    if token and should_enable_actions_fallback(context):
        actions_server = mcp_github.make_actions_readonly_server(token)
        mcp_servers.append(actions_server)
        policies.extend(mcp_github.actions_read_policies(actions_server))

    return LocalAgentConfig(
        model=os.environ.get("GEMINI_MODEL"),
        workspaces=[],
        capabilities=CapabilitiesConfig(enable_subagents=False, enabled_tools=[]),
        policies=policies,
        mcp_servers=mcp_servers,
    )


def build_prompt(context: Mapping[str, object]) -> str:
    mode = context["mode"]
    actions_tool_names = ", ".join(
        f"`{tool_name}`"
        for tool_name in mcp_github.prefixed_tool_names(
            mcp_github.GITHUB_ACTIONS_SERVER_NAME,
            mcp_github.GITHUB_ACTIONS_READ_TOOLS,
        )
    )
    return f"""
You are generating only the analysis section for a GitHub pull request CI summary comment.

Output only markdown for these sections:
- `### Likely root causes`
- `### Suggested next steps`

Do not output the run title, status line, tables, job links, durations, or the hidden HTML marker.
Do not wrap your answer in code fences.
If you use GitHub Actions MCP tools, do so only to fill log gaps for failed jobs already listed in the context.
Registered GitHub Actions MCP tool names: {actions_tool_names}

Comment style:
- Be concise and actionable.
- When mode is `failure`, focus on failures so far and what likely groups together.
- When mode is `final` and there are failures, produce a consolidated failure digest.
- Use only facts that exist in the provided context or MCP fallback results.
- Do not invent run numbers, durations, counts, or additional links.
- Do not describe jobs as cancelled unless the context explicitly says their `conclusion` is `cancelled`.
- Do not mention workflow settings such as `fail-fast`, retries, permissions, or runner behavior unless those words appear in the provided context or fetched logs.
- If the evidence is insufficient for a root cause, say that the evidence is insufficient instead of guessing.
- Use `failed_jobs[*].log_excerpt` as the primary failed-step evidence and `failed_jobs[*].error_contexts` as corroborating whole-job anchor windows.
- Say "likely" for inferred root causes.

Context JSON:
{json.dumps(context, indent=2, sort_keys=True)}

Mode: {mode}
""".strip()


def write_body(path: str, body: str) -> None:
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(body.rstrip() + "\n")


async def summarize(context: Mapping[str, object], body_path: str) -> int:
    failed_jobs = context.get("failed_jobs", [])
    if not isinstance(failed_jobs, list):
        raise SystemExit("CI run context is missing a failed_jobs list")

    if context["mode"] == "progress":
        write_body(body_path, render_progress_comment(context))
        return 0
    if context["mode"] == "final" and not failed_jobs:
        write_body(body_path, render_final_success_comment(context))
        return 0

    config = build_config(context)
    if not config.mcp_servers and not os.environ.get("GEMINI_API_KEY", "").strip():
        raise SystemExit("Missing GEMINI_API_KEY for CI summarization")

    async with Agent(config) as agent:
        response = await agent.chat(build_prompt(context))
        text = await response.text()
        tool_calls = [tool_call async for tool_call in response.tool_calls]

        write_body(body_path, render_failure_comment(context, text))

        print("--- usage_metadata ---")
        print(format_usage_metadata(response.usage_metadata))
        print("--- total_usage ---")
        print(format_usage_metadata(agent.conversation.total_usage))
        if tool_calls:
            print("--- tool_calls ---")
            for tool_name in mcp_github.tool_call_names(tool_calls):
                print(tool_name)

        allowed_tools = mcp_github.GITHUB_ACTIONS_READ_TOOLS
        disallowed = mcp_github.unexpected_tool_calls(
            tool_calls,
            allowed_tools,
            server_name=mcp_github.GITHUB_ACTIONS_SERVER_NAME,
        )
        if disallowed:
            print(f"FAIL: disallowed tools invoked: {disallowed}", file=sys.stderr)
            return 1

    return 0


def main() -> None:
    context_path = required_env("CI_RUN_CONTEXT_PATH")
    body_path = os.environ.get("COMMENT_BODY_PATH", "ci-comment-body.md")
    context = load_context(context_path)
    progress = context.get("progress")
    if not isinstance(progress, Mapping):
        raise SystemExit("CI run context is missing a progress mapping")

    marker = marker_for_run(
        int_value(context["workflow_run_id"]),
        failed_jobs=int_value(progress["failed"]),
        updated_at=str(context["updated_at"]),
    )
    context["comment_marker"] = marker

    raise SystemExit(asyncio.run(summarize(context, body_path)))


if __name__ == "__main__":
    main()
