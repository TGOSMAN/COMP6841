const analysis = {
  tasks: [],
  task: null,
  meta: null,
  rows: [],
  frame: 0,
  playing: false,
  timer: null,
  cursorA: null,
  cursorB: null,
  captureCenter: 0,
  captureSpan: 0,
  sessionId: sessionStorage.getItem("signalForgeSession") || crypto.randomUUID(),
  userData: null,
  frontendMode: "basic",
  tx: { config: null, remainingFrames: 0, history: new Map() }
};
const weatherRadio = {
  intercept: null,
  speaking: false,
  playbackToken: 0,
  audioContext: null,
  noiseSource: null,
  noiseGain: null,
  initialised: false
};
sessionStorage.setItem("signalForgeSession", analysis.sessionId);

const byId = (id) => document.getElementById(id);
const waterfall = byId("analysis-waterfall");
const waterfallContext = waterfall.getContext("2d");
const spectrum = byId("spectrum-trace");
const spectrumContext = spectrum.getContext("2d");
const nativeWaterfall = document.createElement("canvas");
const nativeWaterfallContext = nativeWaterfall.getContext("2d");

async function bootChallenge() {
  const sessionHeaders = { "X-Signal-Session": analysis.sessionId };
  const [tasksResponse, modeResponse, sessionResponse] = await Promise.all([
    fetch("/api/tasks"),
    fetch("/api/mode"),
    fetch("/api/rf/session", { headers: sessionHeaders })
  ]);
  analysis.tasks = (await tasksResponse.json()).tasks;
  renderMode((await modeResponse.json()).mode);
  const session = await sessionResponse.json();
  analysis.userData = session.user_data;
  byId("terminal-user").textContent = `${session.user_data.callsign} / ${session.user_data.operator_id}`;
  terminalWrite(`Signal Forge session ${session.user_data.range_nonce}`, "system");
  terminalWrite("RF frontend online. Type `help` for local commands.", "system");
  const id = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
  analysis.task = analysis.tasks.find((task) => task.id === id);
  if (!analysis.task) {
    document.title = "Challenge not found | Signal Forge CTF";
    byId("challenge-title").textContent = "Challenge not found";
    byId("challenge-scenario").textContent = "Return to the challenge list and select an available mission.";
    return;
  }
  renderChallenge();
  await loadSignalCapture();
}

function renderChallenge() {
  const task = analysis.task;
  const solved = new Set(JSON.parse(localStorage.getItem("solvedTasks") || "[]"));
  const index = analysis.tasks.findIndex((candidate) => candidate.id === task.id);
  document.title = `${task.title} | Signal Forge CTF`;
  byId("challenge-kicker").textContent = `${task.track} / challenge ${index + 1} of ${analysis.tasks.length}`;
  byId("challenge-title").textContent = task.title;
  byId("challenge-score").innerHTML = `<strong>${solved.has(task.id) ? "Solved" : `${task.points} pts`}</strong><span>${task.difficulty}</span>`;
  byId("challenge-scenario").textContent = task.scenario;
  byId("challenge-objective").textContent = task.objective;
  byId("challenge-concepts").replaceChildren(...task.concepts.map((concept) => element("span", concept)));
  byId("challenge-steps").replaceChildren(...task.steps.map((step) => element("li", step)));
  byId("signal-scheme").textContent = task.signal_scheme || "No RF capture is required for this challenge.";
  byId("challenge-hints").innerHTML = task.hints.map((hint, hintIndex) => `
    <details><summary>Hint ${hintIndex + 1}</summary><p>${escapeHtml(hint)}</p></details>
  `).join("");
  renderArtifacts();
  renderPagination(index);
  byId("challenge-progress").textContent = `${String(index + 1).padStart(2, "0")} / ${String(analysis.tasks.length).padStart(2, "0")}`;
  const isWeatherRadio = task.id === "weather-radio-watch";
  byId("weather-radio").hidden = !isWeatherRadio;
  if (isWeatherRadio) initialiseWeatherRadio();
}

function initialiseWeatherRadio() {
  if (weatherRadio.initialised) return;
  weatherRadio.initialised = true;
  byId("weather-generate").addEventListener("click", generateWeatherIntercept);
  byId("weather-play").addEventListener("click", toggleWeatherPlayback);
  byId("weather-transcript-toggle").addEventListener("click", () => {
    const transcript = byId("weather-transcript");
    transcript.hidden = !transcript.hidden;
    byId("weather-transcript-toggle").textContent = transcript.hidden ? "Show text backup" : "Hide text backup";
  });
  byId("weather-report-form").addEventListener("submit", submitWeatherInjection);
  generateWeatherIntercept();
}

async function generateWeatherIntercept() {
  stopWeatherPlayback();
  const generateButton = byId("weather-generate");
  generateButton.disabled = true;
  byId("weather-radio-status").innerHTML = "<i></i> Acquiring";
  byId("weather-report-result").textContent = "Building a new randomized voice exchange...";
  try {
    const response = await fetch("/api/air/weather", { headers: { "X-Signal-Session": analysis.sessionId } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    weatherRadio.intercept = await response.json();
    const transcript = byId("weather-transcript");
    transcript.innerHTML = weatherRadio.intercept.lines.map((line) => `
      <li class="${line.role}"><strong>${escapeHtml(line.speaker)}</strong><span>${escapeHtml(line.text)}</span></li>
    `).join("");
    transcript.hidden = true;
    byId("weather-transcript-toggle").textContent = "Show text backup";
    byId("weather-play").disabled = false;
    byId("weather-transcript-toggle").disabled = false;
    byId("weather-injection").disabled = false;
    byId("weather-report-form").querySelector("button").disabled = false;
    byId("weather-injection").value = "";
    byId("weather-radio-status").innerHTML = "<i></i> Intercept ready";
    byId("weather-report-result").textContent = `Intercept ready: ${weatherRadio.intercept.callsign} on ${weatherRadio.intercept.channel}. Listen for the protocol fields, then write your own decoy.`;
    terminalWrite(`VOICE INTERCEPT ${weatherRadio.intercept.intercept_id} buffered on ${weatherRadio.intercept.channel}`, "system");
  } catch (error) {
    byId("weather-radio-status").innerHTML = "<i></i> Link failed";
    byId("weather-report-result").textContent = `Could not generate transmission: ${error.message}`;
  } finally {
    generateButton.disabled = false;
  }
}

function toggleWeatherPlayback() {
  if (weatherRadio.speaking) {
    stopWeatherPlayback();
    return;
  }
  if (!weatherRadio.intercept || !("speechSynthesis" in window)) {
    revealWeatherTranscript("Audio is unavailable in this browser, so the text backup has been opened.");
    return;
  }
  weatherRadio.speaking = true;
  weatherRadio.playbackToken += 1;
  const token = weatherRadio.playbackToken;
  byId("weather-play").textContent = "Stop radio call";
  byId("weather-radio-status").classList.add("transmitting");
  byId("weather-radio-status").innerHTML = "<i></i> Receiving AM voice";
  byId("weather-radio-scope").classList.add("active");
  startWeatherNoise();
  speakWeatherLine(0, token);
}

function speakWeatherLine(index, token) {
  if (!weatherRadio.speaking || token !== weatherRadio.playbackToken) return;
  if (index >= weatherRadio.intercept.lines.length) {
    stopWeatherPlayback("Intercept complete");
    return;
  }
  const line = weatherRadio.intercept.lines[index];
  const utterance = new SpeechSynthesisUtterance(line.text);
  const voices = speechSynthesis.getVoices().filter((voice) => /^en/i.test(voice.lang));
  const voiceIndex = line.role === "controller" ? 1 : 0;
  if (voices.length) utterance.voice = voices[voiceIndex % voices.length];
  utterance.rate = line.role === "controller" ? 1.08 : 1.14;
  utterance.pitch = line.role === "controller" ? 0.82 : 0.72;
  utterance.volume = 0.9;
  utterance.onend = () => setTimeout(() => speakWeatherLine(index + 1, token), 260 + Math.random() * 300);
  utterance.onerror = (event) => {
    stopWeatherPlayback("Audio unavailable");
    revealWeatherTranscript(`The browser voice engine could not play this call (${event.error || "audio error"}). Use the text backup below to recover the protocol fields.`);
  };
  speechSynthesis.speak(utterance);
}

function startWeatherNoise() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    weatherRadio.audioContext ||= new AudioContextClass();
    weatherRadio.audioContext.resume();
    const buffer = weatherRadio.audioContext.createBuffer(1, weatherRadio.audioContext.sampleRate * 2, weatherRadio.audioContext.sampleRate);
    const samples = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) samples[index] = (Math.random() * 2 - 1) * (0.45 + Math.random() * 0.55);
    const source = weatherRadio.audioContext.createBufferSource();
    const filter = weatherRadio.audioContext.createBiquadFilter();
    const gain = weatherRadio.audioContext.createGain();
    source.buffer = buffer;
    source.loop = true;
    filter.type = "bandpass";
    filter.frequency.value = 1700;
    filter.Q.value = 0.45;
    gain.gain.value = Number(byId("weather-noise").value) / 100 * 0.075;
    source.connect(filter).connect(gain).connect(weatherRadio.audioContext.destination);
    source.start();
    weatherRadio.noiseSource = source;
    weatherRadio.noiseGain = gain;
  } catch {
    // Voice playback remains usable if Web Audio is unavailable.
  }
}

function stopWeatherPlayback(status = "Intercept stopped") {
  weatherRadio.speaking = false;
  weatherRadio.playbackToken += 1;
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  try { weatherRadio.noiseSource?.stop(); } catch { /* already stopped */ }
  weatherRadio.noiseSource = null;
  weatherRadio.noiseGain = null;
  byId("weather-play").textContent = "2. Listen to authentic call";
  byId("weather-radio-scope").classList.remove("active");
  byId("weather-radio-status").classList.remove("transmitting");
  if (weatherRadio.intercept) byId("weather-radio-status").innerHTML = `<i></i> ${escapeHtml(status)}`;
}

async function submitWeatherInjection(event) {
  event.preventDefault();
  if (!weatherRadio.intercept) return;
  const result = byId("weather-report-result");
  const injectionMessage = byId("weather-injection").value.trim();
  if (!injectionMessage) {
    result.textContent = "Write a decoy transmission before attempting the injection.";
    result.classList.remove("success");
    byId("weather-injection").focus();
    return;
  }
  result.textContent = "Injecting message into the simulated voice net...";
  const response = await fetch("/api/air/inject", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Signal-Session": analysis.sessionId },
    body: JSON.stringify({
      session_id: analysis.sessionId,
      intercept_id: weatherRadio.intercept.intercept_id,
      message: injectionMessage
    })
  });
  const data = await response.json();
  result.textContent = data.message;
  result.classList.toggle("success", Boolean(data.ok));
  if (data.flag) {
    byId("challenge-flag").value = data.flag;
    terminalWrite(`VOICE PROTOCOL INJECTION ACCEPTED / FLAG ${data.flag}`, "system");
    speakInjectedMessage(data.broadcast || injectionMessage);
  }
}

function speakInjectedMessage(message) {
  if (!("speechSynthesis" in window)) {
    byId("weather-report-result").textContent += " Browser voice playback is unavailable, but the injection was accepted.";
    return;
  }
  stopWeatherPlayback();
  weatherRadio.speaking = true;
  weatherRadio.playbackToken += 1;
  const token = weatherRadio.playbackToken;
  const utterance = new SpeechSynthesisUtterance(message);
  const voices = speechSynthesis.getVoices().filter((voice) => /^en/i.test(voice.lang));
  if (voices.length) utterance.voice = voices[Math.min(1, voices.length - 1)];
  utterance.rate = 1.08;
  utterance.pitch = 0.78;
  byId("weather-radio-status").classList.add("transmitting");
  byId("weather-radio-status").innerHTML = "<i></i> Broadcasting your injection";
  byId("weather-radio-scope").classList.add("active");
  startWeatherNoise();
  utterance.onend = () => {
    if (token === weatherRadio.playbackToken) stopWeatherPlayback("Injection broadcast complete");
  };
  utterance.onerror = (event) => {
    stopWeatherPlayback("Injection accepted / audio unavailable");
    byId("weather-report-result").textContent += ` Browser voice playback was blocked (${event.error || "audio error"}).`;
  };
  speechSynthesis.speak(utterance);
}

function revealWeatherTranscript(message) {
  const transcript = byId("weather-transcript");
  transcript.hidden = false;
  byId("weather-transcript-toggle").textContent = "Hide text backup";
  byId("weather-report-result").textContent = message;
}

function renderArtifacts() {
  const list = byId("challenge-artifacts");
  list.innerHTML = "";
  analysis.task.artifacts.forEach((artifact) => {
    const item = document.createElement("button");
    item.type = "button";
    item.innerHTML = `<span><strong>${escapeHtml(artifact.label)}</strong><small>${escapeHtml(artifact.type || "artifact")}</small></span><i>Inspect &rarr;</i>`;
    item.addEventListener("click", () => inspectArtifact(artifact));
    list.appendChild(item);
  });
}

function renderPagination(index) {
  const previous = analysis.tasks[index - 1];
  const next = analysis.tasks[index + 1];
  setPageLink(byId("previous-challenge"), previous, "Previous");
  setPageLink(byId("next-challenge"), next, "Next");
}

function setPageLink(link, task, direction) {
  if (!task) {
    link.hidden = true;
    return;
  }
  link.href = `/challenge/${encodeURIComponent(task.id)}`;
  link.textContent = direction === "Previous" ? `← ${task.title}` : `${task.title} →`;
}

async function loadSignalCapture() {
  const artifact = analysis.task.artifacts.find((candidate) => candidate.role === "signal");
  if (!artifact) {
    byId("capture-status").textContent = "No signal capture";
    renderEmptyPlots();
    return;
  }
  try {
    const response = await fetch(artifact.href);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    analysis.meta = await response.json();
    analysis.rows = rowsForArtifact(analysis.meta) || [];
    analysis.frame = Math.max(0, analysis.rows.length - 1);
    analysis.captureCenter = Number(analysis.meta.center_hz || 0);
    analysis.captureSpan = Number(analysis.meta.span_hz || 0);
    byId("signal-title").textContent = artifact.label;
    byId("capture-status").textContent = `${analysis.rows.length} frames / ${analysis.rows[0]?.length || 0} FFT bins`;
    resetAnalysisView();
    renderCaptureMetadata();
    renderLegend();
    if (!analysis.playing) togglePlayback();
    if (analysis.task.id === "weather-radio-watch") await runRfCommand("tune");
  } catch (error) {
    byId("capture-status").textContent = "Capture failed to load";
    byId("measurement-bar").textContent = error.message;
    renderEmptyPlots();
  }
}

function resetAnalysisView() {
  const isVoiceInjection = analysis.task?.id === "weather-radio-watch";
  const lockWindowHz = Math.max(8000, Math.min(40000, analysis.captureSpan / 16));
  const presetOffsetHz = lockWindowHz + 4000;
  const initialCenter = isVoiceInjection ? analysis.captureCenter : analysis.captureCenter - presetOffsetHz;
  byId("analysis-center").value = (initialCenter / 1e6).toFixed(6);
  byId("analysis-span").value = Math.round(analysis.captureSpan / 1e3);
  if (isVoiceInjection) byId("receiver-modulation").value = "AM";
  byId("analysis-floor").value = "-88";
  byId("analysis-range").value = "70";
  byId("analysis-frame").max = Math.max(0, analysis.rows.length - 1);
  byId("analysis-frame").value = analysis.frame;
  analysis.cursorA = null;
  analysis.cursorB = null;
  renderAnalysis();
  if (isVoiceInjection) {
    byId("receiver-lock").textContent = "Preset on target / press Tune to verify";
  } else {
    byId("receiver-lock").textContent = `Near target / adjust +${Math.round(presetOffsetHz / 1000)} kHz toward ${formatHz(analysis.captureCenter)}`;
  }
}

function renderCaptureMetadata() {
  const meta = analysis.meta;
  const entries = [
    ["Scheme", meta.scheme_id || "--"],
    ["Capture centre", formatHz(meta.center_hz)],
    ["Capture span", formatHz(meta.span_hz)],
    ["Resolution", formatHz(Number(meta.span_hz) / Math.max(1, Number(meta.bins || analysis.rows[0]?.length))) + " / bin"],
    ["Modulation", meta.protocol_notes?.modulation || "See artifact notes"]
  ];
  byId("capture-metadata").innerHTML = entries.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("");
}

function renderLegend() {
  const sources = analysis.meta?.sources || [];
  byId("analysis-legend").innerHTML = sources.map((source, index) => {
    const color = analysis.meta.annotations?.[index]?.color || "#59d7e8";
    return `<span><i style="background:${color}"></i>${escapeHtml(source.label)}</span>`;
  }).join("");
}

function currentViewport() {
  const rowLength = analysis.rows[0]?.length || Number(analysis.meta?.bins || 96);
  const captureStart = analysis.captureCenter - analysis.captureSpan / 2;
  let requestedSpan = Math.max(1000, Number(byId("analysis-span").value || analysis.captureSpan / 1e3) * 1e3);
  requestedSpan = Math.min(analysis.captureSpan, requestedSpan);
  let requestedCenter = Number(byId("analysis-center").value || analysis.captureCenter / 1e6) * 1e6;
  requestedCenter = Math.max(captureStart + requestedSpan / 2, Math.min(captureStart + analysis.captureSpan - requestedSpan / 2, requestedCenter));
  const startHz = requestedCenter - requestedSpan / 2;
  const endHz = requestedCenter + requestedSpan / 2;
  const startBin = Math.max(0, Math.floor(((startHz - captureStart) / analysis.captureSpan) * rowLength));
  const endBin = Math.min(rowLength, Math.ceil(((endHz - captureStart) / analysis.captureSpan) * rowLength));
  return { rowLength, captureStart, center: requestedCenter, span: requestedSpan, startHz, endHz, startBin, endBin, binCount: Math.max(1, endBin - startBin) };
}

function renderAnalysis() {
  if (!analysis.rows.length) return renderEmptyPlots();
  const viewport = currentViewport();
  const visibleFrames = Math.min(analysis.rows.length, 120);
  const firstFrame = (analysis.frame - visibleFrames + 1 + analysis.rows.length) % analysis.rows.length;
  nativeWaterfall.width = viewport.binCount;
  nativeWaterfall.height = visibleFrames;
  const image = nativeWaterfallContext.createImageData(viewport.binCount, visibleFrames);
  for (let y = 0; y < visibleFrames; y += 1) {
    const frame = (firstFrame + y) % analysis.rows.length;
    const row = analysis.rows[frame];
    for (let x = 0; x < viewport.binCount; x += 1) {
      const bin = viewport.startBin + x;
      const [red, green, blue] = analysisRgb(row[bin]);
      const pixel = (y * viewport.binCount + x) * 4;
      image.data[pixel] = red;
      image.data[pixel + 1] = green;
      image.data[pixel + 2] = blue;
      image.data[pixel + 3] = 255;
    }
  }
  nativeWaterfallContext.putImageData(image, 0, 0);
  waterfallContext.fillStyle = "#020405";
  waterfallContext.fillRect(0, 0, waterfall.width, waterfall.height);
  waterfallContext.imageSmoothingEnabled = false;
  waterfallContext.drawImage(nativeWaterfall, 0, 0, waterfall.width, waterfall.height);
  drawGrid(waterfallContext, waterfall.width, waterfall.height, 10, 6);
  drawAnnotations(viewport);
  drawOwnTransmissions(viewport, firstFrame, visibleFrames);
  drawSelectedFrame(firstFrame, visibleFrames);
  drawMeasurementCursor(analysis.cursorA, "A", "#73f2a6", viewport);
  drawMeasurementCursor(analysis.cursorB, "B", "#ffc766", viewport);
  drawSpectrum(viewport);
  updateReadouts(viewport);
}

function drawGrid(context, width, height, columns, rows) {
  context.save();
  context.strokeStyle = "rgba(255,255,255,.1)";
  context.lineWidth = 1;
  for (let column = 0; column <= columns; column += 1) {
    const x = Math.round(column / columns * width) + 0.5;
    context.beginPath(); context.moveTo(x, 0); context.lineTo(x, height); context.stroke();
  }
  for (let row = 0; row <= rows; row += 1) {
    const y = Math.round(row / rows * height) + 0.5;
    context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke();
  }
  context.restore();
}

function drawAnnotations(viewport) {
  waterfallContext.save();
  waterfallContext.font = "12px system-ui";
  (analysis.meta.annotations || []).forEach((annotation) => {
    const frequency = analysis.captureCenter + Number(annotation.offset_hz || 0);
    const x = (frequency - viewport.startHz) / viewport.span * waterfall.width;
    if (x < 0 || x > waterfall.width) return;
    waterfallContext.strokeStyle = annotation.color || "#59d7e8";
    waterfallContext.fillStyle = annotation.color || "#59d7e8";
    waterfallContext.setLineDash([5, 5]);
    waterfallContext.beginPath(); waterfallContext.moveTo(x, 0); waterfallContext.lineTo(x, waterfall.height); waterfallContext.stroke();
    waterfallContext.setLineDash([]);
    waterfallContext.fillText(annotation.label, Math.min(waterfall.width - 150, x + 7), 18 + Number(annotation.row || 0) * 17);
  });
  waterfallContext.restore();
}

function drawSelectedFrame(firstFrame, visibleFrames) {
  const y = waterfall.height - 2;
  waterfallContext.save();
  waterfallContext.strokeStyle = "rgba(255,255,255,.8)";
  waterfallContext.setLineDash([3, 5]);
  waterfallContext.beginPath(); waterfallContext.moveTo(0, y); waterfallContext.lineTo(waterfall.width, y); waterfallContext.stroke();
  waterfallContext.restore();
}

function drawOwnTransmissions(viewport, firstFrame, visibleFrames) {
  const rowHeight = waterfall.height / visibleFrames;
  waterfallContext.save();
  for (let visibleRow = 0; visibleRow < visibleFrames; visibleRow += 1) {
    const frame = (firstFrame + visibleRow) % analysis.rows.length;
    const tx = analysis.tx.history.get(frame);
    if (!tx) continue;
    const transmitterCenter = Number(byId("analysis-center").value) * 1e6 + tx.offset_khz * 1e3;
    const bandwidthHz = Math.max(1000, tx.bandwidth_khz * 1e3);
    let waveformOffset = 0;
    if (tx.waveform === "2-FSK") waveformOffset = (frame % 2 ? 1 : -1) * bandwidthHz * 0.24;
    if (tx.waveform === "4-FSK") waveformOffset = [-0.36, -0.12, 0.12, 0.36][frame % 4] * bandwidthHz;
    if (tx.waveform === "GFSK") waveformOffset = Math.sin(frame * 0.7) * bandwidthHz * 0.18;
    if (tx.waveform === "AFSK") waveformOffset = (frame % 3 - 1) * bandwidthHz * 0.2;
    const frequency = transmitterCenter + waveformOffset;
    const x = (frequency - viewport.startHz) / viewport.span * waterfall.width;
    const width = tx.waveform === "noise"
      ? bandwidthHz / viewport.span * waterfall.width
      : Math.max(2, Math.min(18, bandwidthHz / viewport.span * waterfall.width * 0.28));
    if (x + width < 0 || x - width > waterfall.width) continue;
    const alpha = Math.max(0.32, Math.min(0.95, 1 - Math.abs(tx.power_db) / 70));
    waterfallContext.fillStyle = `rgba(255, 74, 210, ${alpha})`;
    waterfallContext.fillRect(x - width / 2, visibleRow * rowHeight, width, Math.max(2, rowHeight + 1));
    if (tx.waveform !== "noise") {
      waterfallContext.fillStyle = "rgba(255,255,255,.72)";
      waterfallContext.fillRect(x - 0.5, visibleRow * rowHeight, 1, Math.max(2, rowHeight + 1));
    }
  }
  if (analysis.tx.remainingFrames > 0 && analysis.tx.config) {
    waterfallContext.fillStyle = "#ff4ad2";
    waterfallContext.font = "700 12px ui-monospace, Consolas, monospace";
    waterfallContext.fillText(`LOCAL TX / ${analysis.tx.config.waveform}`, 10, waterfall.height - 10);
  }
  waterfallContext.restore();
}

function drawMeasurementCursor(cursor, label, color, viewport) {
  if (!cursor) return;
  const frequency = viewport.startHz + cursor.x / waterfall.width * viewport.span;
  const bin = Math.max(viewport.startBin, Math.min(viewport.endBin - 1, Math.round(viewport.startBin + cursor.x / waterfall.width * viewport.binCount)));
  const power = analysis.rows[analysis.frame]?.[bin] || 0;
  const callout = `${label}  ${formatAxisHz(frequency)}  ${powerToDb(power).toFixed(1)} dBFS`;
  waterfallContext.save();
  waterfallContext.strokeStyle = color;
  waterfallContext.lineWidth = 2;
  waterfallContext.beginPath(); waterfallContext.moveTo(cursor.x, 0); waterfallContext.lineTo(cursor.x, waterfall.height); waterfallContext.stroke();
  waterfallContext.font = "700 12px ui-monospace, Consolas, monospace";
  const calloutWidth = waterfallContext.measureText(callout).width + 18;
  const calloutX = Math.max(5, Math.min(waterfall.width - calloutWidth - 5, cursor.x + 7));
  const calloutY = label === "A" ? 8 : 38;
  waterfallContext.fillStyle = color;
  waterfallContext.fillRect(calloutX, calloutY, calloutWidth, 24);
  waterfallContext.fillStyle = "#07100b";
  waterfallContext.fillText(callout, calloutX + 9, calloutY + 16);
  waterfallContext.restore();
}

function drawSpectrum(viewport) {
  const row = analysis.rows[analysis.frame] || analysis.rows[0];
  spectrumContext.fillStyle = "#020607";
  spectrumContext.fillRect(0, 0, spectrum.width, spectrum.height);
  drawGrid(spectrumContext, spectrum.width, spectrum.height, 10, 4);
  const points = [];
  let peak = { power: -Infinity, bin: viewport.startBin };
  for (let x = 0; x < spectrum.width; x += 1) {
    const bin = Math.min(viewport.endBin - 1, viewport.startBin + Math.floor((x / spectrum.width) * viewport.binCount));
    const power = row[bin] || 0;
    const db = powerToDb(power);
    const floor = Number(byId("analysis-floor").value);
    const range = Number(byId("analysis-range").value);
    const y = spectrum.height - Math.max(0, Math.min(1, (db - floor) / range)) * spectrum.height;
    points.push([x, y]);
    if (power > peak.power) peak = { power, bin };
  }
  spectrumContext.beginPath();
  points.forEach(([x, y], index) => { if (index === 0) spectrumContext.moveTo(x, y); else spectrumContext.lineTo(x, y); });
  spectrumContext.lineTo(spectrum.width, spectrum.height);
  spectrumContext.lineTo(0, spectrum.height);
  spectrumContext.closePath();
  const fill = spectrumContext.createLinearGradient(0, 0, 0, spectrum.height);
  fill.addColorStop(0, "rgba(89, 215, 232, .34)");
  fill.addColorStop(1, "rgba(89, 215, 232, .08)");
  spectrumContext.fillStyle = fill;
  spectrumContext.fill();
  spectrumContext.beginPath();
  points.forEach(([x, y], index) => { if (index === 0) spectrumContext.moveTo(x, y); else spectrumContext.lineTo(x, y); });
  spectrumContext.strokeStyle = "#59d7e8";
  spectrumContext.lineWidth = 1.5;
  spectrumContext.stroke();
  const peakFrequency = viewport.captureStart + (peak.bin / Math.max(1, viewport.rowLength - 1)) * analysis.captureSpan;
  byId("peak-readout").textContent = `Peak: ${formatHz(peakFrequency)} / ${powerToDb(peak.power).toFixed(1)} dBFS`;
}

function updateReadouts(viewport) {
  const tickCount = 7;
  byId("analysis-axis").innerHTML = Array.from({ length: tickCount }, (_, index) => {
    const frequency = viewport.startHz + index / (tickCount - 1) * viewport.span;
    return `<span class="frequency-tick"><i></i><b>${formatAxisHz(frequency)}</b></span>`;
  }).join("");
  byId("frame-readout").textContent = `${analysis.frame + 1} / ${analysis.rows.length}`;
  byId("resolution-readout").textContent = `RBW: ${formatHz(viewport.span / Math.max(1, viewport.binCount))}`;
  byId("dynamic-range-readout").textContent = `DR: ${Number(byId("analysis-range").value)} dB`;
  byId("noise-floor-readout").textContent = `Floor: ${Number(byId("analysis-floor").value)} dBFS`;
  if (!analysis.cursorA) {
    byId("measurement-bar").textContent = "Click once for cursor A and again for cursor B.";
    return;
  }
  const cursorFrequency = (cursor) => viewport.startHz + cursor.x / waterfall.width * viewport.span;
  const aText = `A ${formatHz(cursorFrequency(analysis.cursorA))}`;
  if (!analysis.cursorB) {
    byId("measurement-bar").textContent = `${aText} — click again to place cursor B.`;
    return;
  }
  const bText = `B ${formatHz(cursorFrequency(analysis.cursorB))}`;
  const delta = Math.abs(cursorFrequency(analysis.cursorB) - cursorFrequency(analysis.cursorA));
  byId("measurement-bar").textContent = `${aText} / ${bText} / Δf ${formatHz(delta)}`;
}

function renderEmptyPlots() {
  for (const [context, canvas] of [[waterfallContext, waterfall], [spectrumContext, spectrum]]) {
    context.fillStyle = "#030708";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#a8b4ae";
    context.font = "16px system-ui";
    context.fillText("No signal data available for this challenge.", 28, 48);
  }
}

function analysisColor(power) {
  return `rgb(${analysisRgb(power).join(",")})`;
}

function analysisRgb(power) {
  const floor = Number(byId("analysis-floor").value);
  const range = Number(byId("analysis-range").value);
  const normalized = Math.max(0, Math.min(1, (powerToDb(power) - floor) / range));
  const palette = byId("analysis-palette").value;
  if (palette === "mono") {
    const value = Math.round(normalized * 255);
    return [value, value, value];
  }
  if (palette === "turbo") {
    const stops = [[0, 7, 38], [0, 62, 142], [0, 205, 224], [245, 239, 45], [255, 94, 24], [206, 15, 20]];
    const scaled = normalized * (stops.length - 1);
    const low = Math.floor(scaled);
    const high = Math.min(stops.length - 1, low + 1);
    const amount = scaled - low;
    return stops[low].map((value, index) => Math.round(value + (stops[high][index] - value) * amount));
  }
  const stops = [[8, 7, 24], [72, 19, 105], [187, 55, 84], [249, 142, 8], [252, 255, 164]];
  const scaled = normalized * (stops.length - 1);
  const low = Math.floor(scaled);
  const high = Math.min(stops.length - 1, low + 1);
  const amount = scaled - low;
  const rgb = stops[low].map((value, index) => Math.round(value + (stops[high][index] - value) * amount));
  return rgb;
}

function hslToRgb(hue, saturation, lightness) {
  const channel = (offset) => {
    const position = (offset + hue * 12) % 12;
    const amount = saturation * Math.min(lightness, 1 - lightness);
    return Math.round((lightness - amount * Math.max(-1, Math.min(position - 3, 9 - position, 1))) * 255);
  };
  return [channel(0), channel(8), channel(4)];
}

function powerToDb(power) {
  return -110 + Math.max(0, Math.min(1, Number(power || 0))) * 110;
}

function rowsForArtifact(artifact) {
  if (artifact?.rows) return artifact.rows;
  if (!artifact?.sources) return [];
  const bins = Number(artifact.bins || 96);
  const frames = Number(artifact.frames || 120);
  const span = Number(artifact.span_hz || 2000000);
  const rows = [];
  for (let frame = 0; frame < frames; frame += 1) {
    const row = [];
    for (let bin = 0; bin < bins; bin += 1) {
      const offset = -span / 2 + bin / Math.max(1, bins - 1) * span;
      let power = 0.04 + deterministicNoise(bin, frame, Number(artifact.seed || 6841)) * 0.09;
      artifact.sources.forEach((source) => { power = Math.max(power, sourcePower(source, offset, frame)); });
      row.push(Math.min(1, power));
    }
    rows.push(row);
  }
  return rows;
}

function sourcePower(source, offsetHz, frame) {
  const baseOffset = Number(source.offset_hz || 0);
  const bandwidth = Number(source.bandwidth_hz || 16000);
  const period = Number(source.period_frames || 40);
  const duration = Number(source.duration_frames || 10);
  const hopSet = source.hop_offsets_hz;
  const hop = hopSet ? Number(hopSet[Math.floor(frame / Math.max(1, period)) % hopSet.length]) : baseOffset;
  const driftedOffset = hop + Number(source.drift_hz_per_frame || 0) * frame;
  const active = source.kind === "noise_band" || (frame + Number(source.phase_frames || 0)) % period < duration;
  if (source.kind === "sweep") {
    const start = Number(source.sweep_start_hz || -800000);
    const stop = Number(source.sweep_stop_hz || 800000);
    const sweepPeriod = Number(source.sweep_period_frames || 90);
    const sweepOffset = start + (frame % sweepPeriod) / sweepPeriod * (stop - start);
    return Math.abs(offsetHz - sweepOffset) < bandwidth ? Number(source.power || 0.65) : 0;
  }
  if (!active) return 0;
  if (source.kind === "noise_band") {
    return Math.abs(offsetHz - driftedOffset) < bandwidth / 2 ? Number(source.power || 0.32) * (0.75 + deterministicNoise(Math.round(offsetHz), frame, 17) * 0.25) : 0;
  }
  const distance = Math.abs(offsetHz - driftedOffset) / Math.max(1, bandwidth / 2);
  if (distance >= 1) return 0;
  const envelope = Math.pow(1 - distance, 0.32);
  const spectralTexture = 0.64 + deterministicNoise(Math.round(offsetHz / Math.max(1, bandwidth) * 900), frame, 31) * 0.26;
  const voiceRipple = 0.78 + Math.pow(Math.sin(offsetHz / Math.max(1, bandwidth) * 38 + frame * 0.37), 2) * 0.22;
  const carrier = distance < 0.045 ? 0.16 : 0;
  return Math.min(1, Number(source.power || 0.9) * envelope * spectralTexture * voiceRipple + carrier);
}

function deterministicNoise(x, y, seed) {
  const value = Math.sin(x * 12.9898 + y * 78.233 + seed * 37.719) * 43758.5453;
  return value - Math.floor(value);
}

async function inspectArtifact(artifact) {
  const inspector = byId("artifact-inspector");
  const visual = byId("artifact-visual");
  byId("artifact-title").textContent = artifact.label;
  byId("artifact-content").textContent = "Loading artifact...";
  visual.innerHTML = `<div class="artifact-loading">Building visual preview...</div>`;
  inspector.hidden = false;
  inspector.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const response = await fetch(artifact.href, { headers: { "X-Signal-Session": analysis.sessionId } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    const contentType = response.headers.get("content-type") || artifact.type || "";
    if (contentType.startsWith("image/")) {
      const url = URL.createObjectURL(new Blob([bytes], { type: contentType }));
      visual.innerHTML = `<img class="artifact-image" src="${url}" alt="${escapeHtml(artifact.label)} preview">`;
      byId("artifact-content").textContent = `${bytes.length} byte ${contentType} artifact`;
      return;
    }
    const text = new TextDecoder().decode(bytes);
    let parsed = null;
    try { parsed = JSON.parse(text); } catch { parsed = null; }
    if (parsed?.rows || parsed?.sources) renderSignalArtifactPreview(visual, parsed);
    else if (parsed) renderStructuredArtifactPreview(visual, parsed);
    else if (contentType.includes("octet-stream")) renderBinaryArtifactPreview(visual, bytes);
    else renderTextArtifactPreview(visual, text, artifact.type);
    byId("artifact-content").textContent = parsed ? JSON.stringify(parsed, null, 2) : contentType.includes("octet-stream") ? hexDump(bytes) : text;
  } catch (error) {
    byId("artifact-content").textContent = `Unable to preview this artifact: ${error.message}\n\nOpen directly: ${artifact.href}`;
  }
}

function renderSignalArtifactPreview(container, meta) {
  const rows = rowsForArtifact(meta);
  const bins = rows[0]?.length || 1;
  container.innerHTML = `<div class="artifact-preview-heading"><strong>Signal capture preview</strong><span>${rows.length} frames × ${bins} bins</span></div><canvas class="artifact-signal-preview" width="1000" height="300"></canvas>`;
  const preview = container.querySelector("canvas");
  const context = preview.getContext("2d");
  const native = document.createElement("canvas");
  native.width = bins;
  native.height = rows.length;
  const nativeContext = native.getContext("2d");
  const pixels = nativeContext.createImageData(bins, rows.length);
  rows.forEach((row, y) => row.forEach((power, x) => {
    const [red, green, blue] = analysisRgb(power);
    const pixel = (y * bins + x) * 4;
    pixels.data.set([red, green, blue, 255], pixel);
  }));
  nativeContext.putImageData(pixels, 0, 0);
  context.imageSmoothingEnabled = false;
  context.drawImage(native, 0, 0, preview.width, preview.height);
  drawGrid(context, preview.width, preview.height, 10, 5);
}

function renderStructuredArtifactPreview(container, value) {
  const rows = flattenArtifact(value).slice(0, 100);
  container.innerHTML = `<div class="artifact-preview-heading"><strong>Structured data</strong><span>${rows.length} visible fields</span></div><div class="artifact-data-grid">${rows.map(([path, fieldValue]) => `<div><span>${escapeHtml(path)}</span><strong>${escapeHtml(String(fieldValue))}</strong></div>`).join("")}</div>`;
}

function flattenArtifact(value, prefix = "") {
  if (value === null || typeof value !== "object") return [[prefix || "value", value]];
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return child !== null && typeof child === "object" ? flattenArtifact(child, path) : [[path, child]];
  });
}

function renderTextArtifactPreview(container, text, type = "") {
  const lines = text.split(/\r?\n/);
  container.innerHTML = `<div class="artifact-preview-heading"><strong>${type.includes("markdown") ? "Document preview" : "Source / text preview"}</strong><span>${lines.length} lines</span></div><div class="artifact-code-preview">${lines.slice(0, 120).map((line, index) => `<div><i>${index + 1}</i><code>${escapeHtml(line)}</code></div>`).join("")}</div>`;
}

function renderBinaryArtifactPreview(container, bytes) {
  const visible = bytes.slice(0, 512);
  container.innerHTML = `<div class="artifact-preview-heading"><strong>Binary / IQ artifact</strong><span>${bytes.length} bytes</span></div><div class="binary-map">${Array.from(visible, (byte) => `<i style="--level:${byte / 255}" title="0x${byte.toString(16).padStart(2, "0")}"></i>`).join("")}</div>`;
}

function hexDump(bytes) {
  return Array.from(bytes.slice(0, 4096)).reduce((output, byte, index) => {
    const prefix = index % 16 === 0 ? `${index.toString(16).padStart(8, "0")}  ` : "";
    const suffix = index % 16 === 15 ? "\n" : " ";
    return output + prefix + byte.toString(16).padStart(2, "0") + suffix;
  }, "");
}

function receiverConfig() {
  return {
    center_mhz: Number(byId("analysis-center").value),
    span_khz: Number(byId("analysis-span").value),
    gain_db: Number(byId("receiver-gain").value),
    squelch_db: Number(byId("receiver-squelch").value),
    modulation: byId("receiver-modulation").value,
    sample_rate_msps: Number(byId("receiver-sample-rate").value),
    bandwidth_khz: Number(byId("receiver-bandwidth").value),
    agc: byId("receiver-agc").value,
    fft_bins: 1024
  };
}

function transmitterConfig() {
  return {
    waveform: byId("tx-waveform").value,
    offset_khz: Number(byId("tx-offset").value),
    bandwidth_khz: Number(byId("tx-bandwidth").value),
    power_db: Number(byId("tx-power").value),
    duration_ms: Number(byId("tx-duration").value)
  };
}

function activateTransmission(preview = false) {
  const config = transmitterConfig();
  const frameRate = Number(byId("analysis-rate").value || 30);
  analysis.tx.config = config;
  analysis.tx.remainingFrames = preview ? Math.max(8, Math.round(frameRate * 0.55)) : Math.max(3, Math.round(config.duration_ms / 1000 * frameRate));
  byId("tx-status").textContent = preview ? "Previewing" : `Transmitting ${config.waveform}`;
  terminalWrite(`${preview ? "TX PREVIEW" : "TX ACTIVE"} ${config.waveform} offset=${config.offset_khz}kHz bw=${config.bandwidth_khz}kHz power=${config.power_db}dB`, "system");
  if (!analysis.playing) togglePlayback();
  return config;
}

function showTerminalHelp(topic = "") {
  const help = {
    "": [
      "SIGNAL FORGE RF FRONTEND HELP",
      "Topics: help rx | help tx | help request | help effects | help mission",
      "Quick commands: scan, tune, receive, status, decode, request, interfere, forward, send, transmit, clear",
      "Use Basic controls for acquisition. Advanced exposes DSP and raw TX parameters."
    ],
    rx: [
      "RX / RECEIVER",
      "scan                 search the current centre/span",
      "tune <MHz>           set receiver centre and evaluate lock",
      "span <kHz>           set visible and receiver span",
      "gain <dB>            set RF gain (0–60)",
      "squelch <dB>         set the receiver gate",
      "demod <mode>         AUTO, 2-FSK, 4-FSK, ASK, MANCHESTER, CSS, GFSK, AFSK, or AM",
      "receive              print buffered target data when locked",
      "status               show receiver state"
    ],
    tx: [
      "TX / TRANSMITTER (LOCAL SIMULATION)",
      "Use the TX Chain controls for waveform, offset, bandwidth, power, and duration.",
      "Preview waveform draws a short uncommitted trace on the live waterfall.",
      "Transmit burst injects the configured waveform and reports target effects.",
      "transmit <text>      transmit using the current TX Chain configuration",
      "Your energy is magenta; received target energy uses the selected waterfall palette."
    ],
    request: [
      "SAME-ORIGIN REQUESTS",
      "request /path        run an HTTP GET against the Python range backend",
      "Example: request /api/toll/events?vehicle_id=VH-7A29",
      "Spaces and quotes may be used in the path for local training payloads.",
      "The terminal automatically attaches your session identity."
    ],
    effects: [
      "CEMA EFFECTS",
      "interfere <effect>   apply a simulated effect after receiver lock",
      "forward <target>     route buffered receiver data to another range component",
      "send <payload>       send raw target input in Advanced mode",
      "Effects are local and synthetic; output confirms whether the target changed state."
    ],
    mission: [
      `MISSION: ${analysis.task?.title || "loading"}`,
      analysis.task?.objective || "",
      ...(analysis.task?.steps || []).map((item) => `INTEL ${item}`)
    ]
  };
  (help[topic.toLowerCase()] || [`Unknown help topic: ${topic}`, "Try help rx, help tx, help request, help effects, or help mission."]).forEach((line, index) => terminalWrite(line, index === 0 ? "system" : "output"));
}

function terminalWrite(message, kind = "output") {
  const output = byId("terminal-output");
  String(message).split("\n").forEach((line) => {
    const entry = document.createElement("span");
    entry.className = `terminal-line ${kind}`;
    entry.textContent = line;
    output.appendChild(entry);
  });
  output.scrollTop = output.scrollHeight;
}

async function runRfCommand(action, argumentsText = "") {
  terminalWrite(`$ ${action}${argumentsText ? ` ${argumentsText}` : ""}`, "command");
  try {
    const response = await fetch("/api/rf/command", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Signal-Session": analysis.sessionId },
      body: JSON.stringify({
        session_id: analysis.sessionId,
        challenge_id: analysis.task.id,
        action,
        arguments: argumentsText,
        receiver: receiverConfig()
      })
    });
    const data = await response.json();
    (data.lines || [JSON.stringify(data, null, 2)]).forEach((line) => terminalWrite(line, data.ok ? "output" : "error"));
    byId("receiver-lock").textContent = data.locked ? `LOCKED / ${data.target}` : "Receiver unlocked";
    byId("receiver-lock").classList.toggle("locked", Boolean(data.locked));
    return data;
  } catch (error) {
    terminalWrite(`Frontend error: ${error.message}`, "error");
    return null;
  }
}

async function runTerminalCommand(rawCommand) {
  const input = rawCommand.trim();
  if (!input) return;
  const firstSpace = input.indexOf(" ");
  const command = (firstSpace === -1 ? input : input.slice(0, firstSpace)).toLowerCase();
  const argumentsText = firstSpace === -1 ? "" : input.slice(firstSpace + 1).trim();

  if (command === "help") {
    showTerminalHelp(argumentsText);
    return;
  }
  if (command === "clear") {
    byId("terminal-output").replaceChildren();
    return;
  }
  if (command === "basic" || command === "advanced") {
    setFrontendMode(command);
    terminalWrite(`Frontend mode: ${command}`);
    return;
  }
  const controlMap = {
    tune: "analysis-center",
    span: "analysis-span",
    gain: "receiver-gain",
    squelch: "receiver-squelch"
  };
  if (controlMap[command]) {
    const value = Number(argumentsText);
    if (!Number.isFinite(value)) return terminalWrite(`${command}: numeric value required`, "error");
    byId(controlMap[command]).value = value;
    renderAnalysis();
    await runRfCommand(command === "tune" ? "tune" : "status");
    return;
  }
  if (command === "demod") {
    const option = [...byId("receiver-modulation").options].find((candidate) => candidate.value.toUpperCase() === argumentsText.toUpperCase());
    if (!option) return terminalWrite("demod: unsupported mode", "error");
    byId("receiver-modulation").value = option.value;
    await runRfCommand("status");
    return;
  }
  if (command === "request") {
    if (!argumentsText.startsWith("/")) return terminalWrite("request: use a same-origin /path", "error");
    terminalWrite(`$ request ${argumentsText}`, "command");
    try {
      const response = await fetch(argumentsText, { headers: { "X-Signal-Session": analysis.sessionId } });
      terminalWrite(`HTTP ${response.status}`, response.ok ? "system" : "error");
      terminalWrite(prettyJson(await response.text()), response.ok ? "output" : "error");
    } catch (error) {
      terminalWrite(`Request failed: ${error.message}`, "error");
    }
    return;
  }
  if (["scan", "status", "receive", "decode", "interfere", "forward", "send", "transmit"].includes(command)) {
    if (command === "transmit") activateTransmission(false);
    await runRfCommand(command, argumentsText);
    return;
  }
  terminalWrite(`${command}: command not found; try help`, "error");
}

function setFrontendMode(mode) {
  analysis.frontendMode = mode;
  const advanced = mode === "advanced";
  byId("receiver-advanced").hidden = !advanced;
  byId("frontend-basic").classList.toggle("active", !advanced);
  byId("frontend-advanced").classList.toggle("active", advanced);
}

function togglePlayback() {
  analysis.playing = !analysis.playing;
  byId("analysis-play").textContent = analysis.playing ? "Pause" : "Play";
  clearInterval(analysis.timer);
  if (!analysis.playing) return;
  const framesPerSecond = Number(byId("analysis-rate").value || 30);
  analysis.timer = setInterval(() => {
    analysis.frame = (analysis.frame + 1) % analysis.rows.length;
    analysis.tx.history.delete(analysis.frame);
    if (analysis.tx.remainingFrames > 0 && analysis.tx.config) {
      analysis.tx.history.set(analysis.frame, { ...analysis.tx.config });
      analysis.tx.remainingFrames -= 1;
      if (analysis.tx.remainingFrames === 0) byId("tx-status").textContent = "Standby";
    }
    byId("analysis-frame").value = analysis.frame;
    renderAnalysis();
  }, 1000 / framesPerSecond);
}

function renderMode(mode) {
  byId("attack-mode").classList.toggle("active", mode === "attack");
  byId("secure-mode").classList.toggle("active", mode === "secure");
  byId("mode-status").textContent = mode === "attack" ? "Attack Mode" : "Secure Mode";
  byId("mode-status").style.color = mode === "attack" ? "var(--amber)" : "var(--green)";
}

async function setMode(mode) {
  const response = await fetch("/api/mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
  renderMode((await response.json()).mode);
}

byId("analysis-play").addEventListener("click", togglePlayback);
byId("analysis-rate").addEventListener("change", () => { if (analysis.playing) { analysis.playing = false; togglePlayback(); } });
byId("analysis-reset").addEventListener("click", resetAnalysisView);
byId("analysis-cursors").addEventListener("click", () => { analysis.cursorA = null; analysis.cursorB = null; renderAnalysis(); });
byId("analysis-frame").addEventListener("input", (event) => { analysis.frame = Number(event.target.value); renderAnalysis(); });
["analysis-center", "analysis-span", "analysis-floor", "analysis-range", "analysis-palette"].forEach((id) => byId(id).addEventListener("input", renderAnalysis));
waterfall.addEventListener("click", (event) => {
  const bounds = waterfall.getBoundingClientRect();
  const cursor = { x: (event.clientX - bounds.left) / bounds.width * waterfall.width };
  if (!analysis.cursorA || analysis.cursorB) { analysis.cursorA = cursor; analysis.cursorB = null; }
  else analysis.cursorB = cursor;
  renderAnalysis();
});
waterfall.addEventListener("dblclick", async (event) => {
  const bounds = waterfall.getBoundingClientRect();
  const viewport = currentViewport();
  const x = (event.clientX - bounds.left) / bounds.width;
  const frequencyMhz = (viewport.startHz + x * viewport.span) / 1e6;
  byId("analysis-center").value = frequencyMhz.toFixed(6);
  renderAnalysis();
  terminalWrite(`Waterfall tune: ${frequencyMhz.toFixed(6)} MHz`, "command");
  await runRfCommand("tune");
});
byId("artifact-close").addEventListener("click", () => { byId("artifact-inspector").hidden = true; });
byId("attack-mode").addEventListener("click", () => setMode("attack"));
byId("secure-mode").addEventListener("click", () => setMode("secure"));
byId("frontend-basic").addEventListener("click", () => setFrontendMode("basic"));
byId("frontend-advanced").addEventListener("click", () => setFrontendMode("advanced"));
byId("receiver-scan").addEventListener("click", () => runRfCommand("scan"));
byId("receiver-apply").addEventListener("click", () => runRfCommand("tune"));
byId("receiver-receive").addEventListener("click", () => runRfCommand("receive"));
byId("terminal-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = byId("terminal-input");
  const command = input.value;
  input.value = "";
  await runTerminalCommand(command);
});
byId("terminal-help").addEventListener("click", () => showTerminalHelp());
byId("tx-preview").addEventListener("click", () => activateTransmission(true));
byId("tx-transmit").addEventListener("click", async () => {
  const config = activateTransmission(false);
  await runRfCommand("transmit", JSON.stringify(config));
});
byId("challenge-flag-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/api/flag", { method: "POST", headers: { "Content-Type": "application/json", "X-Signal-Session": analysis.sessionId }, body: JSON.stringify({ taskId: analysis.task.id, flag: byId("challenge-flag").value, session_id: analysis.sessionId }) });
  const data = await response.json();
  const result = byId("challenge-flag-result");
  result.textContent = data.message;
  result.style.color = data.ok ? "var(--green)" : "var(--red)";
  if (data.ok) {
    const solved = new Set(JSON.parse(localStorage.getItem("solvedTasks") || "[]"));
    solved.add(analysis.task.id);
    localStorage.setItem("solvedTasks", JSON.stringify([...solved]));
    renderChallenge();
  }
});

function element(tag, text) { const node = document.createElement(tag); node.textContent = text; return node; }
function prettyJson(text) { try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; } }
function formatHz(value) {
  const hz = Number(value || 0);
  if (Math.abs(hz) >= 1e9) return `${(hz / 1e9).toFixed(6)} GHz`;
  if (Math.abs(hz) >= 1e6) return `${(hz / 1e6).toFixed(3)} MHz`;
  if (Math.abs(hz) >= 1e3) return `${(hz / 1e3).toFixed(1)} kHz`;
  return `${Math.round(hz)} Hz`;
}
function formatAxisHz(value) {
  const hz = Number(value || 0);
  if (Math.abs(hz) >= 1e9) return `${(hz / 1e9).toFixed(6)}G`;
  if (Math.abs(hz) >= 1e6) return `${(hz / 1e6).toFixed(3)}M`;
  if (Math.abs(hz) >= 1e3) return `${(hz / 1e3).toFixed(1)}k`;
  return `${Math.round(hz)}`;
}
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[character])); }

bootChallenge();
