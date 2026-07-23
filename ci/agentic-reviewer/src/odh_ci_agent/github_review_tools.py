"""In-process GitHub PR review tools (gh api) with MCP-aligned schemas."""

from __future__ import annotations

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
    "description": "Add a review comment to the current user's pending pull request review.",
    "properties": {
        "owner": {"type": "string", "description": "Repository owner."},
        "repo": {"type": "string", "description": "Repository name."},
        "pullNumber": {"type": "number", "description": "Pull request number."},
        "path": {"type": "string", "description": "Relative path to the commented file."},
        "body": {"type": "string", "description": "Review comment text."},
        "subjectType": {
            "type": "string",
            "description": "Comment target level.",
            "enum": ["FILE", "LINE"],
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

    def _find_pending_review_id(self, owner: str, repo: str, pull_number: int) -> int:
        reviews = gh_api_list_pages(self._pull_path(owner, repo, pull_number) + "/reviews", timeout=180)
        for review in reversed(reviews):
            if not isinstance(review, dict):
                continue
            if review.get("state") == "PENDING" and review.get("id") is not None:
                return int(review["id"])
        raise ValueError("No pending pull request review found for the current token")

    def _ensure_pending_review_id(self, owner: str, repo: str, pull_number: int) -> int:
        if self._pending_review_id is not None:
            return self._pending_review_id
        return self._find_pending_review_id(owner, repo, pull_number)

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
                lambda: self._create_pending_review(base_path, owner, repo, pull_number, args),
            )

        if method == "submit_pending":
            return self._record_invocation(
                "pull_request_review_write",
                method,
                lambda: self._submit_pending_review(base_path, owner, repo, pull_number, args),
            )

        if method == "delete_pending":
            review_id = self._ensure_pending_review_id(owner, repo, pull_number)
            return gh_api_json(f"{base_path}/reviews/{review_id}", method="DELETE")

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
        if args.get("body"):
            payload["body"] = args["body"]
        try:
            response = gh_api_json(f"{base_path}/reviews", method="POST", input_json=payload)
        except GitHubCommandError as exc:
            if "pending review" not in exc.stderr.lower():
                raise
            review_id = self._find_pending_review_id(owner, repo, pull_number)
            self._pending_review_id = review_id
            return {"id": review_id, "state": "PENDING", "reused": True}
        if isinstance(response, dict) and response.get("id") is not None:
            self._pending_review_id = int(response["id"])
        return response

    def _submit_pending_review(
        self,
        base_path: str,
        owner: str,
        repo: str,
        pull_number: int,
        args: dict[str, Any],
    ) -> object:
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

        def _post_comment() -> object:
            owner = str(args["owner"])
            repo = str(args["repo"])
            pull_number = int(args["pullNumber"])
            self._ensure_pending_review_id(owner, repo, pull_number)
            commit_id = self._head_commit_sha(owner, repo, pull_number)

            subject_type = str(args["subjectType"]).upper()
            payload: dict[str, object] = {
                "body": args["body"],
                "commit_id": commit_id,
                "path": args["path"],
            }
            if subject_type == "FILE":
                payload["subject_type"] = "file"
            else:
                payload.update(
                    {
                        "line": int(args["line"]),
                        "side": args.get("side", "RIGHT"),
                    }
                )
                if "startLine" in args:
                    payload["start_line"] = int(args["startLine"])
                if "startSide" in args:
                    payload["start_side"] = args["startSide"]

            return gh_api_json(
                f"{self._pull_path(owner, repo, pull_number)}/comments",
                method="POST",
                input_json=payload,
            )

        return self._record_invocation("add_comment_to_pending_review", None, _post_comment)

    def posting_failure_reason(self) -> str | None:
        """Return a failure reason when the agent tried but failed to post a review."""

        comment_attempts = [
            invocation
            for invocation in self.invocations
            if invocation.tool_name == "add_comment_to_pending_review"
        ]
        submit_attempts = [
            invocation
            for invocation in self.invocations
            if invocation.tool_name == "pull_request_review_write" and invocation.method == "submit_pending"
        ]

        if not comment_attempts:
            return None

        if not any(invocation.success for invocation in comment_attempts):
            return f"failed to post inline review comments ({len(comment_attempts)} attempt(s))"

        if not submit_attempts:
            return "posted inline comments but never submitted the pending review"

        if not any(invocation.success for invocation in submit_attempts):
            return "posted inline comments but failed to submit the pending review"

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
