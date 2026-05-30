const API_BASE = window.location.origin;
const TARGET_SAMPLE_RATE = 16000;

let sessionId = null;
let enrollRecorder = null;
let enrollChunks = [];
let enrollTimer = null;
let enrollStartedAt = null;

let ws = null;
let audioContext = null;
let micStream = null;
let processor = null;
let sourceNode = null;
let sentSamples = 0;

let pairedUpdateCounter = 0;
let pairedUpdateKeys = new Set();
let transcriptSegmentKeys = new Set();
let articleStore = new Map();
let activeArticleKey = null;

const HIDDEN_CLARIFY_ANSWER =
  "Текущий кусок транскрипции выглядит как неполный или еще не до конца сформулированный вопрос. Нужна короткая уточняющая реплика, прежде чем отдавать финальный правовой ответ.";

const $ = (id) => document.getElementById(id);

const statusBadge = $("statusBadge");
const eventsLog = $("eventsLog");
const conversationTimelineEl = $("conversationTimeline");
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
const articleLibraryEl = $("articleLibrary");
const articleViewerEl = $("articleViewer");
const enrollResultEl = $("enrollResult");

function setStatus(text, cls = "") {
  statusBadge.textContent = text;
  statusBadge.className = `badge ${cls}`.trim();
}

function setBadge(el, text, cls = "") {
  if (!el) return;
  el.textContent = text;
  el.className = `badge ${cls}`.trim();
}

function logEvent(obj) {
  const text = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  eventsLog.textContent = `${text}\n\n${eventsLog.textContent}`.slice(0, 30000);
}

function logError(err) {
  const message = err && err.stack ? err.stack : String(err);
  console.error(err);
  logEvent(message);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderList(el, items, formatter = (item) => item) {
  if (!el) return;
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

function renderEnrollmentResult(data, sourceLabel = "file") {
  if (!enrollResultEl) return;
  if (!data) {
    enrollResultEl.innerHTML = "";
    return;
  }

  const enrolled = Boolean(data.enrolled);
  const duration =
    data.lawyer_profile_seconds !== undefined && data.lawyer_profile_seconds !== null
      ? `${Number(data.lawyer_profile_seconds).toFixed(1)} сек`
      : "—";
  const threshold =
    data.similarity_threshold !== undefined && data.similarity_threshold !== null
      ? Number(data.similarity_threshold).toFixed(2)
      : "—";

  enrollResultEl.innerHTML = `
    <div class="user-status compact ${enrolled ? "success" : "warning"}">
      <div class="user-status-title">
        ${enrolled ? "Голос юриста загружен" : "Голос юриста не загружен"}
      </div>
      <div class="user-status-meta">
        <span>Источник: ${escapeHtml(sourceLabel)}</span>
        <span>Длительность: ${escapeHtml(duration)}</span>
        <span>Порог: ${escapeHtml(threshold)}</span>
      </div>
    </div>
  `;
}

function shouldHideLegalOutput(payload) {
  if (!payload) return false;
  const answerText = String(payload?.answer?.text || "").trim();
  if (answerText === HIDDEN_CLARIFY_ANSWER) return true;
  const route = String(payload?.route || "").trim().toLowerCase();
  if (route === "idle") return true;
  if (route === "clarify") return true;
  if (payload?.needs_clarification) return true;
  const hasAnswer = answerText.length > 0;
  const hasArticles = Boolean(payload?.retrieved_articles?.length);
  const hasQuestion =
    Boolean(String(payload?.question || "").trim()) ||
    Boolean(payload?.questions?.filter((item) => String(item || "").trim()).length);

  if (!hasAnswer && !hasArticles) return true;
  if (!hasAnswer && !hasQuestion) return true;
  return false;
}

function setSessionControls(enabled) {
  $("startEnrollBtn").disabled = !enabled;
  $("enrollFile").disabled = !enabled;
  $("uploadEnrollBtn").disabled = !enabled;
  $("startStreamBtn").disabled = !enabled;
  $("consultationFile").disabled = !enabled;
  $("streamFileBtn").disabled = !enabled;
  $("downloadTranscriptBtn").disabled = !enabled;
}

function renderLegalAnalysis(payload, bridgeError = null) {
  if (payload && shouldHideLegalOutput(payload)) {
    return;
  }
  setBadge(legalRouteEl, payload?.route || "—", payload?.route ? "ok" : "");

  if (payload?.fact_check?.grounded === true) {
    setBadge(legalGroundedEl, "grounded", "ok");
  } else if (payload?.fact_check?.grounded === false) {
    setBadge(legalGroundedEl, "needs review", "warn");
  } else {
    setBadge(legalGroundedEl, "—");
  }

  legalConfidenceEl.textContent =
    payload?.fact_check?.confidence !== undefined && payload?.fact_check?.confidence !== null
      ? Number(payload.fact_check.confidence).toFixed(2)
      : "—";
  legalQuestionEl.textContent = payload?.question || "—";
  legalAnswerEl.textContent = payload?.answer?.text || "—";
  lawyerCheckStatusEl.textContent = payload?.lawyer_phrase_check?.status || "—";
  legalBridgeErrorEl.textContent = bridgeError ? `Bridge error: ${bridgeError}` : "";

  renderList(legalQuestionsEl, payload?.questions || [], (item) => escapeHtml(item));
  renderList(
    legalArticlesEl,
    payload?.retrieved_articles || [],
    (item) =>
      `<b>ст. ${escapeHtml(item.article_number)}</b> ${escapeHtml(item.title)} ` +
      `<span class="score">score=${Number(item.final_score).toFixed(2)}</span>`
  );
  renderList(
    lawyerFlaggedPhrasesEl,
    payload?.lawyer_phrase_check?.flagged_phrases || [],
    (item) => escapeHtml(item)
  );

  const combinedErrors = [];
  if (payload?.errors?.length) combinedErrors.push(...payload.errors);
  if (payload?.answer?.generation_error) {
    combinedErrors.push(`generation: ${payload.answer.generation_error}`);
  }
  if (bridgeError) {
    combinedErrors.push(`bridge: ${bridgeError}`);
  }
  renderList(legalErrorsEl, combinedErrors, (item) => escapeHtml(item));
}

function formatTranscriptChunk(payload) {
  if (!payload) return "Transcript chunk is not available.";
  if (payload.transcript_chunk && payload.transcript_chunk.trim()) {
    return payload.transcript_chunk.trim();
  }
  const utterances = payload.utterances || [];
  if (!utterances.length) return "Transcript chunk is not available.";
  return utterances
    .map((item) => `${item.speaker || "Unknown"}: ${item.text || ""}`.trim())
    .join("\n");
}

function normalizeSpeakerRole(rawSpeaker) {
  const value = String(rawSpeaker || "").trim().toLowerCase();
  if (value === "lawyer") return "lawyer";
  if (value === "client") return "client";
  return "unknown";
}

function speakerLabel(rawSpeaker) {
  const role = normalizeSpeakerRole(rawSpeaker);
  if (role === "lawyer") return "Lawyer";
  if (role === "client") return "Client";
  return "Unknown";
}

function appendTranscriptSegments(segments) {
  if (!conversationTimelineEl || !segments?.length) return;

  for (const segment of segments) {
    const key = JSON.stringify([
      segment.segment_id ?? null,
      segment.start_time ?? null,
      segment.end_time ?? null,
      segment.speaker ?? null,
      segment.text ?? "",
    ]);
    if (transcriptSegmentKeys.has(key)) continue;
    transcriptSegmentKeys.add(key);

    const role = normalizeSpeakerRole(segment.speaker);
    const label = speakerLabel(segment.speaker);
    const line = document.createElement("div");
    line.className = `chat-line ${role}`;
    line.innerHTML = `
      <div class="chat-bubble ${role}">
        <div class="chat-speaker">${escapeHtml(label)}</div>
        <div class="chat-text">${escapeHtml(segment.text || "")}</div>
      </div>
    `;
    conversationTimelineEl.appendChild(line);
  }

  conversationTimelineEl.scrollTop = conversationTimelineEl.scrollHeight;
}

function resetConversationTimeline() {
  if (conversationTimelineEl) {
    conversationTimelineEl.innerHTML = "";
  }
  transcriptSegmentKeys = new Set();
  pairedUpdateCounter = 0;
  pairedUpdateKeys = new Set();
}

async function syncTranscriptFromServer() {
  if (!sessionId) return;

  const resp = await fetch(`${API_BASE}/sessions/${sessionId}/transcript`);
  if (!resp.ok) throw new Error(await resp.text());

  const data = await resp.json();
  appendTranscriptSegments(data.segments || []);
  return data;
}

function renderTranscriptChatHtml(payload) {
  const utterances = payload?.utterances || [];
  if (utterances.length) {
    return utterances
      .map((item) => {
        const role = normalizeSpeakerRole(item.speaker);
        const label = item.speaker || "Unknown";
        return `
          <div class="chat-line ${role}">
            <div class="chat-bubble ${role}">
              <div class="chat-speaker">${escapeHtml(label)}</div>
              <div class="chat-text">${escapeHtml(item.text || "")}</div>
            </div>
          </div>
        `;
      })
      .join("");
  }

  const transcriptChunk = formatTranscriptChunk(payload);
  const lines = transcriptChunk
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (!lines.length) {
    return `<div class="chat-empty">Transcript chunk is not available.</div>`;
  }

  return lines
    .map((line) => {
      const match = line.match(/^([^:]+):\s*(.*)$/);
      const label = match ? match[1].trim() : "Unknown";
      const text = match ? match[2].trim() : line;
      const role = normalizeSpeakerRole(label);
      return `
        <div class="chat-line ${role}">
          <div class="chat-bubble ${role}">
            <div class="chat-speaker">${escapeHtml(label)}</div>
            <div class="chat-text">${escapeHtml(text)}</div>
          </div>
        </div>
      `;
    })
    .join("");
}

function buildPairedUpdateKey(payload, bridgeError = null) {
  if (bridgeError) return `error:${bridgeError}`;
  if (!payload) return "empty";
  return JSON.stringify({
    route: payload.route || null,
    transcript_chunk: payload.transcript_chunk || null,
    question: payload.question || null,
    questions: payload.questions || [],
    answer: payload.answer?.text || null,
    articles: (payload.retrieved_articles || []).map((item) => item.article_number),
    errors: payload.errors || [],
    finalized: payload.finalized || false,
  });
}

function articleKey(article) {
  return `${article.article_number}::${article.title}`;
}

function resetArticleLibrary() {
  articleStore = new Map();
  activeArticleKey = null;
  if (articleLibraryEl) {
    articleLibraryEl.innerHTML = "";
  }
  if (articleViewerEl) {
    articleViewerEl.className = "article-viewer empty";
    articleViewerEl.innerHTML = `
      <div class="article-viewer-title">Текст статьи</div>
      <div class="article-viewer-body">Выберите статью из списка слева, чтобы открыть полный текст.</div>
    `;
  }
}

function renderArticleViewer(article) {
  if (!articleViewerEl || !article) return;
  articleViewerEl.className = "article-viewer";
  articleViewerEl.innerHTML = `
    <div class="article-viewer-title">Статья ${escapeHtml(article.article_number)}. ${escapeHtml(article.title)}</div>
    <div class="article-viewer-subtitle">Score: ${Number(article.final_score || 0).toFixed(2)}</div>
    <div class="article-viewer-summary">${escapeHtml(article.summary || "Краткое описание отсутствует.")}</div>
    <div class="article-viewer-body">${escapeHtml(article.text || "Полный текст статьи отсутствует в payload.")}</div>
  `;
}

function renderArticleLibrary() {
  if (!articleLibraryEl) return;
  articleLibraryEl.innerHTML = "";

  const articles = Array.from(articleStore.values()).sort((a, b) => {
    return Number(b.final_score || 0) - Number(a.final_score || 0);
  });

  if (!articles.length) {
    articleLibraryEl.innerHTML = `<div class="article-item"><div class="article-item-summary">Статьи пока не рекомендованы.</div></div>`;
    return;
  }

  for (const article of articles) {
    const key = articleKey(article);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `article-item ${activeArticleKey === key ? "active" : ""}`;
    button.innerHTML = `
      <div class="article-item-title">Статья ${escapeHtml(article.article_number)}. ${escapeHtml(article.title)}</div>
      <div class="article-item-meta">Score: ${Number(article.final_score || 0).toFixed(2)}</div>
      <div class="article-item-summary">${escapeHtml(article.summary || "Краткое описание отсутствует.")}</div>
    `;
    button.addEventListener("click", () => {
      activeArticleKey = key;
      renderArticleLibrary();
      renderArticleViewer(article);
    });
    articleLibraryEl.appendChild(button);
  }
}

function collectArticlesFromPayload(payload) {
  if (!payload || shouldHideLegalOutput(payload)) return;

  for (const article of payload.retrieved_articles || []) {
    const key = articleKey(article);
    const existing = articleStore.get(key);
    if (!existing || Number(article.final_score || 0) > Number(existing.final_score || 0)) {
      articleStore.set(key, article);
    }
  }

  if (!activeArticleKey) {
    const first = Array.from(articleStore.values()).sort((a, b) => Number(b.final_score || 0) - Number(a.final_score || 0))[0];
    if (first) {
      activeArticleKey = articleKey(first);
      renderArticleViewer(first);
    }
  } else if (articleStore.has(activeArticleKey)) {
    renderArticleViewer(articleStore.get(activeArticleKey));
  }

  renderArticleLibrary();
}

function appendLegalHint(payload, bridgeError = null) {
  if (!conversationTimelineEl) return;
  if (payload && shouldHideLegalOutput(payload)) return;

  const key = buildPairedUpdateKey(payload, bridgeError);
  if (pairedUpdateKeys.has(key)) return;
  pairedUpdateKeys.add(key);
  pairedUpdateCounter += 1;

  const route = payload?.route || "—";
  const question = payload?.question || payload?.questions?.[0] || "Question not detected yet.";
  const answer = payload?.answer?.text || "Answer is not available yet.";
  const articles = (payload?.retrieved_articles || [])
    .map((item) => `ст. ${escapeHtml(item.article_number)} ${escapeHtml(item.title)}`)
    .join("<br>");
  const warnings = [
    ...(payload?.errors || []),
    ...(payload?.answer?.generation_error ? [`generation: ${payload.answer.generation_error}`] : []),
    ...(bridgeError ? [`bridge: ${bridgeError}`] : []),
  ];

  const card = document.createElement("div");
  card.className = "timeline-legal-card";
  card.innerHTML = `
    <div class="timeline-legal-header">
      <div class="timeline-legal-title">LegalCopilot prompt ${pairedUpdateCounter}</div>
      <div class="timeline-meta">${payload?.finalized ? "finalized" : "live"}</div>
      <span class="badge ${payload?.route ? "ok" : ""}">${escapeHtml(route)}</span>
    </div>
    <div class="timeline-legal-body">
      <div class="line"><b>Question:</b> ${escapeHtml(question)}</div>
      <div class="line"><b>Answer:</b> ${escapeHtml(answer)}</div>
      <div class="line"><b>Articles:</b><br>${articles || "—"}</div>
      <div class="line"><b>Warnings:</b><br>${warnings.length ? warnings.map(escapeHtml).join("<br>") : "—"}</div>
    </div>
  `;

  conversationTimelineEl.appendChild(card);
  conversationTimelineEl.scrollTop = conversationTimelineEl.scrollHeight;
}

function appendLegalHistory(history, bridgeError = null) {
  for (const payload of history || []) {
    collectArticlesFromPayload(payload);
    appendLegalHint(payload, null);
  }
  if ((!history || !history.length) && bridgeError) {
    appendLegalHint(null, bridgeError);
  }
}

async function createSession() {
  const title = $("sessionTitle").value || null;
  const thresholdRaw = $("speakerThreshold").value;
  const threshold = thresholdRaw ? Number(thresholdRaw) : null;

  const resp = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      speaker_similarity_threshold: threshold,
    }),
  });

  if (!resp.ok) throw new Error(await resp.text());

  const data = await resp.json();
  sessionId = data.session_id;
  $("sessionId").textContent = data.session_id;
  resetConversationTimeline();
  resetArticleLibrary();
  renderLegalAnalysis(null, null);
  setSessionControls(true);
  setStatus("Session created", "ok");
  logEvent(data);
}

async function uploadEnrollFile(file, sourceLabel = "загруженный аудиофайл") {
  if (!sessionId) throw new Error("Session is not created.");

  const form = new FormData();
  form.append("file", file, file.name || "lawyer_enrollment.webm");

  const resp = await fetch(`${API_BASE}/sessions/${sessionId}/enroll`, {
    method: "POST",
    body: form,
  });

  if (!resp.ok) throw new Error(await resp.text());

  const data = await resp.json();
  renderEnrollmentResult(data, sourceLabel);
  logEvent(data);
}

function resetEnrollTimer() {
  enrollStartedAt = null;
  if (enrollTimer) {
    clearInterval(enrollTimer);
    enrollTimer = null;
  }
  $("enrollAudioSec").textContent = "0.0";
}

function startEnrollTimer() {
  enrollStartedAt = performance.now();
  $("enrollAudioSec").textContent = "0.0";
  if (enrollTimer) clearInterval(enrollTimer);
  enrollTimer = setInterval(() => {
    if (!enrollStartedAt) return;
    const elapsed = (performance.now() - enrollStartedAt) / 1000.0;
    $("enrollAudioSec").textContent = elapsed.toFixed(1);
  }, 100);
}

function stopEnrollTimer() {
  if (enrollTimer) {
    clearInterval(enrollTimer);
    enrollTimer = null;
  }
  if (enrollStartedAt) {
    const elapsed = (performance.now() - enrollStartedAt) / 1000.0;
    $("enrollAudioSec").textContent = elapsed.toFixed(1);
  }
}

async function startEnrollRecording() {
  if (!sessionId) throw new Error("Session is not created.");
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("getUserMedia is not available. Use localhost or HTTPS.");
  }
  if (typeof MediaRecorder === "undefined") {
    throw new Error("MediaRecorder is not available in this browser.");
  }

  enrollChunks = [];
  resetEnrollTimer();

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  let options = {};
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
    options = { mimeType: "audio/webm;codecs=opus" };
  } else if (MediaRecorder.isTypeSupported("audio/webm")) {
    options = { mimeType: "audio/webm" };
  }

  enrollRecorder = new MediaRecorder(stream, options);
  enrollRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) enrollChunks.push(event.data);
  };
  enrollRecorder.onerror = (event) => {
    logError(event.error || event);
    setStatus("Enrollment recorder error", "err");
  };
  enrollRecorder.onstart = () => {
    setStatus("Recording lawyer voice", "warn");
    startEnrollTimer();
    logEvent("Enrollment recording started");
  };
  enrollRecorder.onstop = async () => {
    stopEnrollTimer();
    try {
      const blob = new Blob(enrollChunks, {
        type: enrollRecorder.mimeType || "audio/webm",
      });
      if (blob.size === 0) throw new Error("Enrollment recording is empty.");
      const file = new File([blob], "lawyer_enrollment.webm", { type: blob.type });
      await uploadEnrollFile(file, "запись в браузере");
      setStatus("Lawyer voice saved", "ok");
    } catch (err) {
      setStatus("Enrollment failed", "err");
      logError(err);
    } finally {
      stream.getTracks().forEach((track) => track.stop());
      $("startEnrollBtn").disabled = false;
      $("stopEnrollBtn").disabled = true;
    }
  };

  enrollRecorder.start(250);
  $("startEnrollBtn").disabled = true;
  $("stopEnrollBtn").disabled = false;
}

function stopEnrollRecording() {
  if (enrollRecorder && enrollRecorder.state !== "inactive") {
    enrollRecorder.stop();
  }
}

function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/audio/${sessionId}`;
}

function openAudioWebSocket() {
  return new Promise((resolve, reject) => {
    ws = new WebSocket(wsUrl());
    ws.binaryType = "arraybuffer";
    let settled = false;

    ws.onopen = () => {
      $("wsState").textContent = "connected";
      setStatus("WebSocket connected", "ok");
      logEvent("WebSocket connected");
      settled = true;
      resolve(ws);
    };

    ws.onmessage = (event) => {
      try {
        const obj = JSON.parse(event.data);
        logEvent(obj);

        if (obj.event === "legal_update") {
          const payload = obj.payload?.error ? null : obj.payload;
          const bridgeError = obj.payload?.error || null;
          collectArticlesFromPayload(payload);
          renderLegalAnalysis(payload, bridgeError);
          appendLegalHint(payload, bridgeError);
        }

        if (obj.event === "partial") {
          appendTranscriptSegments(obj.payload?.segments || []);
        }

        if (obj.event === "final") {
          $("wsState").textContent = "finalized";
          setStatus("Finalized", "ok");
          const history =
            obj.payload?.legal_copilot_history?.length
              ? obj.payload.legal_copilot_history
              : (obj.payload?.legal_copilot ? [obj.payload.legal_copilot] : []);
          renderLegalAnalysis(
            obj.payload?.legal_copilot || null,
            obj.payload?.legal_copilot_error || null
          );
          appendLegalHistory(
            history,
            obj.payload?.legal_copilot_error || null
          );
          $("downloadTranscriptBtn").disabled = false;
          syncTranscriptFromServer().catch(logError);
        }

        if (obj.event === "error") {
          setStatus("Server error", "err");
        }
      } catch (err) {
        logError(err);
        logEvent(event.data);
      }
    };

    ws.onerror = () => {
      $("wsState").textContent = "error";
      setStatus("WebSocket error", "err");
      logEvent("WebSocket error");
      if (!settled) {
        settled = true;
        reject(new Error("WebSocket error"));
      }
    };

    ws.onclose = () => {
      $("wsState").textContent = "closed";
      stopMicAudioOnly();
      if (!settled) {
        settled = true;
        reject(new Error("WebSocket closed before connection was established."));
      }
    };
  });
}

async function startStreamingMic() {
  if (!sessionId) throw new Error("Session is not created.");
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("getUserMedia is not available. Use localhost or HTTPS.");
  }

  resetConversationTimeline();
  resetArticleLibrary();
  renderLegalAnalysis(null, null);
  sentSamples = 0;
  $("sentAudioSec").textContent = "0.0";
  $("audioSourceMode").textContent = "microphone";
  $("startStreamBtn").disabled = true;
  $("stopStreamBtn").disabled = false;
  $("streamFileBtn").disabled = true;

  setStatus("Starting microphone", "warn");
  await openAudioWebSocket();
  await startMicAudio();
  setStatus("Microphone connected", "ok");
}

async function startMicAudio() {
  micStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) throw new Error("AudioContext is not available in this browser.");

  audioContext = new AudioContextClass();
  if (audioContext.state === "suspended") await audioContext.resume();

  logEvent({
    message: "AudioContext started",
    sampleRate: audioContext.sampleRate,
    state: audioContext.state,
  });

  sourceNode = audioContext.createMediaStreamSource(micStream);
  processor = audioContext.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = (event) => {
    try {
      const input = event.inputBuffer.getChannelData(0);
      if (!input || input.length === 0) return;
      const resampled = resampleLinear(input, audioContext.sampleRate, TARGET_SAMPLE_RATE);
      if (!resampled || resampled.length === 0) return;
      const pcm16 = floatTo16BitPCM(resampled);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(pcm16.buffer);
        sentSamples += resampled.length;
        $("sentAudioSec").textContent = (sentSamples / TARGET_SAMPLE_RATE).toFixed(1);
      }
    } catch (err) {
      logError(err);
    }
  };

  sourceNode.connect(processor);
  processor.connect(audioContext.destination);
}

function stopStreamingMic() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "finalize" }));
  }
  stopMicAudioOnly();
}

function stopMicAudioOnly() {
  if (processor) {
    try { processor.disconnect(); } catch {}
    processor.onaudioprocess = null;
    processor = null;
  }
  if (sourceNode) {
    try { sourceNode.disconnect(); } catch {}
    sourceNode = null;
  }
  if (audioContext) {
    try { audioContext.close(); } catch {}
    audioContext = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }

  $("startStreamBtn").disabled = !sessionId;
  $("stopStreamBtn").disabled = true;
  $("streamFileBtn").disabled = !sessionId;
}

async function streamConsultationFile() {
  if (!sessionId) throw new Error("Session is not created.");
  const file = $("consultationFile").files?.[0];
  if (!file) throw new Error("Choose consultation audio file first.");

  resetConversationTimeline();
  resetArticleLibrary();
  renderLegalAnalysis(null, null);
  sentSamples = 0;
  $("sentAudioSec").textContent = "0.0";
  $("audioSourceMode").textContent = "file";
  $("startStreamBtn").disabled = true;
  $("stopStreamBtn").disabled = false;
  $("streamFileBtn").disabled = true;

  setStatus("Decoding file", "warn");
  const audio = await decodeAudioFileToMono16k(file);
  logEvent({
    message: "Consultation file decoded",
    file: file.name,
    samples: audio.length,
    sampleRate: TARGET_SAMPLE_RATE,
    durationSec: audio.length / TARGET_SAMPLE_RATE,
  });

  await openAudioWebSocket();
  setStatus("Streaming file", "warn");
  await sendAudioFloat32Realtime(audio, TARGET_SAMPLE_RATE, 300);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "finalize" }));
  }
  setStatus("Waiting for finalization", "warn");
}

async function decodeAudioFileToMono16k(file) {
  const arrayBuffer = await file.arrayBuffer();
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) throw new Error("AudioContext is not available in this browser.");

  const ctx = new AudioContextClass();
  try {
    const decoded = await ctx.decodeAudioData(arrayBuffer.slice(0));
    const mono = mixToMono(decoded);
    return resampleLinear(mono, decoded.sampleRate, TARGET_SAMPLE_RATE);
  } finally {
    try { await ctx.close(); } catch {}
  }
}

function mixToMono(audioBuffer) {
  const channels = audioBuffer.numberOfChannels;
  const length = audioBuffer.length;
  if (channels === 1) {
    return new Float32Array(audioBuffer.getChannelData(0));
  }

  const mono = new Float32Array(length);
  for (let ch = 0; ch < channels; ch++) {
    const data = audioBuffer.getChannelData(ch);
    for (let i = 0; i < length; i++) {
      mono[i] += data[i] / channels;
    }
  }
  return mono;
}

async function sendAudioFloat32Realtime(audio, sampleRate, blockMs) {
  const blockSamples = Math.max(1, Math.floor((sampleRate * blockMs) / 1000));
  const totalSamples = audio.length;

  for (let start = 0; start < totalSamples; start += blockSamples) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket is not open while streaming file.");
    }
    const end = Math.min(start + blockSamples, totalSamples);
    const chunk = audio.subarray(start, end);
    const pcm16 = floatTo16BitPCM(chunk);
    ws.send(pcm16.buffer);
    sentSamples += chunk.length;
    $("sentAudioSec").textContent = (sentSamples / sampleRate).toFixed(1);
    await sleep(blockMs);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function loadTranscript() {
  if (!sessionId) return null;
  resetConversationTimeline();
  const data = await syncTranscriptFromServer();
  resetArticleLibrary();
  const history =
    data.metadata?.legal_copilot_history?.length
      ? data.metadata.legal_copilot_history
      : (data.metadata?.legal_copilot ? [data.metadata.legal_copilot] : []);
  renderLegalAnalysis(
    data.metadata?.legal_copilot || null,
    data.metadata?.legal_bridge_error || null
  );
  appendLegalHistory(
    history,
    data.metadata?.legal_bridge_error || null
  );
  logEvent(data);
  return data;
}

async function downloadTranscriptJson() {
  if (!sessionId) throw new Error("Session is not created.");
  const resp = await fetch(`${API_BASE}/sessions/${sessionId}/transcript`);
  if (!resp.ok) throw new Error(await resp.text());

  const data = await resp.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `transcript_${sessionId}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function floatTo16BitPCM(float32Array) {
  const out = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const sample = Math.max(-1, Math.min(1, float32Array[i]));
    out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return out;
}

function resampleLinear(input, inputRate, outputRate) {
  if (inputRate === outputRate) return new Float32Array(input);
  const ratio = inputRate / outputRate;
  const outputLength = Math.floor(input.length / ratio);
  const output = new Float32Array(outputLength);

  for (let i = 0; i < outputLength; i++) {
    const pos = i * ratio;
    const idx = Math.floor(pos);
    const frac = pos - idx;
    const s0 = input[idx] || 0;
    const s1 = input[idx + 1] || s0;
    output[i] = s0 + frac * (s1 - s0);
  }
  return output;
}

$("createSessionBtn").addEventListener("click", async () => {
  try {
    await createSession();
  } catch (err) {
    setStatus("Session creation failed", "err");
    logError(err);
  }
});

$("startEnrollBtn").addEventListener("click", async () => {
  try {
    await startEnrollRecording();
  } catch (err) {
    setStatus("Voice recording failed", "err");
    logError(err);
    $("startEnrollBtn").disabled = false;
    $("stopEnrollBtn").disabled = true;
  }
});

$("stopEnrollBtn").addEventListener("click", stopEnrollRecording);

$("uploadEnrollBtn").addEventListener("click", async () => {
  try {
    const file = $("enrollFile").files?.[0];
    if (!file) throw new Error("Choose enrollment audio file first.");
    await uploadEnrollFile(file, "загруженный аудиофайл");
    setStatus("Enrollment uploaded", "ok");
  } catch (err) {
    setStatus("Enrollment failed", "err");
    logError(err);
  }
});

$("startStreamBtn").addEventListener("click", async () => {
  try {
    await startStreamingMic();
  } catch (err) {
    setStatus("Microphone failed", "err");
    logError(err);
    stopMicAudioOnly();
  }
});

$("stopStreamBtn").addEventListener("click", stopStreamingMic);

$("streamFileBtn").addEventListener("click", async () => {
  try {
    await streamConsultationFile();
  } catch (err) {
    setStatus("File streaming failed", "err");
    logError(err);
    stopMicAudioOnly();
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.close(); } catch {}
    }
  }
});

$("downloadTranscriptBtn").addEventListener("click", async () => {
  try {
    await downloadTranscriptJson();
  } catch (err) {
    setStatus("Transcript download failed", "err");
    logError(err);
  }
});

setStatus("Waiting for session", "warn");
setSessionControls(false);
resetEnrollTimer();
resetConversationTimeline();
resetArticleLibrary();
renderLegalAnalysis(null, null);
renderEnrollmentResult(null);
