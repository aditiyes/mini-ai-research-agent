import json
from pathlib import Path
from types import SimpleNamespace

from mini_research_agent.agent import ResearchAgent
from mini_research_agent.cli import main, render_report


def response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create)
        )
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return next(self.responses)


def test_agent_collects_sources_and_returns_separate_synthesis():
    client = FakeClient(
        [
            response(tool_calls=[tool_call("1", "search_sources", {"query": "urban trees heat"})]),
            response(tool_calls=[tool_call("2", "read_source", {"source_id": "urban-trees-01"})]),
            response(content="The local notes connect tree canopy with cooler shaded surfaces."),
        ]
    )

    report = ResearchAgent(client, "test-model").run("How might urban trees affect heat?")

    evidence_by_id = {item["id"]: item for item in report["evidence"]}
    assert set(evidence_by_id) == {"urban-trees-01", "urban-trees-02"}
    assert "local temperature measurements" in evidence_by_id["urban-trees-01"]["text"]
    assert "Urban trees and surface temperatures" in {
        item["title"] for item in report["source_notes"]
    }
    assert report["synthesis"].startswith("The local notes")
    assert [event["tool"] for event in report["trace"]] == ["search_sources", "read_source"]
    assert "Evidence" in render_report(report)
    assert "Synthesis" in render_report(report)


def test_out_of_scope_question_returns_no_sources():
    client = FakeClient(
        [
            response(tool_calls=[tool_call("1", "search_sources", {"query": "live election results"})]),
            response(content="The local corpus has no relevant material for this question."),
        ]
    )

    report = ResearchAgent(client, "test-model").run("What are today's live election results?")

    assert report["evidence"] == []
    assert report["source_notes"] == []
    assert report["trace"][0]["result"]["sources"] == []
    assert "No relevant evidence" in render_report(report)


def test_repeated_and_disallowed_tool_calls_are_recorded():
    client = FakeClient(
        [
            response(tool_calls=[tool_call("1", "search_sources", {"query": "urban trees"})]),
            response(
                tool_calls=[
                    tool_call("2", "search_sources", {"query": "urban trees"}),
                    tool_call("3", "delete_file", {"path": "anything"}),
                    tool_call("4", "read_source", {"source_id": "missing-source"}),
                ]
            ),
            response(content="The corpus includes local urban-tree planning notes."),
        ]
    )

    report = ResearchAgent(client, "test-model").run("What is known about city trees?")

    assert [event["status"] for event in report["trace"]] == ["ok", "repeated", "error", "error"]
    assert "Repeated" in report["trace"][1]["result"]["error"]
    assert "not allowed" in report["trace"][2]["result"]["error"]
    assert "Unknown source_id" in report["trace"][3]["result"]["error"]


def test_iteration_cap_stops_additional_model_calls():
    client = FakeClient(
        [response(tool_calls=[tool_call("1", "search_sources", {"query": "sleep"})])]
    )

    report = ResearchAgent(client, "test-model", max_iterations=1).run("How does sleep affect attention?")

    assert client.calls == 1
    assert "tool-call limit" in report["synthesis"]
    assert report["evidence"]


def test_cli_uses_dotenv_values_when_present(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=test-key\nOPENAI_MODEL=test-model\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    calls = {}

    class DummyClient:
        def __init__(self, api_key):
            calls["api_key"] = api_key

    monkeypatch.setattr("mini_research_agent.cli.OpenAI", DummyClient)
    def create_agent(client, model, **kwargs):
        calls["model"] = model
        return SimpleNamespace(run=lambda question: {"question": question, "evidence": [], "source_notes": [], "synthesis": "ok", "trace": []})

    monkeypatch.setattr("mini_research_agent.cli.ResearchAgent", create_agent)

    exit_code = main(["--question", "What is known?"])

    assert exit_code == 0
    assert calls == {"api_key": "test-key", "model": "test-model"}


def test_cli_allows_explicit_question_and_model_override(monkeypatch):
    captured = {}

    class DummyClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key

    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    monkeypatch.setattr("mini_research_agent.cli.OpenAI", DummyClient)
    def create_agent(client, model, **kwargs):
        captured["model"] = model
        return SimpleNamespace(run=lambda question: {"question": question, "evidence": [], "source_notes": [], "synthesis": "ok", "trace": []})

    monkeypatch.setattr("mini_research_agent.cli.ResearchAgent", create_agent)

    exit_code = main(["--question", "Why does sleep matter?", "--model", "custom-model"])

    assert exit_code == 0
    assert captured == {"api_key": "from-env", "model": "custom-model"}
