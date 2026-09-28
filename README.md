# Mini AI Research Agent

A small Python CLI agent that answers research questions using two safe, read-only tools over a bundled local corpus:

- `search_sources(query)` finds matching source records and short excerpts.
- `read_source(source_id)` returns the full text of a corpus record.

The agent can make up to five model turns, skips repeated identical tool calls, records every tool result, and formats the final report as **Evidence**, **Synthesis**, and **Source notes**. The evidence and notes are assembled from tool outputs; synthesis is the model's concise interpretation. The bundled entries are illustrative demo material, not authoritative research or citations.

## Setup

Requires Python 3.9 or newer and an OpenAI API key for live model mode.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-4o-mini"
```

Alternatively, copy `.env.example` to `.env` and set the values. The CLI loads `.env` from the current directory (or its parent) without overriding variables already set in the shell.

## Run

```powershell
mini-research "How might urban trees affect heat in cities?" --trace
```

Or run the module directly:

```powershell
python -m mini_research_agent.cli "What does the demo corpus say about sleep?"
```

`--trace` appends the ordered tool-call log as JSON. Only the local corpus tools are exposed to the model; the agent has no general web, filesystem-write, or command-execution tools.

## Tests

Tests use a fake model client and require no API key or network access:

```powershell
python -m pytest
```

The tests cover evidence collection, empty search results, repeated and disallowed calls, and the iteration limit.
