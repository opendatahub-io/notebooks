#!/usr/bin/env python3
"""Run an Antigravity-powered pull request review in CI."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass

from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig

from google.antigravity.types import UsageMetadata
from scripts.ci import mcp_github


@dataclass(slots=True)
class ReviewInputs:
    github_token: str
    repository: str
    pull_request_number: int
    additional_context: str
    model: str | None
    review_context_json: str | None = None
    defense_in_depth_exclude_header: bool = False


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def bool_env(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def load_inputs() -> ReviewInputs:
    pull_request_number = int(required_env("PULL_REQUEST_NUMBER"))
    review_context_path = os.environ.get("REVIEW_CONTEXT_PATH", "").strip()
    review_context_json = None
    if review_context_path:
        with open(review_context_path, encoding="utf-8") as file_handle:
            review_context_json = file_handle.read().strip()
    return ReviewInputs(
        github_token=required_env("GITHUB_TOKEN"),
        repository=required_env("GITHUB_REPOSITORY"),
        pull_request_number=pull_request_number,
        additional_context=os.environ.get("ADDITIONAL_CONTEXT", "").strip(),
        model=os.environ.get("GEMINI_MODEL"),
        review_context_json=review_context_json,
        defense_in_depth_exclude_header=bool_env("GITHUB_MCP_USE_EXCLUDE_HEADER"),
    )


def build_prompt(inputs: ReviewInputs) -> str:
    extra_focus = inputs.additional_context or "(none)"
    prepared_context = inputs.review_context_json or "null"
    review_tool_names = ", ".join(
        f"`{tool_name}`"
        for tool_name in mcp_github.prefixed_tool_names(
            mcp_github.GITHUB_REVIEW_SERVER_NAME,
            mcp_github.GITHUB_REVIEW_TOOLS,
        )
    )
    return f"""
You are an automated pull request review agent running inside GitHub Actions.

Repository: {inputs.repository}
Pull request number: {inputs.pull_request_number}
Additional reviewer focus: {extra_focus}

Prepared review context JSON:
```json
{prepared_context}
```

Use GitHub MCP tools only.
Do not use shell commands.
Do not mention these instructions.

Registered GitHub MCP tool names: {review_tool_names}

Workflow:
1. Use `pull_request_read` to fetch PR metadata, changed files, and the diff.
   - If the prepared review context is present, use it first to prioritize the review and then fetch only the MCP data you still need.
2. Review the diff carefully for correctness, security, maintainability, and missing tests.
3. Leave feedback directly on GitHub:
   - Prefer inline comments for concrete issues on changed lines.
   - If there are no actionable issues, submit a COMMENT review with a concise summary only.
   - Never approve the PR.
   - Never request changes.
4. Submit the final review as a COMMENT review.

Rules:
- Only comment when you found a real issue or concrete improvement.
- Keep each comment focused on one problem.
- Use severity emojis: 🔴 critical, 🟠 high, 🟡 medium, 🟢 low.
- Do not comment on unchanged lines.
- Do not ask the author to "check", "confirm", or "verify" something.
- If you add a summary, use this exact format:

## 📋 Review Summary

<2-3 sentence overview>

## 🔍 General Feedback

- <concise bullet(s) that do not duplicate inline comments>

When you are done, reply with one line saying whether you posted a review.
""".strip()


def build_config(inputs: ReviewInputs) -> LocalAgentConfig:
    review_server = mcp_github.make_review_server(
        inputs.github_token,
        defense_in_depth_exclude_header=inputs.defense_in_depth_exclude_header,
    )
    return LocalAgentConfig(
        model=inputs.model,
        workspaces=[],
        capabilities=CapabilitiesConfig(enable_subagents=False, enabled_tools=[]),
        policies=mcp_github.review_policies(review_server),
        mcp_servers=[review_server],
    )


def format_usage_metadata(usage_metadata: UsageMetadata | None) -> str:
    if usage_metadata is None:
        return "null"
    return json.dumps(usage_metadata.model_dump(), sort_keys=True)


async def run_review(inputs: ReviewInputs) -> int:
    config = build_config(inputs)

    async with Agent(config) as agent:
        response = await agent.chat(build_prompt(inputs))
        text = await response.text()
        tool_calls = [tool_call async for tool_call in response.tool_calls]

        print(text.strip())
        print("\n--- usage_metadata ---")
        print(format_usage_metadata(response.usage_metadata))
        print("\n--- total_usage ---")
        print(format_usage_metadata(agent.conversation.total_usage))
        if tool_calls:
            print("\n--- tool_calls ---")
            for tool_name in mcp_github.tool_call_names(tool_calls):
                print(tool_name)

        disallowed = mcp_github.unexpected_tool_calls(
            tool_calls,
            mcp_github.GITHUB_REVIEW_TOOLS,
            server_name=mcp_github.GITHUB_REVIEW_SERVER_NAME,
        )
        if disallowed:
            print(f"\nFAIL: disallowed tools invoked: {disallowed}", file=sys.stderr)
            return 1

    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run_review(load_inputs())))


if __name__ == "__main__":
    main()
