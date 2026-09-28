const form = document.querySelector("#research-form");
const questionInput = document.querySelector("#question");
const questionCount = document.querySelector("#question-count");
const accessField = document.querySelector("#access-field");
const accessCode = document.querySelector("#access-code");
const submitButton = document.querySelector("#submit-button");
const runStatus = document.querySelector("#run-status");
const report = document.querySelector("#report");
const evidenceList = document.querySelector("#evidence-list");
const synthesisText = document.querySelector("#synthesis-text");
const sourceNotes = document.querySelector("#source-notes");
const traceOutput = document.querySelector("#trace-output");

questionInput.addEventListener("input", () => {
  questionCount.textContent = `${questionInput.value.length} / 500`;
});

questionInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    form.requestSubmit();
  }
});

function externalLink(url, label) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") return null;
    const link = document.createElement("a");
    link.href = parsed.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    return link;
  } catch {
    return null;
  }
}

function renderReport(data) {
  evidenceList.replaceChildren();
  sourceNotes.replaceChildren();

  if (data.evidence.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-result";
    empty.textContent = "No matching evidence was returned for this question.";
    evidenceList.append(empty);
  }

  data.evidence.forEach((item, index) => {
    const row = document.createElement("article");
    row.className = "evidence-row";

    const number = document.createElement("span");
    number.className = "evidence-number";
    number.textContent = String(index + 1).padStart(2, "0");

    const content = document.createElement("div");
    content.className = "evidence-content";
    const title = externalLink(item.url, item.title);
    const heading = document.createElement("h3");
    if (title) heading.append(title);
    else heading.textContent = item.title;

    const snippet = document.createElement("p");
    snippet.textContent = item.text;
    content.append(heading, snippet);
    row.append(number, content);
    evidenceList.append(row);
  });

  synthesisText.textContent = data.synthesis || "No synthesis was returned.";

  data.source_notes.forEach((source) => {
    const item = document.createElement("li");
    const title = document.createElement("span");
    title.textContent = `${source.title} - ${source.organization} (${source.published})`;
    item.append(title);
    const link = externalLink(source.url, source.url);
    if (link) item.append(link);
    else if (source.id) {
      const identifier = document.createElement("span");
      identifier.className = "source-id";
      identifier.textContent = source.id;
      item.append(identifier);
    }
    sourceNotes.append(item);
  });

  traceOutput.textContent = JSON.stringify(data.trace, null, 2);
  document.querySelector("#report-date").textContent = new Date().toLocaleString();
  report.hidden = false;
  report.classList.remove("is-visible");
  requestAnimationFrame(() => report.classList.add("is-visible"));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) {
    questionInput.focus();
    return;
  }

  submitButton.disabled = true;
  submitButton.textContent = "Researching...";
  runStatus.textContent = "SEARCHING LIVE INDEX";
  report.hidden = true;
  form.setAttribute("aria-busy", "true");

  try {
    const headers = { "Content-Type": "application/json" };
    if (accessCode.value) headers["X-App-Token"] = accessCode.value;
    const response = await fetch("/api/research", {
      method: "POST",
      headers,
      body: JSON.stringify({ question }),
    });
    const result = await response.json();

    if (response.status === 401) {
      accessField.hidden = false;
      accessCode.focus();
      throw new Error("Enter the app access code to continue.");
    }
    if (!response.ok) {
      const message = typeof result.detail === "string" ? result.detail : "The research request failed.";
      throw new Error(message);
    }

    renderReport(result);
    runStatus.textContent = "BRIEF COMPLETE";
  } catch (error) {
    runStatus.textContent = error.message || "The research request failed. Try again.";
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = 'Build brief <span aria-hidden="true">&rarr;</span>';
    form.removeAttribute("aria-busy");
  }
});