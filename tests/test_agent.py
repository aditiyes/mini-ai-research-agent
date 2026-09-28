import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from mini_research_agent.agent import ResearchAgent
from mini_research_agent.cli import main, render_report
from mini_research_agent.tools import search_wikipedia
from mini_research_agent.web import app


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


def test_search_wikipedia_normalizes_results_and_limits_result_count(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "query": {
                    "search": [
                        {
                            "pageid": 123,
                            "title": "Example result",
                            "snippet": "A <span>short</span> evidence snippet.",
                            "timestamp": "2026-09-27T12:00:00Z",
                        }
                    ]
                }
            }

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("mini_research_agent.tools.httpx.get", fake_get)

    result = search_wikipedia("current research")

    assert captured["params"]["srlimit"] == 5
    assert captured["timeout"] == 10.0
    assert result["sources"] == [
        {
            "id": "https://en.wikipedia.org/?curid=123",
            "title": "Example result",
            "url": "https://en.wikipedia.org/?curid=123",
            "organization": "Wikipedia",
            "published": "2026-09-27T12:00:00Z",
            "snippet": "A short evidence snippet.",
        }
    ]


def test_search_wikipedia_returns_structured_error_on_provider_failure(monkeypatch):
    def failing_get(url, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("mini_research_agent.tools.httpx.get", failing_get)

    result = search_wikipedia("current research")

    assert result["sources"] == []
    assert "provider unavailable" in result["error"]


def test_agent_includes_live_search_urls_in_report(monkeypatch):
    source_url = "https://en.wikipedia.org/?curid=123"
    monkeypatch.setattr(
        "mini_research_agent.agent.execute_tool",
        lambda name, arguments: {
            "sources": [
                {
                    "id": source_url,
                    "title": "Artemis program",
                    "url": source_url,
                    "organization": "Wikipedia",
                    "published": "n.d.",
                    "snippet": "The Artemis program is NASA's lunar exploration program.",
                }
            ]
        },
    )
    client = FakeClient(
        [
            response(tool_calls=[tool_call("1", "search_wikipedia", {"query": "Artemis program"})]),
            response(content="Wikipedia search results cover the Artemis program and missions."),
        ]
    )

    report = ResearchAgent(client, "test-model").run("What is NASA's Artemis program?")

    assert report["trace"][0]["tool"] == "search_wikipedia"
    assert report["evidence"][0]["url"] == source_url
    assert report["source_notes"][0]["url"] == source_url
    assert source_url in render_report(report)


def test_web_homepage_is_served():
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Research brief" in response.text


def test_web_research_requires_access_token_and_keeps_api_key_server_side(monkeypatch):
    captured = {}

    class DummyOpenAI:
        def __init__(self, api_key):
            captured["api_key"] = api_key

    class DummyAgent:
        def __init__(self, client, model):
            captured["model"] = model

        def run(self, question):
            captured["question"] = question
            return {"question": question, "evidence": [], "synthesis": "Brief", "source_notes": [], "trace": []}

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "test-access-code")
    monkeypatch.setenv("OPENAI_API_KEY", "server-only-key")
    monkeypatch.setattr("mini_research_agent.web.OpenAI", DummyOpenAI)
    monkeypatch.setattr("mini_research_agent.web.ResearchAgent", DummyAgent)
    client = TestClient(app)

    unauthorized = client.post("/api/research", json={"question": "A research question"})
    response = client.post(
        "/api/research",
        headers={"x-app-token": "test-access-code"},
        json={"question": "A research question"},
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["synthesis"] == "Brief"
    assert captured == {
        "api_key": "server-only-key",
        "model": "gpt-4o-mini",
        "question": "A research question",
    }


def test_web_research_fails_closed_without_production_access_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("APP_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "server-only-key")

    response = TestClient(app).post(
        "/api/research", json={"question": "A research question"}
    )

    assert response.status_code == 503


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
