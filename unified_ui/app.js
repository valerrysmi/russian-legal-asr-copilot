const API_BASE = window.location.origin;
const $ = (id) => document.getElementById(id);

const statusBadge = $("statusBadge");
const eventsLog = $("eventsLog");
const conversationTimelineEl = $("conversationTimeline");
const articleLibraryEl = $("articleLibrary");
const articleViewerEl = $("articleViewer");
const realtimeEventsLog = $("realtimeEventsLog");

const legalRouteEl = $("legalRoute");
const legalGroundedEl = $("legalGrounded");
const legalConfidenceEl = $("legalConfidence");
const legalQuestionEl = $("legalQuestion");
const legalQuestionsEl = $("legalQuestions");
const legalArticlesEl = $("legalArticles");
const legalAnswerEl = $("legalAnswer");
const lawyerCheckStatusEl = $("lawyerCheckStatus");
const lawyerFlaggedPhrasesEl = $("lawyerFlaggedPhrases");
const legalErrorsEl = $("legalErrors");
const legalBridgeErrorEl = $("legalBridgeError");

let pollTimer = null;
let lastLogText = "";
let activeArticleKey = null;
let articleStore = new Map();

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function setStatus(text, cls = "") {
  statusBadge.textContent = text;
  statusBadge.className = `badge ${cls}`.trim();
}

function setBadge(el, text, cls = "") {
  if (!el) return;
  el.textContent = text || "—";
  el.className = `badge ${cls}`.trim();
}

function logEvent(obj) {
  const text = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  eventsLog.textContent = `${text}\n\n${eventsLog.textContent}`.slice(0, 30000);
}

function renderRealtimeEvents(events) {
  if (!realtimeEventsLog) return;
  if (!events || !events.length) {
    realtimeEventsLog.textContent = "Realtime-событий пока нет.";
    return;
  }
  realtimeEventsLog.textContent = events
    .map((event) => JSON.stringify(event, null, 2))
    .join("\n\n");
}

function renderList(el, items, formatter = (item) => escapeHtml(item)) {
  el.innerHTML = "";
  if (!items || !items.length) {
    const li = document.createElement("li");
    li.textContent = "—";
    el.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.innerHTML = formatter(item);
    el.appendChild(li);
  }
}

function speakerRole(rawSpeaker) {
  const value = String(rawSpeaker || "").trim().toLowerCase();
  if (value.includes("lawyer") || value.includes("юрист")) return "lawyer";
  if (value.includes("client") || value.includes("клиент")) return "client";
  return "unknown";
}

function parseTranscriptLines(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const bracket = line.match(/^\[([^\]]+)\]\s*(?:\(([^)]*)\))?\s*:\s*(.*)$/);
      if (bracket) {
        return { speaker: bracket[1], chunk: bracket[2] || "", text: bracket[3] };
      }
      const simple = line.match(/^([^:]{2,40}):\s*(.*)$/);
      if (simple) {
        return { speaker: simple[1], chunk: "", text: simple[2] };
      }
      return { speaker: "Unknown", chunk: "", text: line };
    });
}

function renderTranscriptTimeline(transcriptText, copilotText) {
  conversationTimelineEl.innerHTML = "";
  const segments = parseTranscriptLines(transcriptText);

  if (!segments.length) {
    conversationTimelineEl.innerHTML = `<div class="chat-empty">Транскрипция пока не создана.</div>`;
  } else {
    const chat = document.createElement("div");
    chat.className = "transcript-chat";
    for (const segment of segments) {
      const role = speakerRole(segment.speaker);
      const label = segment.speaker || "Unknown";
      const line = document.createElement("div");
      line.className = `chat-line ${role}`;
      line.innerHTML = `
        <div class="chat-bubble ${role}">
          <div class="chat-speaker">${escapeHtml(label)}</div>
          <div class="chat-text">${escapeHtml(segment.text)}</div>
        </div>
      `;
      chat.appendChild(line);
    }
    conversationTimelineEl.appendChild(chat);
  }

  if (copilotText) {
    const card = document.createElement("div");
    card.className = "timeline-legal-card";
    card.innerHTML = `
      <div class="timeline-legal-header">
        <div class="timeline-legal-title">LegalCopilot result</div>
        <div class="timeline-meta">finalized</div>
        <span class="badge ok">analysis</span>
      </div>
      <div class="timeline-legal-body">
        <div class="line">${escapeHtml(shorten(copilotText, 1800))}</div>
      </div>
    `;
    conversationTimelineEl.appendChild(card);
  }

  conversationTimelineEl.scrollTop = conversationTimelineEl.scrollHeight;
}

function renderRealtimeTimeline(events) {
  const updates = (events || []).filter((event) => event.type === "copilot_update");
  if (!updates.length) return;

  for (const update of updates.slice(-8)) {
    const exists = conversationTimelineEl.querySelector(`[data-realtime-key="${CSS.escape(String(update.seq ?? update.chunk_id ?? ""))}"]`);
    if (exists) continue;

    const role = speakerRole(update.speaker);
    const line = document.createElement("div");
    line.className = `chat-line ${role}`;
    line.dataset.realtimeKey = String(update.seq ?? update.chunk_id ?? "");
    line.innerHTML = `
      <div class="chat-bubble ${role}">
        <div class="chat-speaker">${escapeHtml(update.speaker || "Unknown")}</div>
        <div class="chat-text">${escapeHtml(update.text || "")}</div>
      </div>
    `;
    conversationTimelineEl.appendChild(line);

    const card = document.createElement("div");
    card.className = "timeline-legal-card";
    card.dataset.realtimeKey = `copilot-${String(update.seq ?? update.chunk_id ?? "")}`;
    card.innerHTML = `
      <div class="timeline-legal-header">
        <div class="timeline-legal-title">LegalCopilot realtime update</div>
        <div class="timeline-meta">${escapeHtml(update.elapsed_s ?? "")}s</div>
        <span class="badge ${update.route ? "ok" : "warn"}">${escapeHtml(update.route || "pending")}</span>
      </div>
      <div class="timeline-legal-body">
        <div class="line"><b>Active query:</b> ${escapeHtml(update.active_user_query || "—")}</div>
        <div class="line"><b>Answer:</b> ${escapeHtml(update.answer_text || "—")}</div>
      </div>
    `;
    conversationTimelineEl.appendChild(card);
  }

  conversationTimelineEl.scrollTop = conversationTimelineEl.scrollHeight;
}

function shorten(text, limit) {
  const value = String(text || "").trim();
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 3)}...`;
}

function extractFirst(regex, text) {
  const match = String(text || "").match(regex);
  return match ? match[1].trim() : "";
}

function parseCopilotOutput(text) {
  const value = String(text || "");
  const route = extractFirst(/^route:\s*(.+)$/im, value);
  const question =
    extractFirst(/^primary_question:\s*(.+)$/im, value) ||
    extractFirst(/^retrieval_request:\s*\n(.+)$/im, value);
  const confidence = extractFirst(/^confidence:\s*(.+)$/im, value);
  const factCheck = extractFirst(/^fact_check:\s*(.+)$/im, value);
  const lawyerCheck = extractFirst(/^lawyer_phrase_check:\s*(.+)$/im, value);
  const answer = extractFirst(/^answer:\s*(.+)$/im, value);
  const questions = [...value.matchAll(/^\s*-\s*(.+\?)\s*$/gim)].map((match) => match[1]);
  const articles = [...value.matchAll(/art\.\s*([\d.]+):\s*([^(]+)\(([\d.]+)\)/gim)].map((match) => ({
    article_number: match[1],
    title: match[2].trim(),
    final_score: Number(match[3]),
    summary: "",
    text: "",
  }));
  const errors = [...value.matchAll(/(?:error|failed|traceback):\s*(.+)$/gim)].map((match) => match[0]);

  return { route, question, confidence, factCheck, lawyerCheck, answer, questions, articles, errors };
}

function articleKey(article) {
  return `${article.article_number}::${article.title}`;
}

function resetArticleLibrary() {
  articleStore = new Map();
  activeArticleKey = null;
  articleLibraryEl.innerHTML = "";
  articleViewerEl.className = "article-viewer empty";
  articleViewerEl.innerHTML = `
    <div class="article-viewer-title">Текст статьи</div>
    <div class="article-viewer-body">Выберите статью из списка слева.</div>
  `;
}

function renderArticleViewer(article) {
  if (!article) return;
  articleViewerEl.className = "article-viewer";
  articleViewerEl.innerHTML = `
    <div class="article-viewer-title">Статья ${escapeHtml(article.article_number)}. ${escapeHtml(article.title)}</div>
    <div class="article-viewer-subtitle">Score: ${Number(article.final_score || 0).toFixed(3)}</div>
    <div class="article-viewer-summary">${escapeHtml(article.summary || "Краткое описание не найдено в консольном выводе.")}</div>
    <div class="article-viewer-body">${escapeHtml(article.text || "Полный текст статьи не входит в текущий copilot_output.txt.")}</div>
  `;
}

function renderArticleLibrary(articles) {
  resetArticleLibrary();
  for (const article of articles || []) {
    articleStore.set(articleKey(article), article);
  }

  const sorted = Array.from(articleStore.values()).sort(
    (left, right) => Number(right.final_score || 0) - Number(left.final_score || 0),
  );

  if (!sorted.length) {
    articleLibraryEl.innerHTML = `<div class="article-item"><div class="article-item-summary">Статьи пока не найдены.</div></div>`;
    return;
  }

  for (const article of sorted) {
    const key = articleKey(article);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `article-item ${activeArticleKey === key ? "active" : ""}`;
    button.innerHTML = `
      <div class="article-item-title">Статья ${escapeHtml(article.article_number)}. ${escapeHtml(article.title)}</div>
      <div class="article-item-meta">Score: ${Number(article.final_score || 0).toFixed(3)}</div>
      <div class="article-item-summary">${escapeHtml(article.summary || "Описание недоступно.")}</div>
    `;
    button.addEventListener("click", () => {
      activeArticleKey = key;
      renderArticleLibrary(sorted);
      renderArticleViewer(article);
    });
    articleLibraryEl.appendChild(button);
  }

  activeArticleKey = articleKey(sorted[0]);
  renderArticleViewer(sorted[0]);
}

function renderLegalAnalysis(copilotText) {
  const parsed = parseCopilotOutput(copilotText);
  setBadge(legalRouteEl, parsed.route || "—", parsed.route ? "ok" : "");
  setBadge(legalGroundedEl, parsed.factCheck || "—", parsed.factCheck.includes("True") || parsed.factCheck.includes("true") ? "ok" : "");
  legalConfidenceEl.textContent = parsed.confidence || "—";
  legalQuestionEl.textContent = parsed.question || "—";
  legalAnswerEl.textContent = parsed.answer || (copilotText ? shorten(copilotText, 2500) : "—");
  lawyerCheckStatusEl.textContent = parsed.lawyerCheck || "—";
  legalBridgeErrorEl.textContent = "";
  renderList(legalQuestionsEl, parsed.questions, (item) => escapeHtml(item));
  renderList(
    legalArticlesEl,
    parsed.articles,
    (item) => `<b>ст. ${escapeHtml(item.article_number)}</b> ${escapeHtml(item.title)} <span class="score">score=${Number(item.final_score).toFixed(3)}</span>`,
  );
  renderList(lawyerFlaggedPhrasesEl, [], (item) => escapeHtml(item));
  renderList(legalErrorsEl, parsed.errors, (item) => escapeHtml(item));
  renderArticleLibrary(parsed.articles);
}

function renderRealtimeAnalysis(events) {
  const updates = (events || []).filter((event) => event.type === "copilot_update");
  if (!updates.length) return false;
  const latest = updates[updates.length - 1];
  setBadge(legalRouteEl, latest.route || "pending", latest.route ? "ok" : "warn");
  setBadge(legalGroundedEl, "realtime", "warn");
  legalConfidenceEl.textContent = latest.elapsed_s !== undefined ? `${latest.elapsed_s}s` : "—";
  legalQuestionEl.textContent = latest.active_user_query || "—";
  legalAnswerEl.textContent = latest.answer_text || "Ответ появится после содержательного вопроса.";
  lawyerCheckStatusEl.textContent = "realtime window";
  legalBridgeErrorEl.textContent = "";
  renderList(legalQuestionsEl, latest.active_user_query ? [latest.active_user_query] : []);
  renderList(legalArticlesEl, []);
  renderList(lawyerFlaggedPhrasesEl, []);
  renderList(legalErrorsEl, []);
  renderArticleLibrary([]);
  return true;
}

function renderStatus(payload) {
  $("sessionId").textContent = payload.consultation || "—";
  $("outputDir").textContent = payload.outputDir || "—";
  $("pipelineState").textContent = payload.running ? "выполняется" : payload.returnCode === 0 ? "готово" : payload.returnCode ? "ошибка" : "ожидание";

  $("runBtn").disabled = Boolean(payload.running);
  $("stopBtn").disabled = !payload.running;

  if (payload.running) {
    setStatus("Pipeline running", "warn");
  } else if (payload.returnCode === 0) {
    setStatus("Finalized", "ok");
  } else if (payload.returnCode !== null && payload.returnCode !== undefined) {
    setStatus("Pipeline error", "err");
  } else {
    setStatus("Waiting for session", "warn");
  }

  const logText = (payload.log || []).join("\n");
  if (logText && logText !== lastLogText) {
    lastLogText = logText;
    logEvent(logText);
  }
}

function renderResult(payload) {
  renderStatus(payload);
  $("transcriptText").textContent = payload.transcript || "—";
  if ((payload.realtimeEvents || []).length) {
    if (!conversationTimelineEl.dataset.realtimeStarted) {
      conversationTimelineEl.innerHTML = "";
      conversationTimelineEl.dataset.realtimeStarted = "1";
    }
    renderRealtimeTimeline(payload.realtimeEvents);
  } else {
    delete conversationTimelineEl.dataset.realtimeStarted;
    renderTranscriptTimeline(payload.transcript, payload.copilotOutput);
  }
  if (!renderRealtimeAnalysis(payload.realtimeEvents || [])) {
    renderLegalAnalysis(payload.copilotOutput || "");
  }
  renderRealtimeEvents(payload.realtimeEvents || []);
}

async function refresh() {
  const payload = await fetchJson("/api/result");
  renderResult(payload);
}

async function loadDefaults() {
  try {
    const payload = await fetchJson("/api/defaults");
    if (payload.redisHost) $("redisHost").value = payload.redisHost;
    if (payload.redisPort) $("redisPort").value = payload.redisPort;
  } catch (error) {
    logEvent(`Could not load defaults: ${error}`);
  }
}

async function loadConsultations() {
  const payload = await fetchJson("/api/consultations");
  const select = $("consultationSelect");
  select.innerHTML = "";

  for (const item of payload.items || []) {
    const option = document.createElement("option");
    option.value = item.name;
    option.disabled = !item.hasAudio;
    option.dataset.audio = (item.audioFiles || []).join(", ");
    option.textContent = `${item.name}${item.audioFiles?.length ? ` · ${item.audioFiles.join(", ")}` : " · нет аудио"}`;
    select.appendChild(option);
  }

  updateAudioLabel();
}

function updateAudioLabel() {
  const selected = $("consultationSelect").selectedOptions[0];
  $("audioFileName").textContent = selected?.dataset.audio || "—";
  $("transferMode").textContent = $("runMode").value === "realtime"
    ? "realtime chunks"
    : "batch transcript file";
}

async function runPipeline() {
  const payload = {
    consultation: $("consultationSelect").value,
    redisHost: $("redisHost").value.trim(),
    redisPort: $("redisPort").value.trim(),
    mode: $("runMode").value,
    realtimeFactor: Number.parseFloat($("realtimeFactor").value) || 0,
    limit: Number.parseInt($("limit").value, 10) || 0,
  };
  logEvent({ action: "run", ...payload });
  const response = await fetchJson("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    logEvent(response.error || "Не удалось запустить pipeline");
  }
  startPolling();
}

async function stopPipeline() {
  await fetchJson("/api/stop", { method: "POST" });
  await refresh();
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  refresh();
  pollTimer = setInterval(refresh, 1200);
}

$("runBtn").addEventListener("click", () => runPipeline().catch((error) => logEvent(String(error))));
$("stopBtn").addEventListener("click", () => stopPipeline().catch((error) => logEvent(String(error))));
$("refreshBtn").addEventListener("click", () => refresh().catch((error) => logEvent(String(error))));
$("consultationSelect").addEventListener("change", updateAudioLabel);
$("runMode").addEventListener("change", updateAudioLabel);

async function init() {
  await loadDefaults();
  await loadConsultations();
  resetArticleLibrary();
  renderLegalAnalysis("");
  await refresh();
  startPolling();
}

init().catch((error) => {
  setStatus("UI error", "err");
  logEvent(String(error));
});
