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
from odh_ci_agent.review_diff_lines import DiffLineIndex

_READ_METHOD_DESCRIPTION = (
    f"Action to retrieve pull request data. Valid values: {', '.join(PULL_REQUEST_READ_METHODS)}."
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
    "description": (
        "Stage or submit a pull request review. "
        "`create` only stages a pending review body locally. "
        "`submit_pending` sends all staged inline comments in one GitHub review."
    ),
    "properties": {
        "method": {
            "type": "string",
            "description": (
                "Write operation: create, submit_pending, or delete_pending. "
                "`submit_pending` is the step that actually creates and submits the GitHub review."
            ),
            "enum": ["create", "submit_pending", "delete_pending"],
        },
        "owner": {"type": "string", "description": "Repository owner."},
        "repo": {"type": "string", "description": "Repository name."},
        "pullNumber": {"type": "number", "description": "Pull request number."},
        "body": {"type": "string", "description": "Review comment text."},
        "event": {
            "type": "string",
            "description": (
                "Review action when submitting. CI only supports COMMENT; "
                "APPROVE and REQUEST_CHANGES are coerced to COMMENT."
            ),
            "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
        },
    },
    "required": ["method"],
}

ADD_COMMENT_SCHEMA = {
    "type": "object",
    "description": (
        "Stage one line-level review comment locally for the current user's pending pull request review. "
        'The comment is posted to GitHub only when `pull_request_review_write(method="submit_pending")` runs.'
    ),
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
        "line": {
            "type": "number",
            "description": "Line number in the pull request head file (RIGHT) or base file (LEFT) on a changed +/- diff line.",
        },
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
    args["owner"] = owner
    args["repo"] = repo
    args["pullNumber"] = pull_number
    return args


@dataclass
class GitHubReviewClient:
    """Execute GitHub review operations via ``gh api``."""

    repository: str
    pull_number: int
    _pending_review_id: int | None = field(default=None, init=False)
    _head_commit_id: str | None = field(default=None, init=False)
    _authenticated_login: str | None = field(default=None, init=False)
    _authenticated_login_unavailable: bool = field(default=False, init=False)
    _draft_review_body: str | None = field(default=None, init=False)
    _draft_review_comments: list[dict[str, object]] = field(default_factory=list, init=False)
    _diff_line_index: DiffLineIndex | None = field(default=None, init=False)
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

    def _load_diff_line_index(self, owner: str, repo: str, pull_number: int) -> DiffLineIndex:
        if self._diff_line_index is not None:
            return self._diff_line_index
        files = gh_api_list_pages(f"{self._pull_path(owner, repo, pull_number)}/files", timeout=180)
        self._diff_line_index = DiffLineIndex.from_pull_files(files)
        return self._diff_line_index

    @staticmethod
    def _comment_dedupe_key(payload: dict[str, object]) -> tuple[object, ...]:
        return (
            payload["path"],
            payload["line"],
            payload.get("start_line"),
            payload["side"],
            payload["body"],
        )

    def _validate_staged_comment(
        self,
        index: DiffLineIndex,
        payload: dict[str, object],
    ) -> None:
        path = str(payload["path"])
        line = int(str(payload["line"]))
        side = str(payload["side"])
        start_line_raw = payload.get("start_line")
        start_line = int(str(start_line_raw)) if start_line_raw is not None else None
        error = index.validate_comment(path=path, line=line, side=side, start_line=start_line)
        if error:
            raise ValueError(error)

    def _validated_draft_comments(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        if not self._draft_review_comments:
            return []
        index = self._load_diff_line_index(owner, repo, pull_number)
        validated: list[dict[str, object]] = []
        for comment in self._draft_review_comments:
            self._validate_staged_comment(index, comment)
            validated.append(dict(comment))
        return validated

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

    def _is_integration_user_lookup_denied(self, error: GitHubCommandError) -> bool:
        haystacks = (error.stdout.lower(), error.stderr.lower(), str(error).lower())
        return any("resource not accessible by integration" in haystack for haystack in haystacks)

    def _current_user_login(self) -> str | None:
        if self._authenticated_login is None and not self._authenticated_login_unavailable:
            try:
                user = gh_api_json("user")
            except GitHubCommandError as exc:
                if self._is_integration_user_lookup_denied(exc):
                    self._authenticated_login_unavailable = True
                    return None
                raise
            if not isinstance(user, dict) or not user.get("login"):
                raise TypeError("Expected GitHub user response to include login")
            self._authenticated_login = str(user["login"])
        return self._authenticated_login

    def _coerce_review_id(self, review_id: object) -> int:
        if isinstance(review_id, int):
            return review_id
        if isinstance(review_id, str) and review_id.isdigit():
            return int(review_id)
        raise TypeError(f"Expected review id to be int-like, got {review_id!r}")

    def _find_pending_review_id(self, owner: str, repo: str, pull_number: int) -> int:
        login = self._current_user_login()
        reviews = gh_api_list_pages(self._pull_path(owner, repo, pull_number) + "/reviews", timeout=180)
        pending_reviews: list[dict[str, object]] = []
        for review in reversed(reviews):
            if not isinstance(review, dict):
                continue
            if review.get("state") != "PENDING" or review.get("id") is None:
                continue
            user = review.get("user")
            reviewer_login = user.get("login") if isinstance(user, dict) else None
            pending_reviews.append(review)
            if login is not None and reviewer_login == login:
                return int(review["id"])
        if login is None:
            bot_pending_review_ids: list[int] = []
            for pending_review in pending_reviews:
                pending_user = pending_review.get("user")
                pending_login = pending_user.get("login") if isinstance(pending_user, dict) else None
                pending_review_id = pending_review.get("id")
                if isinstance(pending_login, str) and pending_login.endswith("[bot]") and pending_review_id is not None:
                    bot_pending_review_ids.append(self._coerce_review_id(pending_review_id))
            if len(bot_pending_review_ids) == 1:
                return bot_pending_review_ids[0]
            if len(pending_reviews) == 1:
                pending_review_id = pending_reviews[0].get("id")
                if pending_review_id is not None:
                    return self._coerce_review_id(pending_review_id)
        raise ValueError("No pending pull request review found for the current token")

    def _ensure_pending_review_id(self, owner: str, repo: str, pull_number: int) -> int:
        if self._pending_review_id is not None:
            return self._pending_review_id

        base_path = self._pull_path(owner, repo, pull_number)
        try:
            self._pending_review_id = self._find_pending_review_id(owner, repo, pull_number)
            return self._pending_review_id
        except ValueError as err:
            response = self._create_pending_review(base_path, owner, repo, pull_number, {})
            if isinstance(response, dict) and response.get("id") is not None:
                self._pending_review_id = int(response["id"])
            if self._pending_review_id is None:
                raise ValueError("Failed to create or reuse a pending pull request review") from err
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
        validated_comments = self._validated_draft_comments(owner, repo, pull_number)
        if validated_comments:
            payload["comments"] = validated_comments
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

    def _review_submit_body(self, args: dict[str, Any]) -> str:
        body = args.get("body")
        if isinstance(body, str) and body.strip():
            return body.strip()
        if self._draft_review_body and self._draft_review_body.strip():
            return self._draft_review_body.strip()
        return ""

    def _coerce_review_submit_event(self, event: object) -> str:
        if event == "COMMENT":
            return "COMMENT"
        return "COMMENT"

    def _submit_pending_review(
        self,
        base_path: str,
        owner: str,
        repo: str,
        pull_number: int,
        args: dict[str, Any],
    ) -> object:
        submit_body = self._review_submit_body(args)
        if not self._draft_review_comments and not submit_body:
            return {"skipped": True, "reason": "no review comments or body to submit"}

        event = self._coerce_review_submit_event(args.get("event", "COMMENT"))
        if self._pending_review_id is None or self._draft_review_comments or self._draft_review_body:
            self._create_pending_review(base_path, owner, repo, pull_number, args)
        review_id = self._ensure_pending_review_id(owner, repo, pull_number)
        return gh_api_json(
            f"{base_path}/reviews/{review_id}/events",
            method="POST",
            input_json={
                "event": event,
                "body": submit_body,
            },
        )

    def add_comment_to_pending_review(self, **kwargs: Any) -> object:
        args = _with_pr_defaults(kwargs, self.repository, self.pull_number)
        owner = str(args["owner"])
        repo = str(args["repo"])
        pull_number = int(args["pullNumber"])

        def _stage_comment() -> object:
            if "line" not in args:
                raise ValueError("line is required for LINE review comments")

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

            dedupe_key = self._comment_dedupe_key(payload)
            if any(self._comment_dedupe_key(existing) == dedupe_key for existing in self._draft_review_comments):
                return {
                    "staged": True,
                    "comment_count": len(self._draft_review_comments),
                    "deduplicated": True,
                }

            index = self._load_diff_line_index(owner, repo, pull_number)
            self._validate_staged_comment(index, payload)
            self._draft_review_comments.append(payload)
            return {
                "staged": True,
                "comment_count": len(self._draft_review_comments),
            }

        return self._record_invocation("add_comment_to_pending_review", None, _stage_comment)

    def inline_comments_posted(self) -> bool:
        return any(
            invocation.tool_name == "add_comment_to_pending_review" and invocation.success
            for invocation in self.invocations
        ) and any(
            invocation.tool_name == "pull_request_review_write"
            and invocation.method == "submit_pending"
            and invocation.success
            for invocation in self.invocations
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
            invocation for invocation in self.invocations if invocation.tool_name == "add_comment_to_pending_review"
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

        submit_succeeded = any(
            invocation.tool_name == "pull_request_review_write"
            and invocation.method == "submit_pending"
            and invocation.success
            for invocation in self.invocations
        )
        failed_writes = [
            invocation
            for invocation in self.invocations
            if invocation.tool_name in {"add_comment_to_pending_review", "pull_request_review_write"}
            and not invocation.success
            and not (
                submit_succeeded
                and invocation.tool_name == "pull_request_review_write"
                and invocation.method == "submit_pending"
            )
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
