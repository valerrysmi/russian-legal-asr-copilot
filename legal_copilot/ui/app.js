async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

const ARTICLE_TEXTS = {
  "93": `1. Р”РѕР»СЏ РІ СѓСЃС‚Р°РІРЅРѕРј РєР°РїРёС‚Р°Р»Рµ РѕР±С‰РµСЃС‚РІР° СЃ РѕРіСЂР°РЅРёС‡РµРЅРЅРѕР№ РѕС‚РІРµС‚СЃС‚РІРµРЅРЅРѕСЃС‚СЊСЋ РјРѕР¶РµС‚ РїРµСЂРµР№С‚Рё Рє РґСЂСѓРіРѕРјСѓ Р»РёС†Сѓ РЅР° РѕСЃРЅРѕРІР°РЅРёРё СЃРґРµР»РєРё, РІ РїРѕСЂСЏРґРєРµ РїСЂР°РІРѕРїСЂРµРµРјСЃС‚РІР° Р»РёР±Рѕ РЅР° РёРЅРѕРј Р·Р°РєРѕРЅРЅРѕРј РѕСЃРЅРѕРІР°РЅРёРё.\n\n2. РЈС‡Р°СЃС‚РЅРёРє РѕР±С‰РµСЃС‚РІР° РІРїСЂР°РІРµ РїСЂРѕРґР°С‚СЊ РёР»Рё РёРЅС‹Рј РѕР±СЂР°Р·РѕРј РѕС‚С‡СѓР¶РґР°С‚СЊ СЃРІРѕСЋ РґРѕР»СЋ СЃ СѓС‡РµС‚РѕРј РѕРіСЂР°РЅРёС‡РµРЅРёР№, СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅС‹С… Р·Р°РєРѕРЅРѕРј Рё СѓСЃС‚Р°РІРѕРј РѕР±С‰РµСЃС‚РІР°.\n\n3. РџСЂРё РѕС‚РІРµС‚Рµ РЅР° РІРѕРїСЂРѕСЃС‹ Рѕ РїСЂРѕРґР°Р¶Рµ РґРѕР»Рё СЃРёСЃС‚РµРјР° РІ РїРµСЂРІСѓСЋ РѕС‡РµСЂРµРґСЊ РѕРїРёСЂР°РµС‚СЃСЏ РЅР° СЌС‚Сѓ РЅРѕСЂРјСѓ РєР°Рє РЅР° Р±Р°Р·РѕРІСѓСЋ СЃС‚Р°С‚СЊСЋ Рѕ РїРµСЂРµС…РѕРґРµ РґРѕР»Рё Рє РґСЂСѓРіРѕРјСѓ Р»РёС†Сѓ.`,
  "166": `1. РЎРґРµР»РєР° РјРѕР¶РµС‚ Р±С‹С‚СЊ РЅРµРґРµР№СЃС‚РІРёС‚РµР»СЊРЅРѕР№ РїРѕ РѕСЃРЅРѕРІР°РЅРёСЏРј, СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅС‹Рј Р·Р°РєРѕРЅРѕРј.\n\n2. РќРµРґРµР№СЃС‚РІРёС‚РµР»СЊРЅС‹Рµ СЃРґРµР»РєРё РїРѕРґСЂР°Р·РґРµР»СЏСЋС‚СЃСЏ РЅР° РѕСЃРїРѕСЂРёРјС‹Рµ Рё РЅРёС‡С‚РѕР¶РЅС‹Рµ.\n\n3. Р”Р»СЏ legal_copilot СЌС‚Р° СЃС‚Р°С‚СЊСЏ РІР°Р¶РЅР° РІ С‚РµС… СЃС†РµРЅР°СЂРёСЏС…, РіРґРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ СЃРїСЂР°С€РёРІР°РµС‚ Рѕ СЂРёСЃРєР°С… РѕСЃРїР°СЂРёРІР°РЅРёСЏ СЃРґРµР»РєРё СЃ РґРѕР»РµР№ Р»РёР±Рѕ Рѕ РїРѕСЃР»РµРґСЃС‚РІРёСЏС… РЅР°СЂСѓС€РµРЅРёСЏ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹С… С‚СЂРµР±РѕРІР°РЅРёР№ Рє РµРµ РѕС„РѕСЂРјР»РµРЅРёСЋ.`,
  "181.1": `1. Р РµС€РµРЅРёСЏ СЃРѕР±СЂР°РЅРёР№ РїРѕСЂРѕР¶РґР°СЋС‚ РіСЂР°Р¶РґР°РЅСЃРєРѕ-РїСЂР°РІРѕРІС‹Рµ РїРѕСЃР»РµРґСЃС‚РІРёСЏ, РµСЃР»Рё Р·Р°РєРѕРЅ СЃРІСЏР·С‹РІР°РµС‚ С‚Р°РєРёРµ РїРѕСЃР»РµРґСЃС‚РІРёСЏ СЃ РІРѕР»РµРёР·СЉСЏРІР»РµРЅРёРµРј СЃРѕР±СЂР°РЅРёСЏ.\n\n2. Р”Р»СЏ РІРѕРїСЂРѕСЃРѕРІ Рѕ РєРѕСЂРїРѕСЂР°С‚РёРІРЅС‹С… РіРѕР»РѕСЃР°С… Рё Рѕ РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё СЂРµС€РµРЅРёР№ РѕСЂРіР°РЅРѕРІ РѕР±С‰РµСЃС‚РІР° СЌС‚Р° СЃС‚Р°С‚СЊСЏ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РєР°Рє РѕР±С‰Р°СЏ СЂР°РјРєР° РґР»СЏ Р°РЅР°Р»РёР·Р° СЂРµС€РµРЅРёР№ СЃРѕР±СЂР°РЅРёР№ Рё РёС… СЋСЂРёРґРёС‡РµСЃРєРѕРіРѕ Р·РЅР°С‡РµРЅРёСЏ.`,
  "163": `1. РќРѕС‚Р°СЂРёР°Р»СЊРЅРѕРµ СѓРґРѕСЃС‚РѕРІРµСЂРµРЅРёРµ СЃРґРµР»РєРё РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ РІ СЃР»СѓС‡Р°СЏС…, РїСЂРµРґСѓСЃРјРѕС‚СЂРµРЅРЅС‹С… Р·Р°РєРѕРЅРѕРј РёР»Рё СЃРѕРіР»Р°С€РµРЅРёРµРј СЃС‚РѕСЂРѕРЅ.\n\n2. РќРµСЃРѕР±Р»СЋРґРµРЅРёРµ РЅРѕС‚Р°СЂРёР°Р»СЊРЅРѕР№ С„РѕСЂРјС‹ РІР»РµС‡РµС‚ РїРѕСЃР»РµРґСЃС‚РІРёСЏ, СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅС‹Рµ РіСЂР°Р¶РґР°РЅСЃРєРёРј Р·Р°РєРѕРЅРѕРґР°С‚РµР»СЊСЃС‚РІРѕРј.\n\n3. Р’ РґРµРјРѕРЅСЃС‚СЂР°С†РёРё СЌС‚Р° СЃС‚Р°С‚СЊСЏ СѓС‡Р°СЃС‚РІСѓРµС‚ С‚РѕРіРґР°, РєРѕРіРґР° СЃРёСЃС‚РµРјР° РѕР±СЉСЏСЃРЅСЏРµС‚ С‚РµС…РЅРёС‡РµСЃРєРёР№ РїРѕСЂСЏРґРѕРє РѕС„РѕСЂРјР»РµРЅРёСЏ РїРµСЂРµРґР°С‡Рё РґРѕР»Рё.`,
  "250": `1. РџСЂРё РїСЂРѕРґР°Р¶Рµ РґРѕР»Рё РјРѕР¶РµС‚ РёРјРµС‚СЊ Р·РЅР°С‡РµРЅРёРµ РїСЂРµРёРјСѓС‰РµСЃС‚РІРµРЅРЅРѕРµ РїСЂР°РІРѕ РїРѕРєСѓРїРєРё РґСЂСѓРіРёС… СѓРїСЂР°РІРѕРјРѕС‡РµРЅРЅС‹С… Р»РёС†, РµСЃР»Рё РѕРЅРѕ РїСЂРµРґСѓСЃРјРѕС‚СЂРµРЅРѕ Р·Р°РєРѕРЅРѕРј РёР»Рё СѓСЃС‚Р°РІРѕРј.\n\n2. РќР°СЂСѓС€РµРЅРёРµ С‚Р°РєРѕРіРѕ РїСЂР°РІР° СЃРїРѕСЃРѕР±РЅРѕ РїРѕСЂРѕРґРёС‚СЊ СЂРёСЃРє СЃРїРѕСЂР° Рё С‚СЂРµР±РѕРІР°РЅРёСЏ Рѕ РїРµСЂРµРІРѕРґРµ РїСЂР°РІ Рё РѕР±СЏР·Р°РЅРЅРѕСЃС‚РµР№ РїРѕРєСѓРїР°С‚РµР»СЏ.\n\n3. Р’ legal_copilot СЌС‚Р° СЃС‚Р°С‚СЊСЏ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РєР°Рє РѕРґРЅР° РёР· РєР»СЋС‡РµРІС‹С… РЅРѕСЂРј РїСЂРё Р°РЅР°Р»РёР·Рµ СЂРёСЃРєРѕРІ СЃРґРµР»РєРё.`
};

const timeline = document.getElementById("timeline");
const playBtn = document.getElementById("playBtn");
const resetBtn = document.getElementById("resetBtn");
const transcriptSelect = document.getElementById("transcriptSelect");
const userModeBtn = document.getElementById("userModeBtn");
const debugModeBtn = document.getElementById("debugModeBtn");
const userWorkspace = document.getElementById("userWorkspace");
const debugWorkspace = document.getElementById("debugWorkspace");
const backendNotice = document.getElementById("backendNotice");
const sessionLabel = document.getElementById("sessionLabel");

const incomingChunk = document.getElementById("incomingChunk");
const appendedTurns = document.getElementById("appendedTurns");
const activeQuestion = document.getElementById("activeQuestion");
const questionList = document.getElementById("questionList");
const questionCount = document.getElementById("questionCount");
const retrievalCount = document.getElementById("retrievalCount");
const groundingValue = document.getElementById("groundingValue");
const chunkName = document.getElementById("chunkName");
const appendedCount = document.getElementById("appendedCount");
const stageList = document.getElementById("stageList");
const retrievalBranchList = document.getElementById("retrievalBranchList");
const topicLabel = document.getElementById("topicLabel");
const answerSource = document.getElementById("answerSource");
const answerText = document.getElementById("answerText");
const factCheck = document.getElementById("factCheck");
const lawyerPhraseCheck = document.getElementById("lawyerPhraseCheck");

const userChunkLabel = document.getElementById("userChunkLabel");
const userActiveQuestion = document.getElementById("userActiveQuestion");
const userAnswerText = document.getElementById("userAnswerText");
const userArticleSort = document.getElementById("userArticleSort");
const userArticleList = document.getElementById("userArticleList");
const conversationList = document.getElementById("conversationList");
const articleModal = document.getElementById("articleModal");
const articleModalTitle = document.getElementById("articleModalTitle");
const articleModalMeta = document.getElementById("articleModalMeta");
const articleModalBody = document.getElementById("articleModalBody");
const articleModalClose = document.getElementById("articleModalClose");

let currentIndex = 0;
let autoplayTimer = null;
let currentArticleSort = "score";
let currentScenarioKey = "transcript_1.txt";
let currentSteps = [];
let scenarioLoading = false;

function logUi(event, details = {}) {
  const timestamp = new Date().toLocaleTimeString("ru-RU");
  console.log(`[legal_copilot ui ${timestamp}] ${event}`, details);
}

function showBackendNotice(message) {
  logUi("backend_notice", { message });
  if (!backendNotice) {
    return;
  }
  backendNotice.hidden = false;
  backendNotice.textContent = message;
}

function hideBackendNotice() {
  logUi("backend_notice_clear");
  if (!backendNotice) {
    return;
  }
  backendNotice.hidden = true;
  backendNotice.textContent = "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeComparableText(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[.,!?;:()[\]"]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function findLawyerFlagForMessage(message, check) {
  if (!check || message.role !== "assistant") {
    return null;
  }

  const messageText = normalizeComparableText(message.text);
  const flaggedItems = (check.flaggedItems || []).map((item) => ({
    phrase: item.phrase || "",
    comment: item.comment || check.summary || "Review this lawyer statement manually.",
  }));
  const fallbackPhrases = (check.flaggedPhrases || []).map((phrase) => ({
    phrase,
    comment: check.summary || "Review this lawyer statement manually.",
  }));
  const items = flaggedItems.length > 0 ? flaggedItems : fallbackPhrases;

  for (const item of items) {
    const normalizedPhrase = normalizeComparableText(item.phrase);
    if (!normalizedPhrase) {
      continue;
    }
    if (
      messageText.includes(normalizedPhrase) ||
      normalizedPhrase.includes(messageText)
    ) {
      return {
        phrase: item.phrase,
        comment: item.comment,
      };
    }
  }

  return null;
}

function collectConversationUntil(index) {
  const items = [];
  for (let i = 0; i <= index; i += 1) {
    const step = currentSteps[i];
    if (!step || !step.conversation) {
      continue;
    }
    for (const message of step.conversation) {
      const last = items[items.length - 1];
      if (
        last &&
        last.role === message.role &&
        last.text === message.text &&
        last.label === message.label
      ) {
        continue;
      }
      items.push({ ...message, chunkId: step.id });
    }
  }
  return items;
}

function collectTurnGroupsUntil(index) {
  const groups = [];
  for (let i = 0; i <= index; i += 1) {
    const step = currentSteps[i];
    if (!step) {
      continue;
    }
    groups.push({
      id: step.id,
      turns: step.appendedTurns || [],
    });
  }
  return groups;
}

function collectProcessedStepsUntil(index) {
  return currentSteps.slice(0, index + 1).filter((step) => step);
}

function createTimeline() {
  logUi("timeline_create", { stepCount: currentSteps.length });
  timeline.innerHTML = "";
  currentSteps.forEach((step, index) => {
    const button = document.createElement("button");
    button.className = "timeline-item";
    button.innerHTML = `
      <span class="timeline-title">${step.title}</span>
      <span class="timeline-subtitle">${step.subtitle}</span>
    `;
    button.addEventListener("click", () => {
      stopAutoplay();
      renderStep(index);
    });
    timeline.appendChild(button);
  });
}

function renderPrePlaybackState() {
  logUi("render_preplay_state", { stepCount: currentSteps.length });
  currentIndex = -1;

  [...timeline.children].forEach((node) => {
    node.classList.remove("active");
  });

  if (chunkName) {
    chunkName.textContent = "—";
  }
  if (incomingChunk) {
    incomingChunk.textContent = "";
  }
  if (activeQuestion) {
    activeQuestion.textContent = "";
  }
  if (questionCount) {
    questionCount.textContent = "0";
  }
  if (retrievalCount) {
    retrievalCount.textContent = "0";
  }
  if (groundingValue) {
    groundingValue.textContent = "—";
  }
  if (topicLabel) {
    topicLabel.textContent = "ready";
  }
  if (answerSource) {
    answerSource.textContent = "not_started";
  }
  if (answerText) {
    answerText.textContent = "";
  }
  if (factCheck) {
    factCheck.textContent = "";
  }
  if (lawyerPhraseCheck) {
    lawyerPhraseCheck.hidden = true;
    lawyerPhraseCheck.innerHTML = "";
  }
  if (appendedCount) {
    appendedCount.textContent = "0 new turns";
  }
  if (appendedTurns) {
    appendedTurns.innerHTML = "";
  }
  if (questionList) {
    questionList.innerHTML = "";
  }
  if (stageList) {
    stageList.innerHTML = "";
  }
  if (retrievalBranchList) {
    retrievalBranchList.innerHTML = "";
  }
  if (userChunkLabel) {
    userChunkLabel.textContent = "—";
  }
  if (userActiveQuestion) {
    userActiveQuestion.innerHTML = `
      <div class="result-empty-state">Нажмите «Проиграть шаги», чтобы начать обработку транскрипции.</div>
    `;
  }
  if (userAnswerText) {
    userAnswerText.innerHTML = `
      <div class="result-empty-state">Ответы появятся здесь по мере обработки новых чанков.</div>
    `;
  }
  if (conversationList) {
    conversationList.innerHTML = `
      <div class="result-empty-state transcript-empty-state">Обработанный диалог появится после запуска сценария.</div>
    `;
  }
  if (userArticleList) {
    userArticleList.innerHTML = `
      <div class="article-card compact article-empty">
        <p class="article-title">Ссылки на статьи пока не показаны</p>
        <p class="article-summary">Они будут накапливаться на странице по мере обработки чанков.</p>
      </div>
    `;
  }
}

function clearDemoView() {
  logUi("demo_clear");
  stopAutoplay();
  currentSteps = [];
  currentIndex = 0;
  if (playBtn) {
    playBtn.disabled = true;
    playBtn.textContent = "Проиграть шаги";
  }
  if (resetBtn) {
    resetBtn.disabled = true;
  }
  if (timeline) {
    timeline.innerHTML = "";
  }
  if (chunkName) {
    chunkName.textContent = "вЂ”";
  }
  if (incomingChunk) {
    incomingChunk.textContent = "";
  }
  if (activeQuestion) {
    activeQuestion.textContent = "";
  }
  if (questionCount) {
    questionCount.textContent = "0";
  }
  if (retrievalCount) {
    retrievalCount.textContent = "0";
  }
  if (groundingValue) {
    groundingValue.textContent = "вЂ”";
  }
  if (topicLabel) {
    topicLabel.textContent = "unavailable";
  }
  if (answerSource) {
    answerSource.textContent = "backend_unavailable";
  }
  if (answerText) {
    answerText.textContent = "";
  }
  if (factCheck) {
    factCheck.textContent = "";
  }
  if (lawyerPhraseCheck) {
    lawyerPhraseCheck.hidden = true;
    lawyerPhraseCheck.innerHTML = "";
  }
  if (appendedCount) {
    appendedCount.textContent = "0 new turns";
  }
  if (appendedTurns) {
    appendedTurns.innerHTML = "";
  }
  if (questionList) {
    questionList.innerHTML = "";
  }
  if (stageList) {
    stageList.innerHTML = "";
  }
  if (retrievalBranchList) {
    retrievalBranchList.innerHTML = "";
  }
  if (userChunkLabel) {
    userChunkLabel.textContent = "вЂ”";
  }
  if (userActiveQuestion) {
    userActiveQuestion.textContent = "";
  }
  if (userAnswerText) {
    userAnswerText.textContent = "";
  }
  if (conversationList) {
    conversationList.innerHTML = "";
  }
  if (userArticleList) {
    userArticleList.innerHTML = "";
  }
}

function renderQuestionList(target, questions) {
  target.innerHTML = "";
  questions.forEach((question, index) => {
    const card = document.createElement("div");
    card.className = "question-card";
    card.innerHTML = `
      <div class="question-top">
        <span class="question-index">Р’РѕРїСЂРѕСЃ ${index + 1}</span>
        <span class="question-status ${question.status}">${question.status}</span>
      </div>
      <p class="question-text">${question.text}</p>
      <p class="question-note">${question.note}</p>
    `;
    target.appendChild(card);
  });
}

function parseArticleNumberParts(value) {
  return String(value)
    .split(".")
    .map((part) => Number.parseInt(part, 10) || 0);
}

function compareArticleNumbers(left, right) {
  const leftParts = parseArticleNumberParts(left.number);
  const rightParts = parseArticleNumberParts(right.number);
  const maxLength = Math.max(leftParts.length, rightParts.length);

  for (let index = 0; index < maxLength; index += 1) {
    const leftValue = leftParts[index] ?? 0;
    const rightValue = rightParts[index] ?? 0;
    if (leftValue !== rightValue) {
      return leftValue - rightValue;
    }
  }

  return String(left.title).localeCompare(String(right.title), "ru");
}

function prepareUserArticles(articles, sortMode) {
  const uniqueArticles = [];
  const seen = new Set();

  articles.forEach((article) => {
    const key = `${article.number}|${article.title}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    uniqueArticles.push(article);
  });

  if (sortMode === "number") {
    uniqueArticles.sort(compareArticleNumbers);
    return uniqueArticles;
  }

  uniqueArticles.sort((left, right) => {
    const rightScore = Number.parseFloat(right.score) || 0;
    const leftScore = Number.parseFloat(left.score) || 0;
    if (rightScore !== leftScore) {
      return rightScore - leftScore;
    }
    return compareArticleNumbers(left, right);
  });

  return uniqueArticles;
}

function renderArticleCards(target, articles) {
  target.innerHTML = "";
  if (!articles.length) {
    const card = document.createElement("div");
    card.className = "article-card compact article-empty";
    card.innerHTML = `
      <p class="article-title">РЎС‚Р°С‚СЊРё РїРѕСЏРІСЏС‚СЃСЏ РїРѕСЃР»Рµ СЃРѕРґРµСЂР¶Р°С‚РµР»СЊРЅРѕРіРѕ РІРѕРїСЂРѕСЃР°</p>
      <p class="article-summary">РЎРµР№С‡Р°СЃ СЃРёСЃС‚РµРјР° С‚РѕР»СЊРєРѕ РЅР°РєР°РїР»РёРІР°РµС‚ РєРѕРЅС‚РµРєСЃС‚ Рё РЅРµ Р·Р°РїСѓСЃРєР°РµС‚ РїСЂР°РІРѕРІРѕР№ РїРѕРёСЃРє.</p>
    `;
    target.appendChild(card);
    return;
  }
  articles.forEach((article) => {
    const card = document.createElement("div");
    card.className = "article-card compact clickable";
    card.innerHTML = `
      <div class="article-top">
          <p class="article-title">art. ${article.number} - ${article.title}</p>
        <div class="article-meta">
          <span class="score-chip">score ${article.score}</span>
        </div>
      </div>
      <p class="article-summary">${article.summary}</p>
    `;
    card.addEventListener("click", () => openArticleModal(article));
    target.appendChild(card);
  });
}

function renderLawyerPhraseCheck(target, check, detailed = false) {
  if (!target) {
    return;
  }

  if (!check) {
    target.hidden = true;
    target.innerHTML = "";
    target.className = "fact-box lawyer-check-box";
    return;
  }

  target.hidden = false;
  target.className = `fact-box lawyer-check-box ${check.status || "no_statement"}`;

  const summary = check.summary || "РџСЂРѕРІРµСЂРєР° С„СЂР°Р· СЋСЂРёСЃС‚Р° РїРѕРєР° РЅРµ СЃС„РѕСЂРјРёСЂРѕРІР°РЅР°.";
  const reviewed = (check.reviewedPhrases || [])
    .map((phrase) => `<li>${phrase}</li>`)
    .join("");
  const flagged = (check.flaggedPhrases || [])
    .map((phrase) => `<li>${phrase}</li>`)
    .join("");

  target.innerHTML = `
    <div class="lawyer-check-top">
      <span class="lawyer-check-title">РџСЂРѕРІРµСЂРєР° С„СЂР°Р· СЋСЂРёСЃС‚Р°</span>
      <span class="lawyer-check-badge ${check.status || "no_statement"}">${check.status || "no_statement"}</span>
    </div>
    <p class="lawyer-check-summary">${summary}</p>
    <p class="lawyer-check-meta">Grounded: ${check.grounded}. Confidence: ${(Number(check.confidence) || 0).toFixed(2)}</p>
    ${
      detailed && reviewed
        ? `<div class="lawyer-check-group"><p class="lawyer-check-group-title">РџСЂРѕРІРµСЂРµРЅРЅС‹Рµ С„СЂР°Р·С‹</p><ul class="lawyer-check-list">${reviewed}</ul></div>`
        : ""
    }
    ${
      detailed && flagged
        ? `<div class="lawyer-check-group flagged"><p class="lawyer-check-group-title">РўСЂРµР±СѓСЋС‚ СЂСѓС‡РЅРѕР№ РїСЂРѕРІРµСЂРєРё</p><ul class="lawyer-check-list">${flagged}</ul></div>`
        : ""
    }
  `;
}

function renderUserQaHistory(index) {
  const processedSteps = collectProcessedStepsUntil(index);
  const questionItems = processedSteps.filter(
    (step) => step.activeQuestion && String(step.activeQuestion).trim() && step.route !== "idle",
  );
  const answerItems = processedSteps.filter(
    (step) =>
      step.retrievalBranches &&
      step.retrievalBranches.length > 0 &&
      step.answerText &&
      String(step.answerText).trim(),
  );

  if (userActiveQuestion) {
    if (!questionItems.length) {
      userActiveQuestion.innerHTML = `
        <div class="result-empty-state">Система пока не выделила содержательный вопрос клиента.</div>
      `;
    } else {
      userActiveQuestion.innerHTML = questionItems
        .map(
          (step) => `
            <div class="result-history-card">
              <div class="result-history-top">
                <span class="meta-chip">${escapeHtml(step.id)}</span>
              </div>
              <p class="result-history-text">${escapeHtml(step.activeQuestion)}</p>
            </div>
          `,
        )
        .join("");
    }
  }

  if (userAnswerText) {
    if (!answerItems.length) {
      userAnswerText.innerHTML = `
        <div class="result-empty-state">Ответы будут добавляться сюда после поиска статей по каждому чанку.</div>
      `;
    } else {
      userAnswerText.innerHTML = answerItems
        .map(
          (step) => `
            <div class="result-history-card">
              <div class="result-history-top">
                <span class="meta-chip">${escapeHtml(step.id)}</span>
                <span class="meta-chip">${escapeHtml(step.answerSource || "unknown")}</span>
              </div>
              <p class="result-history-text">${escapeHtml(step.answerText)}</p>
            </div>
          `,
        )
        .join("");
    }
  }
}

function openArticleModal(article) {
  logUi("article_open", { number: article.number, title: article.title });
  const fullText = ARTICLE_TEXTS[article.number] || article.summary || "РўРµРєСЃС‚ СЃС‚Р°С‚СЊРё РґР»СЏ СЌС‚РѕР№ РґРµРјРѕРЅСЃС‚СЂР°С†РёРё РЅРµ РґРѕР±Р°РІР»РµРЅ.";
  articleModalTitle.textContent = `РЎС‚Р°С‚СЊСЏ ${article.number}`;
  articleModalMeta.innerHTML = `
    <span class="meta-chip">СЃС‚. ${article.number}</span>
    <span class="meta-chip">${article.title}</span>
    <span class="meta-chip">score ${article.score}</span>
  `;
  articleModalBody.textContent = fullText;
  articleModal.classList.add("open");
  articleModal.setAttribute("aria-hidden", "false");
}

function closeArticleModal() {
  logUi("article_close");
  articleModal.classList.remove("open");
  articleModal.setAttribute("aria-hidden", "true");
}

function renderStep(index) {
  if (!currentSteps.length) {
    logUi("render_step_skipped", { reason: "no_steps", index });
    return;
  }

  if (index < 0 || index >= currentSteps.length) {
    logUi("render_step_skipped", {
      reason: "index_out_of_range",
      index,
      stepCount: currentSteps.length,
    });
    return;
  }

  currentIndex = index;
  const step = currentSteps[index];
  logUi("render_step", {
    index,
    stepId: step?.id,
    route: step?.route,
    questionCount: step?.extractedQuestions?.length ?? 0,
    retrievalCount: step?.retrievalBranches?.length ?? 0,
  });
  const conversationHistory = collectConversationUntil(index);
  const previousConversationHistory = collectConversationUntil(index - 1);
  const appendedHistory = collectTurnGroupsUntil(index);

  [...timeline.children].forEach((node, idx) => {
    node.classList.toggle("active", idx === index);
  });

  chunkName.textContent = step.id;
  incomingChunk.textContent = step.incomingChunk;
  activeQuestion.textContent = step.activeQuestion;
  questionCount.textContent = String(step.extractedQuestions.length);
  retrievalCount.textContent = String(step.retrievalBranches.length);
  groundingValue.textContent = step.grounding;
  topicLabel.textContent = step.topics;
  answerSource.textContent = step.answerSource;
  answerText.textContent = step.answerText;
  factCheck.textContent = step.factCheck;
  renderLawyerPhraseCheck(lawyerPhraseCheck, step.lawyerPhraseCheck, true);
  appendedCount.textContent = `${step.appendedTurns.length} new turns`;

  appendedTurns.innerHTML = "";
  appendedHistory.forEach((group) => {
    const wrapper = document.createElement("div");
    wrapper.className = "history-group";
    wrapper.innerHTML = `<div class="history-label">${group.id}</div>`;

    group.turns.forEach((turn) => {
      const card = document.createElement("div");
      card.className = "turn-card";
      card.innerHTML = `
        <span class="turn-role">${turn.role}</span>
        <p class="turn-text">${turn.text}</p>
      `;
      wrapper.appendChild(card);
    });

    appendedTurns.appendChild(wrapper);
  });

  renderQuestionList(questionList, step.extractedQuestions);

  stageList.innerHTML = "";
  step.stages.forEach((stage) => {
    const card = document.createElement("div");
    card.className = "stage-card";
    card.innerHTML = `
      <div>
        <div class="stage-name">${stage.name}</div>
        <div class="stage-pill ${stage.status === "done" ? "done" : "ready"}">${stage.status}</div>
      </div>
      <p class="stage-text">${stage.text}</p>
    `;
    stageList.appendChild(card);
  });

  retrievalBranchList.innerHTML = "";
  step.retrievalBranches.forEach((branch) => {
    const card = document.createElement("div");
    card.className = "branch-card";
    const reasons = branch.reasons.map((reason) => `<span class="reason-chip">${reason}</span>`).join("");
    const articleCards = branch.articles.map((article) => `
      <div class="article-card compact">
        <div class="article-top">
          <p class="article-title">art. ${article.number} - ${article.title}</p>
          <div class="article-meta">
            <span class="score-chip">score ${article.score}</span>
          </div>
        </div>
        <p class="article-summary">${article.summary}</p>
      </div>
    `).join("");
    card.innerHTML = `
      <div class="branch-top">
        <p class="branch-title">${branch.label}</p>
        <span class="meta-chip">retrieval_request</span>
      </div>
      <div class="query-box">${branch.query}</div>
      <div class="reasons">${reasons}</div>
      <div class="branch-articles">${articleCards}</div>
    `;
    retrievalBranchList.appendChild(card);
  });

  userChunkLabel.textContent = step.id;
  renderUserQaHistory(index);

  conversationList.innerHTML = "";
  appendConversationSection(
    conversationList,
    "Processing now",
    step.processingTurns && step.processingTurns.length ? step.processingTurns : conversationHistory,
    step.lawyerPhraseCheck,
  );
  appendConversationSection(
    conversationList,
    "Already in context",
    previousConversationHistory,
    step.lawyerPhraseCheck,
  );

  renderArticleCards(
    userArticleList,
    prepareUserArticles(
      collectProcessedStepsUntil(index).flatMap((processedStep) =>
        (processedStep.retrievalBranches || []).flatMap((branch) => branch.articles || []),
      ),
      currentArticleSort,
    ),
  );
}

function appendConversationSection(target, title, messages, lawyerCheck) {
  if (!messages || !messages.length) {
    return;
  }

  const section = document.createElement("div");
  section.className = "conversation-section";
  section.innerHTML = `<div class="conversation-section-label">${escapeHtml(title)}</div>`;

  messages.forEach((message) => {
    const lawyerFlag = findLawyerFlagForMessage(message, lawyerCheck);
    const bubble = document.createElement("div");
    bubble.className = `message-bubble ${message.role}${lawyerFlag ? " needs-review" : ""}`;
    const label =
      message.label ||
      (message.role === "client"
        ? "Client"
        : message.role === "assistant"
          ? "Lawyer"
          : "Transcript");
    bubble.innerHTML = `
      <span class="message-role">${escapeHtml(label)}</span>
      <p class="message-text">${escapeHtml(message.text)}</p>
      ${
        lawyerFlag
          ? `<div class="message-warning">
              <span class="message-warning-label">Review</span>
              <p class="message-warning-text">${escapeHtml(lawyerFlag.comment)}</p>
            </div>`
          : ""
      }
    `;
    section.appendChild(bubble);
  });

  target.appendChild(section);
}

function stopAutoplay() {
  logUi("autoplay_stop", { currentIndex });
  if (autoplayTimer) {
    clearInterval(autoplayTimer);
    autoplayTimer = null;
  }
  playBtn.textContent = scenarioLoading ? "Идет подготовка сценария..." : "Проиграть шаги";
}

function startAutoplay() {
  if (!currentSteps.length) {
    logUi("autoplay_start_skipped", { reason: "no_steps" });
    return;
  }
  logUi("autoplay_start", { stepCount: currentSteps.length });
  stopAutoplay();
  renderStep(0);
  playBtn.textContent = "Идет обработка...";
  autoplayTimer = setInterval(() => {
    if (currentIndex >= currentSteps.length - 1) {
      stopAutoplay();
      return;
    }
    renderStep(currentIndex + 1);
  }, 2600);
}

function setMode(mode) {
  logUi("mode_switch", { mode });
  const isUser = mode === "user";
  userModeBtn.classList.toggle("active", isUser);
  debugModeBtn.classList.toggle("active", !isUser);
  userWorkspace.classList.toggle("active", isUser);
  debugWorkspace.classList.toggle("active", !isUser);
}

function applyScenario(scenarioKey, scenario) {
  logUi("scenario_apply", {
    scenarioKey,
    session: scenario.session,
    stepCount: scenario.steps?.length ?? 0,
  });
  stopAutoplay();
  hideBackendNotice();
  scenarioLoading = false;
  if (playBtn) {
    playBtn.disabled = false;
    playBtn.textContent = "Проиграть шаги";
  }
  if (resetBtn) {
    resetBtn.disabled = false;
  }
  currentScenarioKey = scenarioKey;
  currentSteps = scenario.steps;
  currentIndex = 0;

  if (!currentSteps.length) {
    logUi("scenario_apply_empty", { scenarioKey });
    if (playBtn) {
      playBtn.disabled = true;
    }
    if (resetBtn) {
      resetBtn.disabled = true;
    }
    return;
  }

  if (transcriptSelect) {
    transcriptSelect.value = scenarioKey;
  }
  if (sessionLabel) {
    sessionLabel.textContent = `session: ${scenario.session}`;
  }
  createTimeline();
  renderPrePlaybackState();
}

async function loadTranscriptOptions() {
  logUi("transcript_options_load_start");
  let items = [];
  try {
    const payload = await fetchJson("/api/transcripts");
    items = payload.items || [];
    logUi("transcript_options_load_success", { count: items.length });
    hideBackendNotice();
  } catch (error) {
    logUi("transcript_options_load_error", { error: String(error) });
    showBackendNotice("Backend unavailable: transcript list could not be loaded.");
    return;
  }

  if (!transcriptSelect) {
    return;
  }

  transcriptSelect.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = item.label || item.name;
    transcriptSelect.appendChild(option);
  });

  if (!items.find((item) => item.name === currentScenarioKey) && items.length > 0) {
    currentScenarioKey = items[0].name;
  }
}

async function switchScenario(scenarioKey) {
  scenarioLoading = true;
  stopAutoplay();
  if (playBtn) {
    playBtn.disabled = true;
    playBtn.textContent = "Идет подготовка сценария...";
  }
  if (resetBtn) {
    resetBtn.disabled = true;
  }
  logUi("scenario_switch_start", { scenarioKey });
  try {
    const payload = await fetchJson(`/api/demo?transcript=${encodeURIComponent(scenarioKey)}`);
    logUi("scenario_switch_success", {
      scenarioKey,
      stepCount: payload.steps?.length ?? 0,
      session: payload.session,
    });
    hideBackendNotice();
    applyScenario(scenarioKey, {
      session: payload.session || `live-${scenarioKey}`,
      steps: payload.steps || [],
      label: payload.label || scenarioKey,
    });
    return;
  } catch (error) {
    scenarioLoading = false;
    logUi("scenario_switch_error", { scenarioKey, error: String(error) });
    clearDemoView();
    showBackendNotice(`Backend unavailable: failed to load live data for ${scenarioKey}.`);
  }
}

playBtn.addEventListener("click", () => {
  logUi("play_click", { autoplayActive: Boolean(autoplayTimer), scenarioLoading });
  if (scenarioLoading) {
    logUi("play_click_skipped", { reason: "scenario_loading" });
    return;
  }
  if (!currentSteps.length) {
    logUi("play_click_skipped", { reason: "no_steps" });
    return;
  }
  if (autoplayTimer) {
    stopAutoplay();
  } else {
    startAutoplay();
  }
});

resetBtn.addEventListener("click", () => {
  logUi("reset_click");
  if (scenarioLoading) {
    logUi("reset_click_skipped", { reason: "scenario_loading" });
    return;
  }
  stopAutoplay();
  if (!currentSteps.length) {
    logUi("reset_click_skipped", { reason: "no_steps" });
    return;
  }
  renderPrePlaybackState();
});

userModeBtn.addEventListener("click", () => setMode("user"));
debugModeBtn.addEventListener("click", () => setMode("debug"));
transcriptSelect.addEventListener("change", async (event) => {
  logUi("transcript_change", { scenarioKey: event.target.value });
  await switchScenario(event.target.value);
});
userArticleSort.addEventListener("change", (event) => {
  logUi("article_sort_change", { sort: event.target.value, currentIndex });
  currentArticleSort = event.target.value;
  renderStep(currentIndex);
});
articleModalClose.addEventListener("click", closeArticleModal);
articleModal.addEventListener("click", (event) => {
  if (event.target === articleModal) {
    closeArticleModal();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && articleModal.classList.contains("open")) {
    closeArticleModal();
  }
});

async function initializeApp() {
  logUi("initialize_start");
  await loadTranscriptOptions();
  await switchScenario(currentScenarioKey);
  setMode("user");
  logUi("initialize_done", { currentScenarioKey });
}

initializeApp();

