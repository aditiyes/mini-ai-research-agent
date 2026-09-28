"""Command-line interface for the mini research agent."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from mini_research_agent.agent import ResearchAgent

OpenAI = None


def _load_dotenv(path: Optional[str] = None) -> None:
    """Load environment variables from a local .env file without overriding existing ones."""
    dotenv_path = Path(path) if path else Path.cwd()
    candidates = [dotenv_path / ".env", dotenv_path.parent / ".env"]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = [part.strip() for part in line.split("=", 1)]
            os.environ.setdefault(key, value)


def _get_client(api_key: str):
    global OpenAI
    if OpenAI is None:
        from openai import OpenAI as OpenAIClient

        OpenAI = OpenAIClient
    return OpenAI(api_key=api_key)


def render_report(report: dict[str, Any]) -> str:
    lines = ["Evidence"]
    if report["evidence"]:
        for item in report["evidence"]:
            lines.append(f'- [{item["id"]}] {item["title"]}: {item["text"]}')
    else:
        lines.append("- No relevant evidence was found in the local corpus.")

    lines.extend(["", "Synthesis", report["synthesis"], "", "Source notes"])
    if report["source_notes"]:
        for source in report["source_notes"]:
            lines.append(
                f'- [{source["id"]}] {source["title"]}, {source["organization"]} '
                f'({source["published"]})'
            )
    else:
        lines.append("- No sources retrieved.")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research a question using a local read-only corpus.")
    parser.add_argument("question", nargs="*", help="Research question")
    parser.add_argument("--question", dest="explicit_question", help="Question to research")
    parser.add_argument("--model", default=None, help="OpenAI model name to use")
    parser.add_argument("--trace", action="store_true", help="Print tool-call trace as JSON after the report")
    args = parser.parse_args(argv)

    _load_dotenv()
    question = (args.explicit_question or " ".join(args.question)).strip()
    if not question:
        question = input("Research question: ").strip()

    api_key = os.environ.get("OPENAI_API_KEY")
    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        print("Set OPENAI_API_KEY to run the live agent. See README.md.", file=sys.stderr)
        return 2

    try:
        client = _get_client(api_key)
        agent = ResearchAgent(client, model)
        report = agent.run(question)
    except Exception as error:
        print(f"Research run failed: {error}", file=sys.stderr)
        return 1

    print(render_report(report))
    if args.trace:
        print("\nTool trace")
        print(json.dumps(report["trace"], indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
