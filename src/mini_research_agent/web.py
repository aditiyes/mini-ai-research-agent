"""FastAPI web interface for the mini research agent."""

import hmac
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from mini_research_agent.agent import ResearchAgent

load_dotenv()

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")
app = FastAPI(title="Mini Research Agent", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.get("/", include_in_schema=False)
def homepage() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/research")
def research(
    request: ResearchRequest,
    x_app_token: str = Header(default=""),
) -> dict[str, Any]:
    access_token = os.environ.get("APP_ACCESS_TOKEN", "")
    if os.environ.get("APP_ENV") == "production" and not access_token:
        raise HTTPException(status_code=503, detail="App access is not configured.")
    if access_token and not hmac.compare_digest(x_app_token, access_token):
        raise HTTPException(status_code=401, detail="An access code is required.")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="The server is missing its OpenAI API key.")
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Enter a research question.")

    try:
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return ResearchAgent(OpenAI(api_key=api_key), model).run(question)
    except Exception:
        logger.exception("Research request failed")
        raise HTTPException(status_code=502, detail="Research failed. Check the server logs.")