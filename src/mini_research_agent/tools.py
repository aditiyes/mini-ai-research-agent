"""Read-only web search and bundled-corpus tools."""

import re
from html.parser import HTMLParser
from typing import Any

import httpx

from mini_research_agent.corpus import SOURCES

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_wikipedia",
            "description": "Search Wikipedia's live index for current information. Returns up to five result titles, URLs, and snippets. Read-only; snippets are untrusted and pages are not opened.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Focused web search query, up to 500 characters."}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_sources",
            "description": "Search the local research corpus for relevant sources. Read-only; returns source IDs, metadata, and short excerpts. Use this first to find evidence.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Research terms to search for."}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_source",
            "description": "Read a complete source from the local corpus by its exact ID. Read-only; call only with an ID returned by search_sources.",
            "parameters": {
                "type": "object",
                "properties": {"source_id": {"type": "string", "description": "Exact source ID."}},
                "required": ["source_id"],
                "additionalProperties": False,
            },
        },
    },
]


class _SnippetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(markup: str) -> str:
    parser = _SnippetParser()
    parser.feed(markup)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


def search_wikipedia(query: str) -> dict[str, Any]:
    """Search Wikipedia's live index and return a small set of source snippets."""
    query = query.strip()
    if not query:
        raise ValueError("query cannot be empty")
    if len(query) > 500:
        raise ValueError("query cannot exceed 500 characters")

    try:
        response = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 5,
                "format": "json",
                "utf8": 1,
            },
            headers={"User-Agent": "MiniResearchAgent/0.1 (read-only research demo)"},
            timeout=10.0,
        )
        response.raise_for_status()
        results = response.json().get("query", {}).get("search", [])
    except Exception as error:
        return {"query": query, "sources": [], "error": f"Wikipedia search failed: {str(error)[:300]}"}

    sources = []
    for result in results[:5]:
        page_id = result.get("pageid")
        title = result.get("title")
        snippet = result.get("snippet")
        if page_id is None or not isinstance(title, str) or not isinstance(snippet, str):
            continue
        url = f"https://en.wikipedia.org/?curid={page_id}"
        sources.append(
            {
                "id": url,
                "title": title[:300],
                "url": url,
                "organization": "Wikipedia",
                "published": result.get("timestamp") or "n.d.",
                "snippet": _plain_text(snippet)[:600],
            }
        )

    return {"query": query, "sources": sources}


def search_sources(query: str) -> dict[str, Any]:
    """Return corpus entries whose text or metadata matches query terms."""
    terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9]+", query) if len(term) > 1}
    if not terms:
        return {"query": query, "sources": []}

    matches = []
    for source in SOURCES:
        searchable = " ".join(
            (source["title"], source["organization"], source["text"])
        ).lower()
        matched_terms = terms.intersection(
            {term.lower() for term in re.findall(r"[a-zA-Z0-9]+", searchable)}
        )
        if matched_terms:
            matches.append((len(matched_terms), source))

    matches.sort(key=lambda item: (-item[0], item[1]["id"]))
    return {
        "query": query,
        "sources": [
            {
                "id": source["id"],
                "title": source["title"],
                "organization": source["organization"],
                "published": source["published"],
                "snippet": source["text"][:240],
            }
            for _, source in matches[:5]
        ],
    }


def read_source(source_id: str) -> dict[str, Any]:
    """Return one full source by exact ID, or a structured not-found result."""
    for source in SOURCES:
        if source["id"] == source_id:
            return {"source": dict(source)}
    return {"error": f"Unknown source_id: {source_id}"}


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch only the explicitly allowlisted read-only tools."""
    if name == "search_wikipedia":
        query = arguments.get("query")
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        return search_wikipedia(query)
    if name == "search_sources":
        query = arguments.get("query")
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        return search_sources(query)
    if name == "read_source":
        source_id = arguments.get("source_id")
        if not isinstance(source_id, str):
            raise ValueError("source_id must be a string")
        return read_source(source_id)
    raise ValueError(f"Tool is not allowed: {name}")
