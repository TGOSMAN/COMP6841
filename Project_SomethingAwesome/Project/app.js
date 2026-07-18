const state = {
  contexts: [],
  tasks: [],
  selectedTask: null,
  mode: "attack",
  solved: new Set(JSON.parse(localStorage.getItem("solvedTasks") || "[]")),
  waterfallRows: null,
  waterfallArtifact: null,
  mainZoom: {
    freq: 1,
    time: 1
  },
  paused: false,
  frame: 0,
  workbench: {
    artifact: null,
    meta: null,
    rows: null,
    frame: 0,
    zoomFreq: 1,
    zoomTime: 1,
    playing: false,
    cursorA: null,
    cursorB: null,
    timer: null
  }
};
const signalForgeSession = sessionStorage.getItem("signalForgeSession") || crypto.randomUUID();
sessionStorage.setItem("signalForgeSession", signalForgeSession);
const signalSessionHeaders = { "X-Signal-Session": signalForgeSession };

const taskGrid = document.querySelector("#task-grid");
const filters = document.querySelectorAll(".filter");
const detailPanel = document.querySelector("#challenge-detail");
const researchPanel = document.querySelector("#research-panel");
const canvas = document.querySelector("#waterfall");
const ctx = canvas.getContext("2d", { willReadFrequently: true });
const pauseButton = document.querySelector("#pause-waterfall");
const dataMode = document.querySelector("#data-mode");
const attackModeButton = document.querySelector("#attack-mode");
const secureModeButton = document.querySelector("#secure-mode");
const modeStatus = document.querySelector("#mode-status");
const operatorForm = document.querySelector("#operator-form");
const operatorEvents = document.querySelector("#operator-events");
const refreshOperator = document.querySelector("#refresh-operator");
const receiveRadio = document.querySelector("#receive-radio");
const operatorDecode = document.querySelector("#operator-decode");
const zoomFreq = document.querySelector("#zoom-freq");
const zoomTime = document.querySelector("#zoom-time");
const zoomReadout = document.querySelector("#zoom-readout");
const consoleSignalLabel = document.querySelector("#console-signal-label");

async function boot() {
  ensureWorkbench();
  await Promise.all([loadMode(), loadContexts(), loadTasks(), loadResearchNotes(), loadWaterfallRows()]);
  renderTasks();
  updateZoomReadout();
  seedWaterfall();
  drawWaterfall();
  await loadOperatorEvents();
}

async function loadMode() {
  const response = await fetch("/api/mode");
  const data = await response.json();
  state.mode = data.mode;
  renderMode();
}

async function loadTasks() {
  const response = await fetch("/api/tasks");
  const data = await response.json();
  state.tasks = data.tasks;
}

async function loadContexts() {
  const response = await fetch("/api/contexts");
  const data = await response.json();
  state.contexts = data.contexts;
}

async function loadResearchNotes() {
  const response = await fetch("/api/research");
  const notes = await response.json();
  researchPanel.innerHTML = Object.entries(notes)
    .map(([group, items]) => `
      <article>
        <h3>${titleCase(group.replace("_", " "))}</h3>
        <ul>${items.map((item) => `<li>${item}</li>`).join("")}</ul>
      </article>
    `)
    .join("");
}

async function loadWaterfallRows() {
  try {
    const response = await fetch("/captures/tolling-waterfall.json");
    const data = await response.json();
    state.waterfallArtifact = data;
    state.waterfallRows = rowsForArtifact(data);
  } catch {
    state.waterfallArtifact = null;
    state.waterfallRows = null;
  }
}

function renderTasks(filter = "all") {
  taskGrid.innerHTML = "";
  state.contexts
    .filter((context) => filter === "all" || context.tracks.includes(filter))
    .forEach((context) => {
      const solvedCount = context.subtasks.filter((task) => state.solved.has(task.id)).length;
      const trackLabels = context.tracks.map((track) => track.toUpperCase()).join(" / ");
      const card = document.createElement("article");
      card.className = "task-card situation-card";
      card.innerHTML = `
        <div class="task-topline">
          <span class="tag">${escapeHtml(trackLabels)}</span>
          <span class="difficulty">${escapeHtml(context.level)} / ${context.total_points} pts</span>
        </div>
        <h3>${escapeHtml(context.title)}</h3>
        <p class="task-context">${escapeHtml(context.status)} situation</p>
        <p>${escapeHtml(context.summary)}</p>
        <div class="context-meta">
          <span>${context.subtask_count} subtasks</span>
          <span>${solvedCount}/${context.subtask_count} solved</span>
          <span>${(context.planned_subtasks || []).length} planned</span>
        </div>
        <a class="task-open" href="/context/${encodeURIComponent(context.id)}">Open situation</a>
      `;
      taskGrid.appendChild(card);
    });
}

function selectTask(taskId) {
  const task = state.tasks.find((candidate) => candidate.id === taskId);
  if (!task) return;
  state.selectedTask = task;
  renderTasks(document.querySelector(".filter.active")?.dataset.filter || "all");
  renderDetail(task);
  loadTaskSignal(task);
}

function renderDetail(task) {
  const solved = state.solved.has(task.id);
  detailPanel.innerHTML = `
    <div class="detail-head">
      <div>
        <span class="tag">${task.track.replace("-", " ")}</span>
        <h3>${task.title}</h3>
      </div>
      <strong>${solved ? "Solved" : `${task.points} pts`}</strong>
    </div>
    <p>${task.objective}</p>
    <div class="concept-list">
      ${task.concepts.map((concept) => `<span>${concept}</span>`).join("")}
    </div>
    ${task.signal_scheme ? `
      <div class="signal-scheme">
        <strong>Signal scheme</strong>
        <p>${task.signal_scheme}</p>
      </div>
    ` : ""}
    <h4>Small Steps</h4>
    <ol class="step-list">
      ${task.steps.map((step) => `<li>${step}</li>`).join("")}
    </ol>
    <h4>Artifacts</h4>
    <div class="artifact-list">
      ${task.artifacts.map((artifact) => `
        <button type="button" data-artifact='${JSON.stringify(artifact)}'>${artifact.label}</button>
      `).join("")}
    </div>
    <h4>Hints</h4>
    <div class="hint-stack">
      ${task.hints.map((hint, index) => `
        <details>
          <summary>Hint ${index + 1}</summary>
          <p>${hint}</p>
        </details>
      `).join("")}
    </div>
    <form class="flag-form">
      <input aria-label="Flag input" placeholder="CTF{YOUR_FLAG}" autocomplete="off">
      <button type="submit">Submit flag</button>
    </form>
    <p class="flag-result" aria-live="polite"></p>
  `;
  detailPanel.querySelector(".flag-form").addEventListener("submit", submitFlag);
  detailPanel.querySelectorAll("[data-artifact]").forEach((button) => {
    button.addEventListener("click", () => openArtifact(JSON.parse(button.dataset.artifact)));
  });
}

async function loadTaskSignal(task) {
  const signalArtifact = task.artifacts?.find((artifact) => artifact.role === "signal");
  if (!signalArtifact) return;
  try {
    const response = await fetch(signalArtifact.href);
    const data = await response.json();
    state.waterfallArtifact = data;
    state.waterfallRows = rowsForArtifact(data);
    state.frame = 0;
    consoleSignalLabel.textContent = task.signal_scheme || data.description || signalArtifact.label;
    seedWaterfall();
  } catch {
    consoleSignalLabel.textContent = "Signal artifact failed to load";
  }
}

async function submitFlag(event) {
  event.preventDefault();
  const input = event.currentTarget.querySelector("input");
  const result = detailPanel.querySelector(".flag-result");
  const response = await fetch("/api/flag", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ taskId: state.selectedTask.id, flag: input.value })
  });
  const data = await response.json();
  result.textContent = data.message;
  result.style.color = data.ok ? "var(--green)" : "var(--red)";
  if (data.ok) {
    state.solved.add(state.selectedTask.id);
    localStorage.setItem("solvedTasks", JSON.stringify([...state.solved]));
    renderTasks(document.querySelector(".filter.active")?.dataset.filter || "all");
  }
}

filters.forEach((button) => {
  button.addEventListener("click", () => {
    filters.forEach((candidate) => candidate.classList.remove("active"));
    button.classList.add("active");
    renderTasks(button.dataset.filter);
  });
});

attackModeButton.addEventListener("click", () => setMode("attack"));
secureModeButton.addEventListener("click", () => setMode("secure"));

async function setMode(mode) {
  const response = await fetch("/api/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode })
  });
  const data = await response.json();
  state.mode = data.mode;
  renderMode();
  await loadOperatorEvents();
}

function renderMode() {
  attackModeButton.classList.toggle("active", state.mode === "attack");
  secureModeButton.classList.toggle("active", state.mode === "secure");
  modeStatus.textContent = state.mode === "attack" ? "Attack Mode" : "Secure Mode";
  modeStatus.style.color = state.mode === "attack" ? "var(--amber)" : "var(--green)";
}

operatorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await fetch("/operator/comment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      callsign: document.querySelector("#operator-callsign").value,
      route_note: document.querySelector("#operator-route-note").value,
      operator_comment: document.querySelector("#operator-comment").value
    })
  });
  await loadOperatorEvents();
});

refreshOperator.addEventListener("click", loadOperatorEvents);
receiveRadio.addEventListener("click", receiveRadioIntercept);

zoomFreq.addEventListener("input", () => {
  state.mainZoom.freq = Number(zoomFreq.value);
  updateZoomReadout();
  seedWaterfall();
});

zoomTime.addEventListener("input", () => {
  state.mainZoom.time = Number(zoomTime.value);
  updateZoomReadout();
  seedWaterfall();
});

function updateZoomReadout() {
  zoomReadout.textContent = `${state.mainZoom.freq.toFixed(1)}x freq / ${state.mainZoom.time.toFixed(1)}x time`;
}

async function receiveRadioIntercept() {
  operatorDecode.textContent = "Receiving burst, correlating preamble...";
  const response = await fetch("/api/radio/intercept", { headers: signalSessionHeaders });
  const data = await response.json();
  document.querySelector("#operator-callsign").value = data.callsign;
  document.querySelector("#operator-route-note").value = `${data.modulation} ${data.channel_label}: ${data.vehicle_id} ${data.route_code}/${data.schedule_code}`;
  document.querySelector("#operator-comment").value = data.operator_note;
  operatorDecode.innerHTML = `
    <dl>
      <dt>frame</dt><dd>${data.frame_id}</dd>
      <dt>channel</dt><dd>${data.channel_label}</dd>
      <dt>modulation</dt><dd>${data.modulation}</dd>
      <dt>vehicle</dt><dd>${data.vehicle_id}</dd>
      <dt>route</dt><dd>${data.route_code}</dd>
      <dt>checksum</dt><dd>${data.checksum}</dd>
      <dt>sink</dt><dd>${data.sink_warning}</dd>
    </dl>
  `;
}

async function loadOperatorEvents() {
  const response = await fetch("/operator/events", { headers: signalSessionHeaders });
  const data = await response.json();
  operatorEvents.innerHTML = "";
  data.events.forEach((event) => {
    const card = document.createElement("article");
    card.className = "operator-event";
    const header = document.createElement("h3");
    header.textContent = event.callsign;
    const note = document.createElement("p");
    note.textContent = event.route_note;
    const comment = document.createElement("div");
    comment.className = "operator-comment";
    if (data.mode === "attack") {
      comment.innerHTML = event.operator_comment;
    } else {
      comment.textContent = event.operator_comment;
    }
    card.append(header, note, comment);
    operatorEvents.appendChild(card);
  });
}

pauseButton.addEventListener("click", () => {
  state.paused = !state.paused;
  pauseButton.textContent = state.paused ? "Resume" : "Pause";
  pauseButton.setAttribute("aria-pressed", String(state.paused));
});

dataMode.addEventListener("change", () => {
  state.frame = 0;
  seedWaterfall();
});

function titleCase(value) {
  return value.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    "\"": "&quot;"
  }[character]));
}

function ensureWorkbench() {
  const workbench = document.createElement("dialog");
  workbench.id = "artifact-workbench";
  workbench.innerHTML = `
    <form method="dialog">
      <button class="close-button" aria-label="Close artifact workbench">x</button>
    </form>
    <div class="workbench-head">
      <div>
        <p class="eyebrow">Artifact Analysis</p>
        <h2 id="workbench-title">Artifact</h2>
      </div>
      <div class="workbench-controls">
        <button id="workbench-play" type="button">Play</button>
        <input id="workbench-scrubber" type="range" min="0" max="0" value="0">
        <label>Freq zoom <input id="workbench-zoom-freq" type="range" min="1" max="8" step="0.5" value="1"></label>
        <label>Time zoom <input id="workbench-zoom-time" type="range" min="1" max="6" step="0.5" value="1"></label>
        <button id="workbench-reset-cursors" type="button">Reset cursors</button>
      </div>
    </div>
    <div class="workbench-grid">
      <div>
        <canvas id="workbench-waterfall" width="760" height="360"></canvas>
        <div class="axis-scale" id="workbench-axis" aria-hidden="true"></div>
        <div class="cursor-readout" id="cursor-readout">Click the waterfall to place cursor A and B.</div>
      </div>
      <div class="workbench-side">
        <h3>Decoded / Metadata</h3>
        <div id="workbench-summary"></div>
        <details>
          <summary>Raw artifact</summary>
          <pre id="workbench-raw"></pre>
        </details>
      </div>
    </div>
  `;
  document.body.appendChild(workbench);
  document.querySelector("#workbench-play").addEventListener("click", toggleWorkbenchPlayback);
  document.querySelector("#workbench-scrubber").addEventListener("input", (event) => {
    state.workbench.frame = Number(event.target.value);
    renderWorkbenchWaterfall();
  });
  document.querySelector("#workbench-zoom-freq").addEventListener("input", (event) => {
    state.workbench.zoomFreq = Number(event.target.value);
    renderWorkbenchWaterfall();
  });
  document.querySelector("#workbench-zoom-time").addEventListener("input", (event) => {
    state.workbench.zoomTime = Number(event.target.value);
    renderWorkbenchWaterfall();
  });
  document.querySelector("#workbench-reset-cursors").addEventListener("click", () => {
    state.workbench.cursorA = null;
    state.workbench.cursorB = null;
    renderWorkbenchWaterfall();
  });
  document.querySelector("#workbench-waterfall").addEventListener("click", (event) => {
    const canvasBox = event.currentTarget.getBoundingClientRect();
    const point = {
      x: ((event.clientX - canvasBox.left) / canvasBox.width) * event.currentTarget.width,
      y: ((event.clientY - canvasBox.top) / canvasBox.height) * event.currentTarget.height
    };
    if (!state.workbench.cursorA || state.workbench.cursorB) {
      state.workbench.cursorA = point;
      state.workbench.cursorB = null;
    } else {
      state.workbench.cursorB = point;
    }
    renderWorkbenchWaterfall();
  });
}

async function openArtifact(artifact) {
  state.workbench.artifact = artifact;
  state.workbench.meta = null;
  state.workbench.cursorA = null;
  state.workbench.cursorB = null;
  state.workbench.zoomFreq = 1;
  state.workbench.zoomTime = 1;
  const response = await fetch(artifact.href);
  const text = await response.text();
  let parsed = null;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = null;
  }
  document.querySelector("#workbench-title").textContent = artifact.label;
  document.querySelector("#workbench-raw").textContent = parsed ? JSON.stringify(parsed, null, 2) : text;
  document.querySelector("#workbench-summary").innerHTML = summarizeArtifact(artifact, parsed, text);
  document.querySelector("#workbench-zoom-freq").value = "1";
  document.querySelector("#workbench-zoom-time").value = "1";
  if (parsed?.rows || parsed?.sources) {
    state.workbench.meta = parsed;
    state.workbench.rows = rowsForArtifact(parsed);
  } else if (state.waterfallRows) {
    state.workbench.meta = state.waterfallArtifact;
    state.workbench.rows = state.waterfallRows;
  } else {
    state.workbench.rows = null;
  }
  const scrubber = document.querySelector("#workbench-scrubber");
  scrubber.max = state.workbench.rows ? Math.max(0, state.workbench.rows.length - 1) : 0;
  scrubber.value = 0;
  state.workbench.frame = 0;
  renderWorkbenchWaterfall();
  document.querySelector("#artifact-workbench").showModal();
}

function summarizeArtifact(artifact, parsed, text) {
  if (parsed?.recovered_payload) {
    return `
      <dl>
        ${Object.entries(parsed.recovered_payload).map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("")}
      </dl>
      <p>${(parsed.security_notes || []).join(" ")}</p>
    `;
  }
  if (parsed?.global) {
    return `
      <dl>
        <dt>datatype</dt><dd>${parsed.global["core:datatype"]}</dd>
        <dt>sample rate</dt><dd>${parsed.global["core:sample_rate"]}</dd>
        <dt>description</dt><dd>${parsed.global["core:description"]}</dd>
      </dl>
    `;
  }
  if (parsed?.rows || parsed?.sources) {
    const rows = rowsForArtifact(parsed);
    const sources = parsed.sources || [];
    return `
      <p>${parsed.description || "Waterfall frame artifact."}</p>
      <dl>
        <dt>centre</dt><dd>${formatHz(parsed.center_hz || 0)}</dd>
        <dt>span</dt><dd>${formatHz(parsed.span_hz || 0)}</dd>
        <dt>rows</dt><dd>${rows.length}</dd>
        <dt>sources</dt><dd>${sources.map((source) => source.label).join(", ") || "precomputed rows"}</dd>
      </dl>
    `;
  }
  return `<p>${artifact.type || "artifact"} / ${text.length} bytes</p>`;
}

function toggleWorkbenchPlayback() {
  const button = document.querySelector("#workbench-play");
  state.workbench.playing = !state.workbench.playing;
  button.textContent = state.workbench.playing ? "Pause" : "Play";
  if (state.workbench.playing) {
    state.workbench.timer = setInterval(() => {
      const rows = state.workbench.rows || [];
      if (!rows.length) return;
      state.workbench.frame = (state.workbench.frame + 1) % rows.length;
      document.querySelector("#workbench-scrubber").value = state.workbench.frame;
      renderWorkbenchWaterfall();
    }, 180);
  } else {
    clearInterval(state.workbench.timer);
  }
}

function renderWorkbenchWaterfall() {
  const wbCanvas = document.querySelector("#workbench-waterfall");
  const wbCtx = wbCanvas.getContext("2d");
  const viewport = waterfallViewport(wbCanvas.width, wbCanvas.height, state.workbench.zoomFreq, state.workbench.zoomTime);
  wbCtx.fillStyle = "#020707";
  wbCtx.fillRect(0, 0, wbCanvas.width, wbCanvas.height);
  const rows = state.workbench.rows;
  if (rows?.length) {
    for (let y = 0; y < wbCanvas.height; y += 1) {
      const rowIndex = Math.floor(state.workbench.frame + y / state.workbench.zoomTime);
      if (rowIndex >= rows.length) continue;
      const row = rows[rowIndex];
      for (let x = 0; x < wbCanvas.width; x += 1) {
        const index = Math.floor(viewport.startBin + (x / wbCanvas.width) * viewport.binCount);
        wbCtx.fillStyle = colorForPower(row[index]);
        wbCtx.fillRect(x, y, 1, 1);
      }
    }
  } else {
    wbCtx.fillStyle = "rgba(115, 242, 166, 0.18)";
    wbCtx.fillRect(0, wbCanvas.height / 2 - 18, wbCanvas.width, 36);
  }
  drawWorkbenchAxes(viewport);
  drawAnnotations(wbCtx, state.workbench.meta, viewport, wbCanvas.width, wbCanvas.height);
  drawCursor("cursorA", "#73f2a6");
  drawCursor("cursorB", "#ffc766");
  updateCursorReadout();
}

function waterfallViewport(width, height, freqZoom = 1, timeZoom = 1) {
  const rowLength = state.workbench.rows?.[0]?.length || state.waterfallRows?.[0]?.length || 96;
  const binCount = Math.max(8, Math.floor(rowLength / freqZoom));
  const startBin = Math.max(0, Math.floor((rowLength - binCount) / 2));
  return { rowLength, binCount, startBin, endBin: startBin + binCount, freqZoom, timeZoom, width, height };
}

function drawWorkbenchAxes(viewport) {
  const meta = state.workbench.meta || state.waterfallArtifact || {};
  const center = Number(meta.center_hz || 2437000000);
  const span = Number(meta.span_hz || 2000000);
  const startHz = center - span / 2 + (viewport.startBin / viewport.rowLength) * span;
  const endHz = center - span / 2 + (viewport.endBin / viewport.rowLength) * span;
  document.querySelector("#workbench-axis").innerHTML = `
    <span>${formatHz(startHz)}</span>
    <span>${formatHz((startHz + endHz) / 2)}</span>
    <span>${formatHz(endHz)}</span>
  `;
}

function drawAnnotations(renderCtx, meta, viewport, width, height) {
  if (!meta?.annotations?.length) return;
  const center = Number(meta.center_hz || 2437000000);
  const span = Number(meta.span_hz || 2000000);
  const visibleStartHz = center - span / 2 + (viewport.startBin / viewport.rowLength) * span;
  const visibleSpanHz = (viewport.binCount / viewport.rowLength) * span;
  renderCtx.save();
  renderCtx.font = "12px system-ui";
  renderCtx.lineWidth = 1;
  meta.annotations.forEach((annotation) => {
    const offset = Number(annotation.offset_hz || 0);
    const x = ((center + offset - visibleStartHz) / visibleSpanHz) * width;
    if (x < 0 || x > width) return;
    renderCtx.strokeStyle = annotation.color || "#ffc766";
    renderCtx.fillStyle = annotation.color || "#ffc766";
    renderCtx.beginPath();
    renderCtx.moveTo(x, 0);
    renderCtx.lineTo(x, height);
    renderCtx.stroke();
    renderCtx.fillText(annotation.label || "marker", Math.min(width - 120, x + 6), 18 + (annotation.row || 0) * 16);
  });
  renderCtx.restore();
}

function drawCursor(name, color) {
  const cursor = state.workbench[name];
  if (!cursor) return;
  const wbCanvas = document.querySelector("#workbench-waterfall");
  const wbCtx = wbCanvas.getContext("2d");
  wbCtx.strokeStyle = color;
  wbCtx.lineWidth = 2;
  wbCtx.beginPath();
  wbCtx.moveTo(cursor.x, 0);
  wbCtx.lineTo(cursor.x, wbCanvas.height);
  wbCtx.moveTo(0, cursor.y);
  wbCtx.lineTo(wbCanvas.width, cursor.y);
  wbCtx.stroke();
}

function updateCursorReadout() {
  const readout = document.querySelector("#cursor-readout");
  const a = state.workbench.cursorA;
  const b = state.workbench.cursorB;
  if (!a || !b) {
    readout.textContent = "Click the waterfall to place cursor A and B.";
    return;
  }
  const meta = state.workbench.meta || state.waterfallArtifact || {};
  const spanHz = Number(meta.span_hz || 2000000) / state.workbench.zoomFreq;
  const deltaHz = Math.abs(a.x - b.x) / document.querySelector("#workbench-waterfall").width * spanHz;
  const deltaFrames = Math.abs(Math.round((a.y - b.y) / state.workbench.zoomTime));
  readout.textContent = `Delta frequency: ${Math.round(deltaHz)} Hz / Delta time: ${deltaFrames} frames`;
}

function rowsForArtifact(artifact) {
  if (artifact?.rows) return artifact.rows;
  if (!artifact?.sources) return null;
  const bins = artifact.bins || 96;
  const frames = Math.max(artifact.frames || 120, 720);
  const center = Number(artifact.center_hz || 2437000000);
  const span = Number(artifact.span_hz || 2000000);
  const rows = [];
  for (let frame = 0; frame < frames; frame += 1) {
    const row = [];
    for (let bin = 0; bin < bins; bin += 1) {
      const offsetHz = -span / 2 + (bin / Math.max(1, bins - 1)) * span;
      let power = backgroundPower(bin, frame, artifact.seed || 6841);
      for (const source of artifact.sources) {
        power = Math.max(power, sourcePower(source, offsetHz, frame, center, span));
      }
      row.push(Number(Math.min(1, power).toFixed(3)));
    }
    rows.push(row);
  }
  return rows;
}

function sourcePower(source, offsetHz, frame) {
  const offset = Number(source.offset_hz || 0);
  const bandwidth = Number(source.bandwidth_hz || 16000);
  const period = Number(source.period_frames || 40);
  const duration = Number(source.duration_frames || 10);
  const phase = Number(source.phase_frames || 0);
  const phasedFrame = frame + phase;
  const cycleIndex = Math.floor(phasedFrame / Math.max(1, period));
  const cyclePosition = positiveModulo(phasedFrame, Math.max(1, period));
  const drift = Number(source.drift_hz_per_frame || 0) * frame;
  const hopSet = source.hop_offsets_hz || null;
  const hop = hopSet ? Number(hopSet[positiveModulo(cycleIndex, hopSet.length)]) : offset;
  const jitter = Number(source.jitter_hz || Math.min(3500, bandwidth * 0.04)) *
    (smoothNoise(cycleIndex * 1.7, frame / 27, hashString(source.label || "source")) - 0.5);
  const active = source.kind === "noise_band" || cyclePosition < duration;
  const distance = Math.abs(offsetHz - hop - drift - jitter);
  if (!active && source.kind !== "sweep") return 0;
  if (source.kind === "sweep") {
    const sweepStart = Number(source.sweep_start_hz || -800000);
    const sweepStop = Number(source.sweep_stop_hz || 800000);
    const sweepPeriod = Number(source.sweep_period_frames || 90);
    const sweepPosition = positiveModulo(frame, sweepPeriod) / sweepPeriod;
    const sweepOffset = sweepStart + sweepPosition * (sweepStop - sweepStart);
    const sweepSigma = Math.max(1, bandwidth / 2.8);
    return Number(source.power || 0.65) * gaussian(offsetHz - sweepOffset, sweepSigma);
  }
  if (source.kind === "noise_band") {
    const edge = gaussian(Math.max(0, distance - bandwidth / 2), Math.max(1, bandwidth / 9));
    const noiseSeed = hashString(source.label || "noise");
    const texture =
      0.62 +
      deterministicNoise(Math.round(offsetHz / 900), frame, noiseSeed) * 0.25 +
      deterministicNoise(Math.round(offsetHz / 3100), Math.floor(frame / 2), noiseSeed + 41) * 0.13;
    return Number(source.power || 0.32) * edge * texture;
  }
  const temporal = raisedCosineEnvelope(cyclePosition, duration);
  const spectral = gaussian(distance, Math.max(1, bandwidth / 3.2));
  return Number(source.power || 0.9) * temporal * spectral;
}

function backgroundPower(bin, frame, seed) {
  const coarse = deterministicNoise(Math.floor(bin / 9), Math.floor(frame / 7), seed);
  const medium = deterministicNoise(Math.floor(bin / 3), Math.floor(frame / 2), seed + 19);
  const fine = deterministicNoise(bin, frame, seed + 43);
  return 0.032 + coarse * 0.026 + medium * 0.022 + fine * 0.018;
}

function raisedCosineEnvelope(position, duration) {
  if (duration <= 1) return 1;
  if (position < 0 || position >= duration) return 0;
  const edge = Math.max(1.5, duration * 0.22);
  if (position < edge) {
    return 0.5 - 0.5 * Math.cos(Math.PI * position / edge);
  }
  if (position > duration - edge) {
    return 0.5 - 0.5 * Math.cos(Math.PI * (duration - position) / edge);
  }
  return 1;
}

function gaussian(distance, sigma) {
  return Math.exp(-0.5 * Math.pow(distance / sigma, 2));
}

function positiveModulo(value, divisor) {
  return ((value % divisor) + divisor) % divisor;
}

function smoothNoise(x, y, seed) {
  const a = Math.sin(x * 1.71 + y * 2.13 + seed * 0.017);
  const b = Math.sin(x * 3.11 - y * 1.37 + seed * 0.031);
  const c = Math.sin(x * 0.73 + y * 4.19 + seed * 0.047);
  return (a + b * 0.55 + c * 0.3 + 1.85) / 3.7;
}

function hashString(value) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function deterministicNoise(x, y, seed) {
  const value = Math.sin((x * 12.9898 + y * 78.233 + seed * 37.719)) * 43758.5453;
  return value - Math.floor(value);
}

function formatHz(value) {
  const hz = Number(value);
  if (Math.abs(hz) >= 1000000000) return `${(hz / 1000000000).toFixed(6)} GHz`;
  if (Math.abs(hz) >= 1000000) return `${(hz / 1000000).toFixed(3)} MHz`;
  if (Math.abs(hz) >= 1000) return `${(hz / 1000).toFixed(1)} kHz`;
  return `${Math.round(hz)} Hz`;
}

function colorForPower(power) {
  const p = Math.max(0, Math.min(1, power));
  const r = Math.floor(18 + p * 237);
  const g = Math.floor(44 + Math.sin(p * Math.PI) * 190);
  const b = Math.floor(45 + (1 - p) * 130);
  return `rgb(${r}, ${g}, ${b})`;
}

function artifactPower(x, width, tick) {
  if (dataMode.value !== "artifact" || !state.waterfallRows) return null;
  const row = state.waterfallRows[Math.floor(tick / state.mainZoom.time) % state.waterfallRows.length];
  const rowLength = row.length;
  const binCount = Math.max(8, Math.floor(rowLength / state.mainZoom.freq));
  const startBin = Math.max(0, Math.floor((rowLength - binCount) / 2));
  const index = Math.floor(startBin + (x / width) * binCount);
  return row[Math.min(row.length - 1, index)];
}

function simulatedPower(x, width, tick) {
  const centre = width / 2;
  const beacon = Math.abs(x - (centre - width * 0.23)) < 4 && tick % 54 < 12 ? 0.94 : 0;
  const replay = Math.abs(x - (centre + width * 0.18)) < 4 && tick % 70 > 42 ? 0.84 : 0;
  const sweepX = (tick * 4) % width;
  const sweep = Math.abs(x - sweepX) < 3 ? 0.7 : 0;
  const jammer = x > width * 0.65 && x < width * 0.82 && tick % 180 > 84 ? 0.28 : 0;
  const noise = Math.random() * 0.16;
  return Math.max(noise + jammer, beacon, replay, sweep);
}

function signalPower(x, width, tick) {
  const artifact = artifactPower(x, width, tick);
  if (artifact !== null) return artifact;
  return simulatedPower(x, width, tick);
}

function seedWaterfall() {
  for (let y = 0; y < canvas.height; y += 1) {
    const tick = canvas.height - y;
    for (let x = 0; x < canvas.width; x += 1) {
      ctx.fillStyle = colorForPower(signalPower(x, canvas.width, tick));
      ctx.fillRect(x, y, 1, 1);
    }
  }
  state.frame = canvas.height;
}

function drawWaterfall() {
  if (!state.paused) {
    const rowsPerFrame = 2;
    ctx.drawImage(canvas, 0, 0, canvas.width, canvas.height - rowsPerFrame, 0, rowsPerFrame, canvas.width, canvas.height - rowsPerFrame);
    for (let row = 0; row < rowsPerFrame; row += 1) {
      for (let x = 0; x < canvas.width; x += 1) {
        ctx.fillStyle = colorForPower(signalPower(x, canvas.width, state.frame + row));
        ctx.fillRect(x, row, 1, 1);
      }
    }
    state.frame += rowsPerFrame;
  }
  requestAnimationFrame(drawWaterfall);
}

boot();
