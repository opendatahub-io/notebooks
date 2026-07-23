"""In-process GitHub PR review tools (gh api) with MCP-aligned schemas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from google.antigravity.hooks import policy
from google.antigravity.tools.tool_runner import ToolWithSchema

from odh_ci_agent.github_api import (
    GitHubCommandError,
    gh_api_diff,
    gh_api_json,
    gh_api_list_pages,
    split_repository,
)
from odh_ci_agent.mcp_github import GITHUB_REVIEW_TOOLS, PULL_REQUEST_READ_METHODS

_READ_METHOD_DESCRIPTION = (
    "Action to retrieve pull request data. "
    f"Valid values: {', '.join(PULL_REQUEST_READ_METHODS)}."
)

PULL_REQUEST_READ_SCHEMA = {
    "type": "object",
    "description": "Get information on a specific pull request.",
    "properties": {
        "method": {
            "type": "string",
            "description": _READ_METHOD_DESCRIPTION,
            "enum": list(PULL_REQUEST_READ_METHODS),
        },
        "owner": {"type": "string", "description": "Repository owner."},
        "repo": {"type": "string", "description": "Repository name."},
        "pullNumber": {"type": "number", "description": "Pull request number."},
        "page": {"type": "number", "description": "Page number for pagination (min 1).", "minimum": 1},
        "perPage": {
            "type": "number",
            "description": "Results per page for pagination (min 1, max 100).",
            "minimum": 1,
            "maximum": 100,
        },
    },
    "required": ["method"],
}

PULL_REQUEST_REVIEW_WRITE_SCHEMA = {
    "type": "object",
    "description": "Create and/or submit a pull request review.",
    "properties": {
        "method": {
            "type": "string",
            "description": "Write operation: create, submit_pending, or delete_pending.",
            "enum": ["create", "submit_pending", "delete_pending"],
        },
        "owner": {"type": "string", "description": "Repository owner."},
        "repo": {"type": "string", "description": "Repository name."},
        "pullNumber": {"type": "number", "description": "Pull request number."},
        "body": {"type": "string", "description": "Review comment text."},
        "event": {
            "type": "string",
            "description": "Review action when submitting.",
            "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
        },
    },
    "required": ["method"],
}

ADD_COMMENT_SCHEMA = {
    "type": "object",
    "description": "Stage a line-level review comment for the current user's pending pull request review.",
    "properties": {
        "owner": {"type": "string", "description": "Repository owner."},
        "repo": {"type": "string", "description": "Repository name."},
        "pullNumber": {"type": "number", "description": "Pull request number."},
        "path": {"type": "string", "description": "Relative path to the commented file."},
        "body": {"type": "string", "description": "Review comment text."},
        "subjectType": {
            "type": "string",
            "description": "Comment target level. Only LINE comments are supported in CI.",
            "enum": ["LINE"],
        },
        "line": {"type": "number", "description": "Diff line number for LINE comments."},
        "side": {
            "type": "string",
            "description": "Diff side for LINE comments.",
            "enum": ["LEFT", "RIGHT"],
        },
        "startLine": {"type": "number", "description": "First line for multi-line comments."},
        "startSide": {
            "type": "string",
            "description": "Starting diff side for multi-line comments.",
            "enum": ["LEFT", "RIGHT"],
        },
        "suggestion": {
            "type": "string",
            "description": "Optional replacement snippet rendered as a GitHub suggestion block.",
        },
    },
    "required": ["path", "body", "subjectType"],
}


@dataclass(frozen=True, slots=True)
class ReviewToolInvocation:
    """Recorded outcome of a mutating review tool call."""

    tool_name: str
    method: str | None
    success: bool
    error: str | None = None


def _with_pr_defaults(kwargs: dict[str, Any], repository: str, pull_number: int) -> dict[str, Any]:
    owner, repo = split_repository(repository)
    args = dict(kwargs)
    args.setdefault("owner", owner)
    args.setdefault("repo", repo)
    args.setdefault("pullNumber", pull_number)
    return args


@dataclass
class GitHubReviewClient:
    """Execute GitHub review operations via ``gh api``."""

    repository: str
    pull_number: int
    _pending_review_id: int | None = field(default=None, init=False)
    _head_commit_id: str | None = field(default=None, init=False)
    _authenticated_login: str | None = field(default=None, init=False)
    _draft_review_body: str | None = field(default=None, init=False)
    _draft_review_comments: list[dict[str, object]] = field(default_factory=list, init=False)
    invocations: list[ReviewToolInvocation] = field(default_factory=list, init=False)

    def _pull_path(self, owner: str, repo: str, pull_number: int) -> str:
        return f"repos/{owner}/{repo}/pulls/{pull_number}"

    def _record_invocation(
        self,
        tool_name: str,
        method: str | None,
        action: Any,
    ) -> object:
        try:
            result = action()
        except Exception as exc:
            self.invocations.append(
                ReviewToolInvocation(
                    tool_name=tool_name,
                    method=method,
                    success=False,
                    error=str(exc),
                )
            )
            raise
        self.invocations.append(ReviewToolInvocation(tool_name=tool_name, method=method, success=True))
        return result

    def _head_commit_sha(self, owner: str, repo: str, pull_number: int) -> str:
        if self._head_commit_id is not None:
            return self._head_commit_id
        pull = gh_api_json(self._pull_path(owner, repo, pull_number))
        if not isinstance(pull, dict):
            raise TypeError("Expected pull request response to be a JSON object")
        head_sha = pull.get("head", {}).get("sha")
        if not isinstance(head_sha, str) or not head_sha:
            raise ValueError("Pull request response did not include head.sha")
        self._head_commit_id = head_sha
        return head_sha

    def _clear_local_draft(self) -> None:
        self._draft_review_body = None
        self._draft_review_comments.clear()

    def _render_comment_body(self, body: str, suggestion: object | None) -> str:
        rendered_body = body.strip()
        if suggestion is None:
            return rendered_body
        rendered_suggestion = str(suggestion).strip("\n")
        if not rendered_suggestion:
            return rendered_body
        return f"{rendered_body}\n\n```suggestion\n{rendered_suggestion}\n```"

    def _stage_pending_review(self, args: dict[str, Any]) -> object:
        body = args.get("body")
        if isinstance(body, str) and body.strip():
            self._draft_review_body = body
        return {
            "state": "PENDING",
            "staged": True,
            "comment_count": len(self._draft_review_comments),
        }

    def pull_request_read(self, **kwargs: Any) -> object:
        args = _with_pr_defaults(kwargs, self.repository, self.pull_number)
        owner = str(args["owner"])
        repo = str(args["repo"])
        pull_number = int(args["pullNumber"])
        method = str(args["method"])
        base_path = self._pull_path(owner, repo, pull_number)

        if method == "get":
            return gh_api_json(base_path)
        if method == "get_diff":
            return gh_api_diff(base_path, timeout=180)
        if method == "get_files":
            query: dict[str, object] = {}
            if "page" in args:
                query["page"] = args["page"]
            if "perPage" in args:
                query["per_page"] = args["perPage"]
            return gh_api_list_pages(f"{base_path}/files", query=query or None, timeout=180)
        if method == "get_status":
            head_sha = self._head_commit_sha(owner, repo, pull_number)
            return gh_api_json(f"repos/{owner}/{repo}/commits/{head_sha}/status")
        if method == "get_commits":
            return gh_api_list_pages(f"{base_path}/commits", timeout=180)
        if method == "get_review_comments":
            return gh_api_list_pages(f"{base_path}/comments", timeout=180)
        if method == "get_reviews":
            return gh_api_list_pages(f"{base_path}/reviews", timeout=180)
        if method == "get_comments":
            return gh_api_list_pages(f"repos/{owner}/{repo}/issues/{pull_number}/comments", timeout=180)
        if method == "get_check_runs":
            head_sha = self._head_commit_sha(owner, repo, pull_number)
            return gh_api_json(
                f"repos/{owner}/{repo}/commits/{head_sha}/check-runs",
                query={"per_page": args.get("perPage", 100)},
            )
        raise ValueError(f"Unsupported pull_request_read method: {method}")

    def _current_user_login(self) -> str:
        if self._authenticated_login is None:
            user = gh_api_json("user")
            if not isinstance(user, dict) or not user.get("login"):
                raise TypeError("Expected GitHub user response to include login")
            self._authenticated_login = str(user["login"])
        return self._authenticated_login

    def _find_pending_review_id(self, owner: str, repo: str, pull_number: int) -> int:
        login = self._current_user_login()
        reviews = gh_api_list_pages(self._pull_path(owner, repo, pull_number) + "/reviews", timeout=180)
        for review in reversed(reviews):
            if not isinstance(review, dict):
                continue
            user = review.get("user")
            reviewer_login = user.get("login") if isinstance(user, dict) else None
            if (
                review.get("state") == "PENDING"
                and review.get("id") is not None
                and reviewer_login == login
            ):
                return int(review["id"])
        raise ValueError("No pending pull request review found for the current token")

    def _ensure_pending_review_id(self, owner: str, repo: str, pull_number: int) -> int:
        if self._pending_review_id is not None:
            return self._pending_review_id

        base_path = self._pull_path(owner, repo, pull_number)
        try:
            self._pending_review_id = self._find_pending_review_id(owner, repo, pull_number)
            return self._pending_review_id
        except ValueError:
            response = self._create_pending_review(base_path, owner, repo, pull_number, {})
            if isinstance(response, dict) and response.get("id") is not None:
                self._pending_review_id = int(response["id"])
            if self._pending_review_id is None:
                raise ValueError("Failed to create or reuse a pending pull request review")
            return self._pending_review_id

    def _delete_pending_review(self, base_path: str, review_id: int) -> object:
        response = gh_api_json(f"{base_path}/reviews/{review_id}", method="DELETE")
        self._pending_review_id = None
        return response

    def _is_pending_review_conflict(self, error: GitHubCommandError) -> bool:
        haystacks = (error.stdout.lower(), error.stderr.lower(), str(error).lower())
        return any("pending review" in haystack for haystack in haystacks)

    def pull_request_review_write(self, **kwargs: Any) -> object:
        args = _with_pr_defaults(kwargs, self.repository, self.pull_number)
        owner = str(args["owner"])
        repo = str(args["repo"])
        pull_number = int(args["pullNumber"])
        method = str(args["method"])
        base_path = self._pull_path(owner, repo, pull_number)

        if method == "create":
            return self._record_invocation(
                "pull_request_review_write",
                method,
                lambda: self._stage_pending_review(args),
            )

        if method == "submit_pending":
            return self._record_invocation(
                "pull_request_review_write",
                method,
                lambda: self._submit_pending_review(base_path, owner, repo, pull_number, args),
            )

        if method == "delete_pending":
            def _delete_pending() -> object:
                self._clear_local_draft()
                if self._pending_review_id is None:
                    return {"deleted": False, "staged": False}
                return self._delete_pending_review(base_path, self._pending_review_id)

            return self._record_invocation("pull_request_review_write", method, _delete_pending)

        raise ValueError(f"Unsupported pull_request_review_write method: {method}")

    def _create_pending_review(
        self,
        base_path: str,
        owner: str,
        repo: str,
        pull_number: int,
        args: dict[str, Any],
    ) -> object:
        payload: dict[str, object] = {}
        if self._draft_review_comments:
            payload["comments"] = list(self._draft_review_comments)
            payload["commit_id"] = self._head_commit_sha(owner, repo, pull_number)
        body = args.get("body")
        if isinstance(body, str) and body.strip():
            payload["body"] = body
        elif self._draft_review_body:
            payload["body"] = self._draft_review_body
        try:
            response = gh_api_json(f"{base_path}/reviews", method="POST", input_json=payload)
        except GitHubCommandError as exc:
            if not self._is_pending_review_conflict(exc):
                raise
            review_id = self._find_pending_review_id(owner, repo, pull_number)
            if self._draft_review_comments:
                self._delete_pending_review(base_path, review_id)
                response = gh_api_json(f"{base_path}/reviews", method="POST", input_json=payload)
            else:
                self._pending_review_id = review_id
                return {"id": review_id, "state": "PENDING", "reused": True}
        if isinstance(response, dict) and response.get("id") is not None:
            self._pending_review_id = int(response["id"])
            self._clear_local_draft()
        return response

    def _submit_pending_review(
        self,
        base_path: str,
        owner: str,
        repo: str,
        pull_number: int,
        args: dict[str, Any],
    ) -> object:
        if self._pending_review_id is None or self._draft_review_comments or self._draft_review_body:
            self._create_pending_review(base_path, owner, repo, pull_number, {})
        review_id = self._ensure_pending_review_id(owner, repo, pull_number)
        return gh_api_json(
            f"{base_path}/reviews/{review_id}/events",
            method="POST",
            input_json={
                "event": args.get("event", "COMMENT"),
                "body": args.get("body", ""),
            },
        )

    def add_comment_to_pending_review(self, **kwargs: Any) -> object:
        args = _with_pr_defaults(kwargs, self.repository, self.pull_number)

        def _stage_comment() -> object:
            payload: dict[str, object] = {
                "body": self._render_comment_body(str(args["body"]), args.get("suggestion")),
                "path": str(args["path"]),
                "line": int(args["line"]),
                "side": str(args.get("side", "RIGHT")).upper(),
            }
            if "startLine" in args:
                payload["start_line"] = int(args["startLine"])
            if "startSide" in args:
                payload["start_side"] = str(args["startSide"]).upper()
            self._draft_review_comments.append(payload)
            return {
                "staged": True,
                "comment_count": len(self._draft_review_comments),
            }

        return self._record_invocation("add_comment_to_pending_review", None, _stage_comment)

    def inline_comments_posted(self) -> bool:
        return (
            any(
                invocation.tool_name == "add_comment_to_pending_review" and invocation.success
                for invocation in self.invocations
            )
            and any(
                invocation.tool_name == "pull_request_review_write"
                and invocation.method == "submit_pending"
                and invocation.success
                for invocation in self.invocations
            )
        )

    def _first_error_snippet(self, invocations: list[ReviewToolInvocation]) -> str:
        for invocation in invocations:
            if not invocation.error:
                continue
            if '"errors":[' in invocation.error:
                array_match = re.search(r'"errors"\s*:\s*\[(.*?)\]', invocation.error, re.DOTALL)
                if array_match:
                    item_match = re.search(r'"([^"]+)"', array_match.group(1))
                    if item_match:
                        return item_match.group(1)[:160]
            if '"message":' in invocation.error:
                match = re.search(r'"message"\s*:\s*"([^"]+)"', invocation.error)
                if match:
                    return match.group(1)[:160]
            return invocation.error.splitlines()[0][:160]
        return ""

    def posting_failure_reason(self) -> str | None:
        """Return a failure reason when the agent tried but failed to post a review."""

        comment_attempts = [
            invocation
            for invocation in self.invocations
            if invocation.tool_name == "add_comment_to_pending_review"
        ]
        create_attempts = [
            invocation
            for invocation in self.invocations
            if invocation.tool_name == "pull_request_review_write" and invocation.method == "create"
        ]
        submit_attempts = [
            invocation
            for invocation in self.invocations
            if invocation.tool_name == "pull_request_review_write" and invocation.method == "submit_pending"
        ]

        if not comment_attempts and not create_attempts and not submit_attempts:
            return None

        if comment_attempts and not any(invocation.success for invocation in comment_attempts):
            detail = self._first_error_snippet([i for i in comment_attempts if not i.success])
            message = f"failed to post inline review comments ({len(comment_attempts)} attempt(s))"
            return f"{message}: {detail}" if detail else message

        if comment_attempts and any(invocation.success for invocation in comment_attempts):
            if not submit_attempts:
                return "staged inline comments but never submitted the pending review"
            if not any(invocation.success for invocation in submit_attempts):
                detail = self._first_error_snippet([i for i in submit_attempts if not i.success])
                message = "staged inline comments but failed to submit the pending review"
                return f"{message}: {detail}" if detail else message
            return None

        failed_writes = [
            invocation
            for invocation in self.invocations
            if invocation.tool_name in {"add_comment_to_pending_review", "pull_request_review_write"}
            and not invocation.success
        ]
        if failed_writes:
            first = failed_writes[0]
            label = first.tool_name if first.method is None else f"{first.tool_name}({first.method})"
            detail = self._first_error_snippet(failed_writes)
            message = f"GitHub review tool {label} failed"
            return f"{message}: {detail}" if detail else message

        return None


def make_github_review_tools(
    repository: str,
    pull_number: int,
) -> tuple[list[ToolWithSchema], GitHubReviewClient]:
    client = GitHubReviewClient(repository=repository, pull_number=pull_number)
    tools = [
        ToolWithSchema(client.pull_request_read, PULL_REQUEST_READ_SCHEMA),
        ToolWithSchema(client.pull_request_review_write, PULL_REQUEST_REVIEW_WRITE_SCHEMA),
        ToolWithSchema(client.add_comment_to_pending_review, ADD_COMMENT_SCHEMA),
    ]
    return tools, client


def review_tool_policies() -> list[policy.Policy]:
    return [policy.deny_all(), *[policy.allow(tool_name) for tool_name in GITHUB_REVIEW_TOOLS]]
