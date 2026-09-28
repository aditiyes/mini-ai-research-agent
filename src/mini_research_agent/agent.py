"""Bounded tool-calling loop and evidence-first report assembly."""

import json
from typing import Any

from mini_research_agent.tools import TOOL_SCHEMAS, execute_tool

SYSTEM_PROMPT = """You are a concise research assistant using only a small local corpus.
Use search_sources to find relevant evidence and read_source to inspect useful records.
Never make factual claims unsupported by tool results. If the corpus has no relevant
material, say so plainly. Stop when you have enough evidence or search returns no hits.
Do not repeat an identical tool call. Do not claim this corpus is comprehensive.
Return only a short synthesis; the application adds the evidence and source notes."""


class ResearchAgent:
    """An OpenAI-compatible tool loop with a strict model-turn limit."""

    def __init__(self, client: Any, model: str, max_iterations: int = 5):
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        self.client = client
        self.model = model
        self.max_iterations = max_iterations

    def run(self, question: str) -> dict[str, Any]:
        if not question.strip():
            raise ValueError("Research question cannot be empty")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question.strip()},
        ]
        trace: list[dict[str, Any]] = []
        evidence: dict[str, dict[str, str]] = {}
        seen_calls: set[str] = set()
        synthesis = ""

        for iteration in range(1, self.max_iterations + 1):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0,
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            if not tool_calls:
                synthesis = message.content or "No synthesis was returned by the model."
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [self._serialize_call(call) for call in tool_calls],
                }
            )
            for call in tool_calls:
                name = call.function.name
                raw_arguments = call.function.arguments
                trace_entry: dict[str, Any] = {
                    "iteration": iteration,
                    "tool": name,
                    "arguments": raw_arguments,
                }
                try:
                    arguments = json.loads(raw_arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be a JSON object")
                    fingerprint = json.dumps(
                        [name, arguments], sort_keys=True, separators=(",", ":")
                    )
                    if fingerprint in seen_calls:
                        result = {"error": "Repeated identical tool call was skipped."}
                        trace_entry["status"] = "repeated"
                    else:
                        seen_calls.add(fingerprint)
                        result = execute_tool(name, arguments)
                        trace_entry["status"] = "error" if "error" in result else "ok"
                    self._collect_evidence(result, evidence)
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    result = {"error": str(error)}
                    trace_entry["status"] = "error"
                trace_entry["result"] = result
                trace.append(trace_entry)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=True),
                    }
                )
        else:
            synthesis = (
                "The tool-call limit was reached. This report includes only the "
                "evidence gathered so far."
            )

        return {
            "question": question.strip(),
            "evidence": list(evidence.values()),
            "synthesis": synthesis.strip(),
            "source_notes": [
                {"id": item["id"], "title": item["title"], "organization": item["organization"], "published": item["published"]}
                for item in evidence.values()
            ],
            "trace": trace,
        }

    @staticmethod
    def _serialize_call(call: Any) -> dict[str, Any]:
        return {
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.function.name,
                "arguments": call.function.arguments,
            },
        }

    @staticmethod
    def _collect_evidence(result: dict[str, Any], evidence: dict[str, dict[str, str]]) -> None:
        source = result.get("source")
        if isinstance(source, dict) and source.get("id"):
            evidence[source["id"]] = {
                "id": source["id"],
                "title": source["title"],
                "organization": source["organization"],
                "published": source["published"],
                "text": source["text"],
            }
        for item in result.get("sources", []):
            if item.get("id"):
                evidence.setdefault(
                    item["id"],
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "organization": item["organization"],
                        "published": item["published"],
                        "text": item["snippet"],
                    },
                )
