#!/usr/bin/env python3
"""Fetch a Google Doc and convert it to markdown.

Uses the `gws` CLI tool (Google Workspace CLI) to access the Google Docs API.
Requires `gws` to be installed and authenticated.

Usage (from repo root):
    python .agents/tools/fetch_google_doc.py <document-id-or-url> [-o output.md]

Examples:
    python .agents/tools/fetch_google_doc.py 1aLED1gER-YINBjCHp5mUg5ChQf4BNpdRlnoEBKs_RF8
    python .agents/tools/fetch_google_doc.py 'https://docs.google.com/document/d/1aLED.../edit' -o bug-bash.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def extract_document_id(doc_id_or_url: str) -> str:
    """Extract document ID from a URL or return as-is if already an ID."""
    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_id_or_url)
    if match:
        return match.group(1)
    # Assume it's already a document ID
    return doc_id_or_url


def fetch_document(doc_id: str) -> dict:
    """Fetch document JSON via gws CLI."""
    result = subprocess.run(
        [
            "gws",
            "docs",
            "documents",
            "get",
            "--params",
            json.dumps({"documentId": doc_id, "includeTabsContent": True}),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Error: gws failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # gws may print non-JSON lines before the JSON output (e.g., "Using keyring backend: keyring")
    output = result.stdout
    json_start = output.find("{")
    if json_start == -1:
        print(f"Error: no JSON found in gws output:\n{output[:500]}", file=sys.stderr)
        sys.exit(1)

    return json.loads(output[json_start:])


def extract_text(content: list) -> str:
    """Extract plain text from Google Docs body content."""
    parts: list[str] = []
    for item in content:
        if "paragraph" in item:
            for elem in item["paragraph"]["elements"]:
                if "textRun" in elem:
                    parts.append(elem["textRun"]["content"])
        elif "table" in item:
            for row in item["table"].get("tableRows", []):
                cells = []
                for cell in row.get("tableCells", []):
                    cell_text = extract_text(cell.get("content", []))
                    cells.append(cell_text.strip())
                parts.append(" | ".join(cells))
                parts.append("\n")
    return "".join(parts)


def extract_links(content: list) -> list[tuple[str, str]]:
    """Extract hyperlinks from Google Docs body content."""
    links: list[tuple[str, str]] = []
    for item in content:
        if "paragraph" in item:
            for elem in item["paragraph"]["elements"]:
                if "textRun" in elem:
                    style = elem["textRun"].get("textStyle", {})
                    link = style.get("link", {})
                    url = link.get("url", "")
                    if url:
                        text = elem["textRun"].get("content", "").strip()
                        links.append((text, url))
        elif "table" in item:
            for row in item["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    links.extend(extract_links(cell.get("content", [])))
    return links


def doc_to_markdown(doc: dict) -> str:
    """Convert a Google Doc JSON to markdown."""
    title = doc.get("title", "Untitled")
    doc_id = doc.get("documentId", "unknown")
    tabs = doc.get("tabs", [])

    lines = [
        f"# {title}",
        "",
        f"Source: https://docs.google.com/document/d/{doc_id}/edit",
        "",
    ]

    for tab in tabs:
        props = tab.get("tabProperties", {})
        tab_title = props.get("title", "Untitled Tab")
        body_content = tab.get("documentTab", {}).get("body", {}).get("content", [])

        lines.append(f"## {tab_title}")
        lines.append("")
        lines.append(extract_text(body_content))

        links = extract_links(body_content)
        if links:
            lines.append("### Links")
            lines.append("")
            for text, url in links:
                if text and text != url:
                    lines.append(f"- [{text}]({url})")
                else:
                    lines.append(f"- {url}")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a Google Doc as markdown")
    parser.add_argument("document", help="Google Doc ID or URL")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)")
    args = parser.parse_args()

    doc_id = extract_document_id(args.document)
    print(f"Fetching document {doc_id}...", file=sys.stderr)

    doc = fetch_document(doc_id)
    markdown = doc_to_markdown(doc)

    if args.output:
        Path(args.output).write_text(markdown)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(markdown)


if __name__ == "__main__":
    main()
