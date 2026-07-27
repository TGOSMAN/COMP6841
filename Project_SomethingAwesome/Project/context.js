const contextState = {
  contexts: [],
  context: null,
  solved: new Set(JSON.parse(localStorage.getItem("solvedTasks") || "[]"))
};

const contextById = (id) => document.getElementById(id);

async function bootContext() {
  const [contextsResponse] = await Promise.all([
    fetch("/api/contexts")
  ]);
  contextState.contexts = (await contextsResponse.json()).contexts;

  const id = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
  contextState.context = contextState.contexts.find((candidate) => candidate.id === id);
  if (!contextState.context) {
    document.title = "Situation not found | Signal Forge CTF";
    contextById("context-title").textContent = "Situation not found";
    contextById("context-summary").textContent = "Return to the situation list and choose an available context.";
    return;
  }
  renderContext();
}

function renderContext() {
  const context = contextState.context;
  const index = contextState.contexts.findIndex((candidate) => candidate.id === context.id);
  const solvedCount = context.subtasks.filter((task) => contextState.solved.has(task.id)).length;
  const tracks = context.tracks.map((track) => track.toUpperCase()).join(" / ");

  document.title = `${context.title} | Signal Forge CTF`;
  contextById("context-kicker").textContent = `${context.level} / ${tracks}`;
  contextById("context-title").textContent = context.title;
  contextById("context-summary").textContent = context.summary;
  contextById("context-situation").textContent = context.situation;
  contextById("context-progress").textContent = `${String(index + 1).padStart(2, "0")} / ${String(contextState.contexts.length).padStart(2, "0")}`;
  contextById("context-score").innerHTML = `<strong>${solvedCount}/${context.subtask_count}</strong><span>${context.total_points} pts</span>`;

  contextById("subtask-grid").replaceChildren(...context.subtasks.map(renderSubtaskCard));
  const planned = context.planned_subtasks?.length ? context.planned_subtasks : ["No planned subtasks yet."];
  contextById("planned-list").replaceChildren(...planned.map((item) => {
    const node = document.createElement("li");
    node.textContent = item;
    return node;
  }));
}

function renderSubtaskCard(task) {
  const solved = contextState.solved.has(task.id);
  const card = document.createElement("article");
  card.className = "subtask-card";
  card.innerHTML = `
    <div class="task-topline">
      <span class="tag">${escapeHtml(task.source_task_id || task.track.replace("-", " "))}</span>
      <span class="difficulty">${escapeHtml(task.difficulty)} / ${task.points} pts</span>
    </div>
    <h3>${escapeHtml(task.title)}</h3>
    <p>${escapeHtml(task.objective)}</p>
    ${task.flag_location ? `<p class="task-context">Flag: ${escapeHtml(task.flag_location)}</p>` : ""}
    <div class="concept-list">
      ${task.concepts.slice(0, 4).map((concept) => `<span>${escapeHtml(concept)}</span>`).join("")}
    </div>
    <a class="task-open" href="/challenge/${encodeURIComponent(task.id)}">${solved ? "Review solved subtask" : "Open subtask"}</a>
  `;
  return card;
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

bootContext();
