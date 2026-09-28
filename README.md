# Mini AI Research Agent

A small research agent with a CLI and a responsive web interface. It uses three read-only tools:

- `search_wikipedia(query)` searches Wikipedia's live index and returns up to five titles, URLs, and snippets.
- `search_sources(query)` finds matching records in a small illustrative local corpus.
- `read_source(source_id)` returns the full text of a local corpus record.

The agent can make up to five model turns, skips repeated identical tool calls, records every tool result, and formats the final report as **Evidence**, **Synthesis**, and **Source notes**. Wikipedia results are snippets only: the agent does not open pages, and snippets are treated as untrusted input. This is live search over Wikipedia, not a general-purpose web search engine. The bundled local entries are illustrative demo material, not authoritative research or citations.

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

`--trace` appends the ordered tool-call log as JSON. The agent has no filesystem-write or command-execution tools. Live Wikipedia search requires an internet connection; the local corpus remains available as supplementary demo material.

## Web App

Set `OPENAI_API_KEY` in `.env`, then start the local web app:

```powershell
uvicorn mini_research_agent.web:app --reload
```

Open `http://127.0.0.1:8000`. The OpenAI key stays on the server. When `APP_ACCESS_TOKEN` is set, the page asks for that access code before it can run research.

## Deploy

The repository includes a Render Blueprint. Open [Render's Blueprint deploy page](https://render.com/deploy?repo=https://github.com/aditiyes/mini-ai-research-agent), connect the repository, and provide `OPENAI_API_KEY` and a strong `APP_ACCESS_TOKEN` as secrets when prompted. Render builds the Python service and assigns its public URL. Keep both values out of GitHub; the access token protects the billable research endpoint.

## Tests

Tests use a fake model client and require no API key or network access:

```powershell
python -m pytest
```

The tests cover evidence collection, empty search results, live-index response handling, provider errors, repeated and disallowed calls, the iteration limit, and web endpoint authentication. Tests use mocked clients and do not require API keys or network access.
