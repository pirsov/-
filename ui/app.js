async function api(path, opts) {
  let r;
  try {
    r = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
  } catch (_) {
    const err = new Error("Сервер не отвечает. Запусти: python -u run.py --ui");
    throw err;
  }
  let j = {};
  try { j = await r.json(); } catch (_) { /* empty */ }
  if (!r.ok) throw new Error(humanError(j.error || r.statusText || JSON.stringify(j)));
  return j;
}

function humanError(raw) {
  const s = String(raw || "");
  if (/DEEPSEEK_API_KEY|deepseek.*unset|нет ключа/i.test(s)) {
    return "Нет ключа DeepSeek. Задай User env DEEPSEEK_API_KEY.";
  }
  if (/ollama|11434|Connection refused|URLError/i.test(s)) {
    return "Ollama down. Запусти ollama serve.";
  }
  if (/goal empty/i.test(s)) return "Сначала введи текст цели.";
  return s;
}

function el(id) { return document.getElementById(id); }

function toast(msg) {
  const t = el("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._tm);
  toast._tm = setTimeout(() => { t.hidden = true; }, 5200);
}

let pollTimer = null;
let snapPollTimer = null;
let logPollTimer = null;
let runStartedAt = null;
let timerTick = null;
let smokeQs = [];
let smokeLoaded = false;
let smokeAnswers = {};
let lastFileContent = "";
let focusStage = 1;
let lastProgress = null;
let pendingHitl = null;
let selectedHitl = {};
let filesPollTimer = null;
let lastFilePath = "";
let knownFilePaths = [];
let loop24Active = false;
let lastLogText = "";
let lastHitlAskShown = "";
let lastCurrentTask = "";

function isLoop24Active(run, snap) {
  const st = (run && run.status) || "";
  const mode = (run && run.mode) || (snap && snap.mode) || null;
  if (mode === "loop_24h" && (st === "running" || st === "looping" || st === "waiting_human")) {
    return true;
  }
  if (st === "looping") return true;
  if (st === "running" && mode === "loop_24h") return true;
  return false;
}

function syncStartStopButton(active) {
  loop24Active = !!active;
  const startBtn = el("btn-start-24h");
  const stopBtn = el("btn-stop-24h");
  if (startBtn) {
    startBtn.classList.add("btn-24h");
    if (loop24Active) {
      startBtn.dataset.mode = "stop";
      startBtn.textContent = "Остановить";
      startBtn.classList.remove("btn-start", "ghost");
      startBtn.classList.add("btn-stop");
    } else {
      startBtn.dataset.mode = "start";
      startBtn.textContent = "Старт 24h";
      startBtn.classList.remove("btn-stop", "ghost");
      startBtn.classList.add("btn-start");
    }
  }
  if (stopBtn) stopBtn.hidden = !loop24Active;
}

function highlightCode(text, path) {
  const codeEl = el("file-view-code");
  const pre = el("file-view");
  const label = el("file-path-label");
  if (label) label.textContent = path || "выбери файл";
  if (!codeEl) {
    if (pre) pre.textContent = text || "";
    return;
  }
  codeEl.textContent = text || "";
  const ext = String(path || "").split(".").pop() || "lua";
  const lang = ext === "luau" || ext === "lua" ? "lua" : (ext === "json" ? "json" : "plaintext");
  codeEl.className = "language-" + lang;
  if (window.hljs) {
    try { window.hljs.highlightElement(codeEl); } catch (_) { /* ignore */ }
  }
}


function formatTimer(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}

function startTimer(iso) {
  runStartedAt = iso ? Date.parse(iso) : Date.now();
  if (timerTick) clearInterval(timerTick);
  const tick = () => { el("run-timer").textContent = formatTimer(Date.now() - runStartedAt); };
  tick();
  timerTick = setInterval(tick, 1000);
}

function stopTimer() {
  if (timerTick) { clearInterval(timerTick); timerTick = null; }
}

function setFocus(n, { scroll = true } = {}) {
  focusStage = Math.max(1, Math.min(6, Number(n) || 1));
  document.querySelectorAll(".panel[data-stage]").forEach(panel => {
    const id = Number(panel.getAttribute("data-stage"));
    panel.classList.toggle("focus", id === focusStage);
  });
  if (scroll) {
    const panel = document.getElementById("panel-" + focusStage);
    if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (focusStage === 6) loadFixIssues().catch(() => {});
  if (focusStage === 5) restoreSmokeIfSaved().catch(() => {});
  syncPrimary();
}

function syncPrimary() {
  document.querySelectorAll(".btn").forEach(b => {
    if (b.id !== "btn-next" && b.id !== "modal-ok") b.classList.remove("primary");
  });
  const next = lastProgress && lastProgress.next_action;
  const nextText = el("next-text");
  const nextBtn = el("btn-next");
  const stageMeta = (lastProgress && lastProgress.stages || []).find(s => s.id === (lastProgress.stage || focusStage));
  const label = stageMeta
    ? `${String(stageMeta.id).padStart(2, "0")} · ${stageMeta.label}`
    : "…";
  if (next) {
    nextText.textContent = `${label} — ${next.label || ""}`;
    nextBtn.textContent = next.label || "Далее";
    nextBtn.disabled = !next.button;
    nextBtn.onclick = () => {
      if (!next.button) return;
      setFocus(next.stage || focusStage);
      const target = el(next.button);
      if (target && !target.disabled) target.click();
    };
    if (next.button) {
      const primary = el(next.button);
      if (primary) primary.classList.add("primary");
    }
    nextBtn.classList.add("primary");
  }
}

function applyProgress(progress) {
  lastProgress = progress;
  const stages = progress.stages || [];
  const current = progress.stage || 1;

  el("stage-rail").innerHTML = stages.map(st => {
    const mark = st.state === "done" ? "✓" : (st.state === "skipped" ? "↷" : st.id);
    return `<button type="button" class="stage-dot ${st.state}" data-stage="${st.id}" title="${st.hint || st.why || st.label}">
      <span class="n">${mark}</span>
      <span class="lbl-full">${st.label}</span>
      <span class="lbl-short">${st.id}</span>
    </button>`;
  }).join("");

  el("stage-rail").querySelectorAll(".stage-dot").forEach(btn => {
    btn.onclick = () => {
      const n = Number(btn.getAttribute("data-stage"));
      const st = stages.find(x => x.id === n);
      if (st && st.state === "locked" && n > current) {
        toast(st.hint || "Сначала заверши или пропусти предыдущий шаг");
      }
      setFocus(n);
    };
  });

  stages.forEach(st => {
    const badge = document.querySelector(`[data-badge="${st.id}"]`);
    if (!badge) return;
    badge.className = "badge " + st.state;
    badge.textContent = st.state === "done" ? "✓ done"
      : st.state === "skipped" ? "↷ skip"
      : st.state === "current" ? "сейчас"
      : "locked";
    const skipBtn = document.querySelector(`.btn-skip[data-skip="${st.id}"]`);
    const unskipBtn = document.querySelector(`.btn-unskip[data-unskip="${st.id}"]`);
    if (skipBtn) skipBtn.hidden = !st.can_skip || st.skipped || st.done;
    if (unskipBtn) unskipBtn.hidden = !st.skipped;
  });

  const c = progress.counts || {};
  const iss = c.issues != null ? c.issues : (progress.issue_count || 0);
  el("counts").textContent =
    `TZ ${c.tz_tasks || 0} · Luau ${c.luau_files || 0} · skills ${c.compact_skills || 0}` +
    (iss ? ` · ошибки ${iss}` : "");

  // Keep user focus if they switched; otherwise follow recommended current.
  if (!document.querySelector(".panel.focus")) setFocus(current, { scroll: false });
  else syncPrimary();
}

function setChip(id, ok, okText, badText) {
  const n = el(id);
  n.classList.toggle("ok", !!ok);
  n.classList.toggle("bad", !ok);
  n.textContent = ok ? okText : badText;
}

async function refresh() {
  try {
    const s = await api("/api/status");
    setChip("ds-status", s.deepseek, "DeepSeek: OK", "DeepSeek: нет ключа");
    const ol = (s.health && s.health.ollama) || {};
    setChip("ollama-status", !!ol.ok, `Ollama: OK (${ol.count || 0})`, "Ollama: down");
    el("raw-count").textContent = String(s.raw_count || 0);
    el("projects").innerHTML = (s.projects || []).map(p =>
      `<div><strong>${p.id}</strong> — ${p.title || ""} · luau ${p.luau_files || 0}</div>`
    ).join("") || "<p class='muted'>нет проектов</p>";
    el("compact").innerHTML = (s.compact || []).map(c =>
      `<div><strong>${c.id}</strong> · ${c.chars}c · promoted=${c.promoted}</div>`
    ).join("");
    applyProgress(s.progress);
    if (!document.querySelector(".panel.focus")) setFocus(s.progress.stage || 1, { scroll: false });
    if (s.run) renderRun(s.run);
    if (s.current_task != null) setCurrentTask(s.current_task);
    if (s.snapshot) renderAgentSnap(s.snapshot);
    else if (s.hitl_pack || s.waiting_human != null || s.current_task != null) {
      renderAgentSnap({
        waiting_human: s.waiting_human,
        hitl_pack: s.hitl_pack,
        plugins_closed: s.plugins_closed,
        queue_pending: s.queue_pending,
        current_task: s.current_task,
        run: s.run,
      });
    }
  } catch (e) {
    setChip("ds-status", false, "", "Сервер: offline");
    setChip("ollama-status", false, "", "—");
    toast(String(e.message || e));
  }
}

async function refreshProgressOnly() {
  try {
    const p = await api("/api/progress?smoke_loaded=" + (smokeLoaded ? "1" : "0"));
    applyProgress(p);
  } catch (_) { /* ignore */ }
}

async function doSkip(stage, opts = {}) {
  const j = await api("/api/progress/skip", {
    method: "POST",
    body: JSON.stringify({ stage, through: opts.through, undo: !!opts.undo }),
  });
  applyProgress(j.progress);
  const next = (j.progress && j.progress.stage) || stage;
  setFocus(opts.undo ? stage : next);
  toast(opts.undo ? "Шаг возвращён в поток" : "Шаг пропущен");
}

document.querySelectorAll(".btn-skip").forEach(btn => {
  btn.onclick = async (e) => {
    e.stopPropagation();
    try { await doSkip(Number(btn.getAttribute("data-skip"))); }
    catch (err) { toast(String(err.message || err)); }
  };
});
document.querySelectorAll(".btn-unskip").forEach(btn => {
  btn.onclick = async (e) => {
    e.stopPropagation();
    try { await doSkip(Number(btn.getAttribute("data-unskip")), { undo: true }); }
    catch (err) { toast(String(err.message || err)); }
  };
});

el("btn-skip-to-smoke").onclick = (e) => {
  e.stopPropagation();
  el("modal").hidden = false;
};
el("modal-cancel").onclick = () => { el("modal").hidden = true; };
el("modal-ok").onclick = async () => {
  el("modal").hidden = true;
  try {
    await doSkip(1, { through: 4 });
    setFocus(5);
  } catch (err) {
    toast(String(err.message || err));
  }
};

document.querySelectorAll(".panel[data-stage]").forEach(panel => {
  panel.addEventListener("click", (e) => {
    if (e.target.closest("button, textarea, input, a, label, pre")) return;
    setFocus(Number(panel.getAttribute("data-stage")));
  });
});

function renderRun(run) {
  const st = run.status || "idle";
  const pill = el("run-status");
  pill.className = "run-pill " + st;
  pill.querySelector(".run-label").textContent =
    st + (run.exit_code != null ? ` · exit ${run.exit_code}` : "");
  if (st === "running") {
    if (!runStartedAt) startTimer(run.started_at);
  } else if (st === "done" || st === "error") {
    stopTimer();
  }
  const rep = run.report || {};
  el("run-report").textContent = JSON.stringify({
    status: st,
    quality: rep.quality,
    started_tasks: rep.started_tasks,
    done_notes: rep.done_notes,
    wrote_files: rep.wrote_files,
    validator_fails: rep.validator_fails,
    hitl_seen: rep.hitl_seen,
    lines: rep.lines,
  }, null, 2);
  const box = el("run-log");
  if (run.log_tail) {
    const auto = el("log-autoscroll").checked;
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    box.textContent = run.log_tail;
    if (auto || atBottom) box.scrollTop = box.scrollHeight;
  }
  if (st === "running") {
    startPoll();
    startFilesPoll();
  }
  if (st === "done" || st === "error") {
    stopPoll();
    stopFilesPoll();
    loadFiles({ autoOpen: !lastFilePath }).catch(() => {});
    refreshProgressOnly();
  }
  if (st === "idle" && !loop24Active) stopFilesPoll();
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try { renderRun(await api("/api/run/status")); }
    catch (e) { toast(String(e.message || e)); }
  }, 3000);
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function shortFileLabel(path) {
  const p = String(path || "");
  const parts = p.split("/");
  if (parts.length <= 3) return p;
  return parts.slice(-3).join("/");
}

async function openCodeFile(path) {
  if (!path) return;
  lastFilePath = path;
  const file = await api("/api/file?path=" + encodeURIComponent(path));
  lastFileContent = file.content || "";
  highlightCode(lastFileContent, path);
  const copyBtn = el("btn-copy-code");
  if (copyBtn) copyBtn.disabled = !lastFileContent;
  document.querySelectorAll(".tree-file > button").forEach(b => {
    b.classList.toggle("active", b.getAttribute("data-path") === path);
  });
  const list = el("file-list");
  if (list) {
    list.querySelectorAll(".file-btn").forEach(b => {
      b.classList.toggle("active", b.getAttribute("data-path") === path);
    });
  }
  const sel = el("file-select");
  if (sel && sel.value !== path) sel.value = path;
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderTreeNodes(nodes, depth) {
  if (!Array.isArray(nodes) || !nodes.length) return "";
  return nodes.map(node => {
    if (node.type === "dir") {
      const open = depth < 2 ? " open" : "";
      return `<details class="tree-dir"${open}>
        <summary>${escapeHtml(node.name)}</summary>
        <div class="tree-kids">${renderTreeNodes(node.children || [], depth + 1)}</div>
      </details>`;
    }
    const path = node.path || "";
    const active = path === lastFilePath ? " active" : "";
    return `<div class="tree-file">
      <button type="button" data-path="${escapeHtml(path)}" class="${active.trim()}" title="${escapeHtml(path)}">${escapeHtml(node.name)}</button>
    </div>`;
  }).join("");
}

function bindFileTreeClicks(rootEl) {
  if (!rootEl) return;
  rootEl.querySelectorAll(".tree-file > button").forEach(btn => {
    btn.onclick = () => {
      openCodeFile(btn.getAttribute("data-path")).catch(e => toast(String(e.message || e)));
    };
  });
}

function renderFileExplorer(paths, tree) {
  const list = Array.isArray(paths) ? paths.slice() : [];
  knownFilePaths = list;
  const sel = el("file-select");
  const box = el("file-list");
  const treeEl = el("file-tree");
  if (sel) {
    const prev = lastFilePath || sel.value;
    sel.innerHTML = list.length
      ? list.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(shortFileLabel(p))}</option>`).join("")
      : `<option value="">— нет файлов —</option>`;
    if (prev && list.includes(prev)) sel.value = prev;
  }
  if (treeEl) {
    if (Array.isArray(tree) && tree.length) treeEl.innerHTML = renderTreeNodes(tree, 0);
    else if (list.length) {
      treeEl.innerHTML = list.map(p => {
        const active = p === lastFilePath ? " active" : "";
        return `<div class="tree-file"><button type="button" data-path="${escapeHtml(p)}" class="${active.trim()}" title="${escapeHtml(p)}">${escapeHtml(shortFileLabel(p))}</button></div>`;
      }).join("");
    } else treeEl.innerHTML = "<p class='muted'>нет файлов — агент ещё не записал код</p>";
    bindFileTreeClicks(treeEl);
  }
  if (box) {
    box.innerHTML = list.map(p =>
      `<button type="button" class="btn file-btn${p === lastFilePath ? " active" : ""}" data-path="${escapeHtml(p)}" title="${escapeHtml(p)}">${escapeHtml(shortFileLabel(p))}</button>`
    ).join("") || "<p class='muted'>нет файлов</p>";
    box.querySelectorAll(".file-btn").forEach(btn => {
      btn.onclick = () => openCodeFile(btn.getAttribute("data-path")).catch(e => toast(String(e.message || e)));
    });
  }
}

async function loadFiles({ autoOpen = true } = {}) {
  const j = await api("/api/files");
  const files = Array.isArray(j.files) ? j.files : [];
  const tree = j.tree;
  const prev = lastFilePath;
  renderFileExplorer(files, tree);
  if (!files.length) {
    lastFileContent = "";
    highlightCode("", "");
    const copyBtn = el("btn-copy-code");
    if (copyBtn) copyBtn.disabled = true;
    return files;
  }
  const keep = prev && files.includes(prev) ? prev : files[0];
  if (autoOpen && (!prev || !files.includes(prev) || !lastFileContent)) await openCodeFile(keep);
  else if (autoOpen && keep !== prev) await openCodeFile(keep);
  else renderFileExplorer(files, tree);
  return files;
}

function startFilesPoll() {
  if (filesPollTimer) return;
  filesPollTimer = setInterval(() => { loadFiles({ autoOpen: false }).catch(() => {}); }, 3000);
}
function stopFilesPoll() {
  if (filesPollTimer) { clearInterval(filesPollTimer); filesPollTimer = null; }
}

if (el("file-select")) {
  el("file-select").onchange = () => {
    const p = el("file-select").value;
    if (p) openCodeFile(p).catch(e => toast(String(e.message || e)));
  };
}

el("btn-copy-code").onclick = async () => {
  if (!lastFileContent) return;
  try {
    await navigator.clipboard.writeText(lastFileContent);
    toast("Скопировано");
  } catch (_) { toast("Не удалось скопировать"); }
};

el("btn-activate").onclick = async () => {
  try {
    await api("/api/activate", { method: "POST", body: JSON.stringify({ project: "game1" }) });
    await refresh();
    setFocus(2);
  } catch (e) { toast(String(e.message || e)); }
};

el("btn-improve-goal").onclick = async () => {
  const btn = el("btn-improve-goal");
  const goalBox = el("goal");
  const prev = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Улучшаю…";
  try {
    const j = await api("/api/goal/improve", {
      method: "POST",
      body: JSON.stringify({ project: "game1", goal: goalBox.value }),
    });
    goalBox.value = j.goal || goalBox.value;
    goalBox.classList.remove("flash");
    void goalBox.offsetWidth;
    goalBox.classList.add("flash");
    const hint = (j.skills_hint || []).join(", ");
    toast(hint ? `Промт улучшен · skills: ${hint}` : "Промт улучшен");
  } catch (e) {
    toast(String(e.message || e));
  } finally {
    btn.disabled = false;
    btn.textContent = prev;
  }
};

el("btn-auto").onclick = async () => {
  el("compress-out").textContent = "DeepSeek выбирает skills…";
  try {
    const j = await api("/api/skills/auto", {
      method: "POST",
      body: JSON.stringify({ project: "game1", goal: el("goal").value, max_pick: 3 }),
    });
    el("compress-out").textContent = JSON.stringify(j, null, 2);
    await refresh();
    setFocus(3);
  } catch (e) {
    el("compress-out").textContent = String(e.message || e);
    toast(String(e.message || e));
  }
};

el("btn-tz").onclick = async () => {
  el("tz-out").textContent = "…";
  try {
    const j = await api("/api/tz", {
      method: "POST",
      body: JSON.stringify({ project: "game1", goal: el("goal").value }),
    });
    el("tz-out").textContent = `task_lines=${j.task_lines} fits_ctx=${j.fits_ctx}\n\n` + (j.preview || "");
    await refresh();
    setFocus(4);
  } catch (e) {
    el("tz-out").textContent = String(e.message || e);
    toast(String(e.message || e));
  }
};

el("btn-run").onclick = async () => {
  el("run-report").textContent = "starting…";
  el("run-log").textContent = "";
  el("file-view").textContent = "";
  el("file-list").innerHTML = "";
  runStartedAt = null;
  try {
    const j = await api("/api/run/start", {
      method: "POST",
      body: JSON.stringify({ sleep: 0, hitl: "y" }),
    });
    startTimer(j.started_at);
    renderRun(j);
    startPoll();
  } catch (e) {
    el("run-report").textContent = String(e.message || e);
    toast(String(e.message || e));
  }
};

function otherDetail(qid) {
  const inp = el("smoke") && el("smoke").querySelector(`input[data-other="${qid}"]`);
  if (inp && typeof inp.value === "string") return inp.value.trim();
  const a = smokeAnswers[qid];
  return a && a.detail ? String(a.detail).trim() : "";
}

function smokeAnswered(qid) {
  const a = smokeAnswers[qid];
  if (!a) return false;
  if (a.answer === "y" || a.answer === "n") return true;
  if (a.answer === "other") return otherDetail(qid).length > 0;
  return false;
}

function updateSmokeProgress() {
  // Sync details from DOM so "Другое" text is never lost before submit
  for (const q of smokeQs) {
    const a = smokeAnswers[q.id];
    if (a && a.answer === "other") a.detail = otherDetail(q.id);
  }
  const total = smokeQs.length;
  let answered = 0;
  for (const q of smokeQs) {
    if (smokeAnswered(q.id)) answered += 1;
  }
  const pct = total ? Math.round((answered / total) * 100) : 0;
  el("smoke-bar").style.setProperty("--pct", pct + "%");
  el("smoke-count").textContent = `${answered}/${total} ответов`;
  el("btn-smoke-submit").disabled = !(total > 0 && answered === total);
  refreshProgressOnly();
}

function setSmokeChoice(qid, value) {
  const row = el("smoke").querySelector(`.q[data-id="${qid}"]`);
  if (!row) return;
  const inp = row.querySelector("input[data-other]");
  const typed = inp ? String(inp.value || "") : "";
  smokeAnswers[qid] = {
    answer: value,
    detail: value === "other" ? typed : "",
  };
  row.querySelectorAll(".yn-btn").forEach(b => {
    b.classList.toggle("active", b.getAttribute("data-v") === value);
  });
  const otherBox = row.querySelector(".smoke-other");
  if (otherBox) {
    otherBox.classList.toggle("open", value === "other");
    if (value === "other" && inp) {
      // keep existing text; focus for typing
      setTimeout(() => inp.focus(), 0);
    }
  }
  updateSmokeProgress();
}

function bindOtherInput(inp) {
  const sync = () => {
    const qid = inp.getAttribute("data-other");
    if (!qid) return;
    if (!smokeAnswers[qid] || smokeAnswers[qid].answer !== "other") {
      setSmokeChoice(qid, "other");
    } else {
      smokeAnswers[qid].detail = inp.value;
      updateSmokeProgress();
    }
  };
  inp.addEventListener("input", sync);
  inp.addEventListener("change", sync);
  inp.addEventListener("blur", sync);
  inp.addEventListener("keydown", (e) => {
    // stop panel/rail handlers from stealing keys
    e.stopPropagation();
  });
}

function renderSmokeQuestions(questions, savedAnswers) {
  smokeQs = questions || [];
  smokeLoaded = smokeQs.length > 0;
  Object.keys(smokeAnswers).forEach(k => delete smokeAnswers[k]);
  el("smoke").innerHTML = smokeQs.map((q, i) => `
    <div class="q" data-id="${q.id}">
      <div class="q-prompt"><span class="muted">${String(i + 1).padStart(2, "0")}</span> ${q.prompt}</div>
      <div class="yn">
        <button type="button" class="yn-btn y" data-v="y">Y</button>
        <button type="button" class="yn-btn n" data-v="n">N</button>
        <button type="button" class="yn-btn other" data-v="other">Другое</button>
      </div>
      <div class="smoke-other">
        <input type="text" data-other="${q.id}" autocomplete="off" placeholder="Уточни: что именно (например Best: -- не пишется)" />
      </div>
    </div>`).join("") || "<p class='muted'>нет вопросов</p>";
  el("smoke").querySelectorAll(".yn-btn").forEach(btn => {
    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      const qid = btn.closest(".q").getAttribute("data-id");
      setSmokeChoice(qid, btn.getAttribute("data-v"));
    };
  });
  el("smoke").querySelectorAll("input[data-other]").forEach(bindOtherInput);

  // Restore previously saved answers (after refresh)
  const saved = savedAnswers || {};
  for (const q of smokeQs) {
    const a = saved[q.id];
    if (!a || typeof a !== "object") continue;
    let ans = String(a.answer || "").toLowerCase();
    if (ans === "другое" || ans === "o") ans = "other";
    if (ans !== "y" && ans !== "n" && ans !== "other") continue;
    const row = el("smoke").querySelector(`.q[data-id="${q.id}"]`);
    if (!row) continue;
    const inp = row.querySelector("input[data-other]");
    if (inp && a.detail) inp.value = String(a.detail);
    smokeAnswers[q.id] = { answer: ans, detail: ans === "other" ? String(a.detail || "") : "" };
    row.querySelectorAll(".yn-btn").forEach(b => {
      b.classList.toggle("active", b.getAttribute("data-v") === ans);
    });
    const otherBox = row.querySelector(".smoke-other");
    if (otherBox) otherBox.classList.toggle("open", ans === "other");
  }
  updateSmokeProgress();
}

async function restoreSmokeIfSaved() {
  try {
    const latest = await api("/api/smoke/latest?project=game1");
    if (!latest.saved || !latest.answers || !Object.keys(latest.answers).length) {
      return false;
    }
    let questions = latest.questions || [];
    if (!questions.length) {
      // Fallback: rebuild question list from answer prompts
      questions = Object.entries(latest.answers).map(([id, v]) => ({
        id,
        prompt: (v && v.prompt) || id,
      }));
    }
    renderSmokeQuestions(questions, latest.answers);
    if (latest.others && latest.others.length) {
      el("smoke-out").textContent = JSON.stringify({
        restored: true,
        when: latest.when,
        others: latest.others,
        answers: latest.answers,
      }, null, 2);
    }
    return true;
  } catch (_) {
    return false;
  }
}

el("btn-smoke-load").onclick = async () => {
  try {
    // Prefer restoring saved smoke; only fetch fresh questions if none saved
    const restored = await restoreSmokeIfSaved();
    if (restored) {
      toast("Восстановлены сохранённые ответы smoke");
      return;
    }
    const j = await api("/api/smoke/questions?project=game1");
    renderSmokeQuestions(j.questions || [], {});
    toast("Y / N / Другое — текст Другое обязателен");
  } catch (e) { toast(String(e.message || e)); }
};

el("btn-smoke-submit").onclick = async () => {
  // Final DOM sync right before save
  updateSmokeProgress();
  const answers = {};
  let yes = 0, total = 0;
  for (const q of smokeQs) {
    const a = smokeAnswers[q.id] || {};
    let answer = a.answer;
    const detail = otherDetail(q.id);
    if (answer === "other" || detail) {
      // if user typed without clicking Другое, treat as other
      if (!answer || answer === "y" || answer === "n") {
        if (detail) answer = "other";
      }
    }
    if (answer === "other") {
      if (!detail) {
        toast(`Вопрос ${q.id}: напиши уточнение в «Другое»`);
        const row = el("smoke").querySelector(`.q[data-id="${q.id}"]`);
        if (row) {
          setSmokeChoice(q.id, "other");
          const inp = row.querySelector("input[data-other]");
          if (inp) inp.focus();
        }
        return;
      }
      answers[q.id] = { answer: "other", prompt: q.prompt, detail };
    } else if (answer === "y" || answer === "n") {
      answers[q.id] = { answer, prompt: q.prompt, detail: "" };
    } else {
      toast("Отметь все пункты: Y, N или Другое (с текстом)");
      return;
    }
    total += 1;
    if (answer === "y") yes += 1;
  }
  const overall_ok = total > 0 && yes / total >= 0.7;
  const notes = Object.entries(answers)
    .filter(([, v]) => v.answer === "other" && v.detail)
    .map(([id, v]) => `${id}: ${v.detail}`)
    .join(" | ");
  try {
    const j = await api("/api/smoke/submit", {
      method: "POST",
      body: JSON.stringify({
        project: "game1",
        answers,
        notes,
        overall_ok,
        promote_skills: overall_ok
          ? ["forge-player-attrs", "forge-luau-touch", "forge-ui-modern", "forge-ui-animation"]
          : [],
      }),
    });
    el("smoke-out").textContent = JSON.stringify({
      ok: j.ok,
      saved: j.saved,
      others: j.others,
      promoted: j.promoted,
      skipped_missing: j.skipped_missing,
      answers: j.answers,
    }, null, 2);
    const miss = (j.skipped_missing || []).length;
    const promo = (j.promoted || []).length;
    toast(
      miss
        ? `Сохранено · promote ${promo} · нет файлов: ${(j.skipped_missing || []).join(", ")}`
        : ((j.others && j.others.length)
          ? `Сохранено · Другое: ${j.others.length} · promote ${promo}`
          : (overall_ok ? `Smoke сохранён · promote ${promo}` : "Smoke сохранён"))
    );
    await refresh();
    setFocus(6);
    await loadFixIssues();
  } catch (e) { toast(String(e.message || e)); }
};

async function loadFixIssues() {
  const box = el("fix-issues");
  if (!box) return;
  try {
    const j = await api("/api/fix/issues?project=game1");
    const issues = j.issues || [];
    if (!issues.length) {
      box.innerHTML = "<p class='muted'>Ошибок smoke нет — всё Y. Можно пропустить блок 6.</p>";
      return;
    }
    box.innerHTML = issues.map(it => `
      <div>
        <strong>${it.id}</strong>
        <span class="badge ${it.answer === "other" ? "current" : "skipped"}">${it.answer}</span>
        — ${it.prompt || ""}
        ${it.detail ? `<div class="muted">↳ ${it.detail}</div>` : ""}
      </div>
    `).join("");
  } catch (e) {
    box.innerHTML = `<p class="muted">${String(e.message || e)}</p>`;
  }
}

el("btn-fix-refresh").onclick = async () => {
  try { await loadFixIssues(); toast("Список обновлён"); }
  catch (e) { toast(String(e.message || e)); }
};

el("btn-fix-tz").onclick = async () => {
  el("fix-out").textContent = "Собираю TZ из smoke N/Другое…";
  try {
    const j = await api("/api/fix/from-smoke", {
      method: "POST",
      body: JSON.stringify({ project: "game1" }),
    });
    el("fix-out").textContent =
      `issues=${(j.issues || []).length} task_lines=${j.task_lines}\n\n` + (j.preview || j.message || "");
    if (j.progress) applyProgress(j.progress);
    toast(j.task_lines ? `TZ фиксов: ${j.task_lines} задач` : (j.message || "Готово"));
    await loadFixIssues();
  } catch (e) {
    el("fix-out").textContent = String(e.message || e);
    toast(String(e.message || e));
  }
};

el("btn-fix-run").onclick = async () => {
  setFocus(4, { scroll: false });
  el("run-report").textContent = "starting fix week…";
  el("run-log").textContent = "";
  runStartedAt = null;
  try {
    // Restore game1 snapshot into live src/ so week has real files + pending F*
    try {
      await api("/api/activate", { method: "POST", body: JSON.stringify({ project: "game1" }) });
    } catch (_) { /* continue even if already active */ }
    const j = await api("/api/run/start", {
      method: "POST",
      body: JSON.stringify({ sleep: 0, hitl: "y" }),
    });
    startTimer(j.started_at);
    renderRun(j);
    startPoll();
    setFocus(4);
    toast("Фиксы: activate game1 + --week (блок 4)");
  } catch (e) {
    toast(String(e.message || e));
    setFocus(6);
  }
};

el("btn-fix-done").onclick = async () => {
  try {
    const j = await api("/api/fix/done", { method: "POST", body: "{}" });
    if (j.progress) applyProgress(j.progress);
    toast("Фиксы отмечены готовыми");
  } catch (e) { toast(String(e.message || e)); }
};

function chatAppend(role, text) {
  const box = el("chat-log");
  if (!box) return;
  const line = document.createElement("div");
  line.className = "chat-line " + role;
  line.textContent = text;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function setAgentPill(status) {
  const pill = el("agent-status");
  if (!pill) return;
  const st = status || "idle";
  pill.className = "run-pill " + st;
  pill.querySelector(".run-label").textContent = st;
}

function renderHitlPack(pack) {
  pendingHitl = pack && pack.questions ? pack : null;
  selectedHitl = {};
  const box = el("hitl-box");
  const ask = el("hitl-ask");
  const opts = el("hitl-options");
  const otherWrap = el("hitl-other-wrap");
  if (!box) return;
  if (!pendingHitl) {
    box.hidden = true;
    return;
  }
  const q = (pendingHitl.questions || [])[0] || {};
  const qid = String(q.id || "Q1");
  ask.textContent = (q.ask || q.topic || "Вопрос агента") + (qid ? ` (${qid})` : "");
  opts.innerHTML = "";
  ["A", "B", "C"].forEach((key) => {
    const opt = (q.options || []).find(o => String(o.key || "").toUpperCase() === key);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn";
    btn.textContent = opt && opt.label ? `${key}. ${opt.label}` : key;
    btn.onclick = () => sendHitlAnswer(qid, key);
    opts.appendChild(btn);
  });
  const otherBtn = document.createElement("button");
  otherBtn.type = "button";
  otherBtn.className = "btn ghost";
  otherBtn.textContent = "Другое";
  otherBtn.onclick = () => {
    otherWrap.hidden = false;
    el("hitl-other").focus();
    otherWrap.dataset.qid = qid;
  };
  opts.appendChild(otherBtn);
  otherWrap.hidden = true;
  el("hitl-other").value = "";
  box.hidden = false;
}

async function sendHitlAnswer(qid, key, note) {
  try {
    chatAppend("user", `${qid}=${key}` + (note ? ` · ${note}` : ""));
    const body = note
      ? { answers: { [qid]: "other" }, note }
      : { answer: `${qid}=${key}` };
    const j = await api("/api/answer", { method: "POST", body: JSON.stringify(body) });
    el("hitl-box").hidden = true;
    if (j.status === "waiting_human" && j.hitl_pack) {
      chatAppend("agent", "Нужно уточнение");
      renderHitlPack(j.hitl_pack);
    } else {
      chatAppend("agent", j.message || "Ответ принят — агент продолжает");
      pendingHitl = null;
      el("hitl-box").hidden = true;
      // Do not leave a stale pack visible; 24h should go idle→week, not re-ask Q1
      if (j.next && j.next.action && j.next.action !== "ask_hitl") {
        /* keep hitl hidden */
      }
    }
    if (j.snapshot) renderAgentSnap(j.snapshot);
    toast("Ответ отправлен");
  } catch (e) {
    toast(String(e.message || e));
  }
}

el("hitl-other") && (el("hitl-other").onkeydown = async (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  const qid = el("hitl-other-wrap").dataset.qid || "Q1";
  const note = el("hitl-other").value.trim();
  if (!note) { toast("Напиши уточнение"); return; }
  await sendHitlAnswer(qid, "other", note);
});

function setCurrentTask(label) {
  const node = el("current-task");
  if (!node) return;
  const text = (label || "").trim();
  lastCurrentTask = text;
  if (!text) {
    node.textContent = "задача —";
    node.classList.add("is-empty");
    return;
  }
  node.textContent = text;
  node.classList.remove("is-empty");
}

function setLoopWaiting(waiting) {
  const progress = el("loop-progress");
  if (progress) progress.classList.toggle("waiting", !!waiting);
}

function maybeShowHitlInChat(pack) {
  if (!pack || !pack.questions) return;
  const q = (pack.questions || [])[0] || {};
  const ask = String(q.ask || q.topic || "").trim();
  if (!ask || ask === lastHitlAskShown) return;
  lastHitlAskShown = ask;
  const qid = q.id ? ` (${q.id})` : "";
  chatAppend("agent", ask + qid);
}

function renderAgentSnap(snap) {
  if (!snap) return;
  const run = snap.run || {};
  const st = run.status || (snap.waiting_human ? "waiting_human" : "idle");
  const waiting = !!(snap.waiting_human || st === "waiting_human");
  setAgentPill(st);
  setLoopWaiting(waiting);
  if (snap.current_task != null) setCurrentTask(snap.current_task);
  else if (run.current_task != null) setCurrentTask(run.current_task);
  const closed = Number(snap.plugins_closed || 0);
  const pending = Number(snap.queue_pending || 0);
  const total = Math.max(closed + pending, 1);
  const pct = Math.round((closed / total) * 100);
  const bar = el("loop-bar");
  if (bar) bar.style.setProperty("--pct", pct + "%");
  const stats = el("loop-stats");
  if (stats) {
    const cycle = run.loop_cycle != null ? ` · цикл ${run.loop_cycle}/${run.loop_max || "?"}` : "";
    stats.textContent = `плагины ${closed} · очередь ${pending}${cycle}`;
  }
  const active24 = isLoop24Active(run, snap);
  syncStartStopButton(active24);
  if (waiting && snap.hitl_pack) {
    renderHitlPack(snap.hitl_pack);
    maybeShowHitlInChat(snap.hitl_pack);
  } else if (!waiting) {
    lastHitlAskShown = "";
  }
  if (st === "looping" || st === "waiting_human" || st === "running") {
    startSnapPoll();
    startFilesPoll();
  } else if (st === "idle" || st === "done" || st === "error") {
    stopSnapPoll();
    if (!active24) stopFilesPoll();
  }
}

async function refreshLogs() {
  const box = el("run-log");
  if (!box) return;
  const j = await api("/api/logs?lines=100");
  const text = j.text || (j.lines || []).join("\n");
  if (text === lastLogText) return;
  lastLogText = text;
  const autoEl = el("log-autoscroll");
  const auto = !autoEl || autoEl.checked;
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  box.textContent = text || "";
  if (auto || atBottom) box.scrollTop = box.scrollHeight;
}

function startLogPoll() {
  if (logPollTimer) return;
  refreshLogs().catch(() => {});
  logPollTimer = setInterval(() => {
    refreshLogs().catch(() => {});
  }, 2000);
}

function stopLogPoll() {
  if (logPollTimer) { clearInterval(logPollTimer); logPollTimer = null; }
}

function startSnapPoll() {
  if (snapPollTimer) return;
  snapPollTimer = setInterval(async () => {
    try {
      const s = await api("/api/status_snapshot");
      renderAgentSnap(s);
    } catch (_) { /* ignore */ }
  }, 3000);
}

/** Unified 3s status poll — progress, step, Start/Stop (non-blocking). */
let statusPollTimer = null;
function startStatusPoll() {
  if (statusPollTimer) return;
  statusPollTimer = setInterval(async () => {
    try {
      const s = await api("/api/status");
      if (s.deepseek != null) setChip("ds-status", s.deepseek, "DeepSeek: OK", "DeepSeek: нет ключа");
      const ol = (s.health && s.health.ollama) || {};
      if (el("ollama-status")) setChip("ollama-status", !!ol.ok, `Ollama: OK (${ol.count || 0})`, "Ollama: down");
      if (s.progress) applyProgress(s.progress);
      if (s.run) renderRun(s.run);
      if (s.current_task != null && !(s.snapshot && s.snapshot.current_task != null)) {
        setCurrentTask(s.current_task);
      }
      if (s.snapshot) renderAgentSnap(s.snapshot);
      else if (s.run) {
        renderAgentSnap({
          waiting_human: s.waiting_human,
          hitl_pack: s.hitl_pack,
          plugins_closed: s.plugins_closed,
          queue_pending: s.queue_pending,
          current_task: s.current_task,
          run: s.run,
        });
      }
      const st = (s.run && s.run.status) || "";
      const active = isLoop24Active(s.run, s.snapshot || s);
      if (st === "running" || st === "looping" || active) {
        syncStartStopButton(true);
        startFilesPoll();
      } else if (!active) syncStartStopButton(false);
    } catch (_) {}
  }, 3000);
}

function stopSnapPoll() {
  if (snapPollTimer) { clearInterval(snapPollTimer); snapPollTimer = null; }
}

el("chat-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const input = el("chat-input");
  const msg = (input.value || "").trim();
  if (!msg) return;
  input.value = "";
  chatAppend("user", msg);
  el("btn-chat").disabled = true;
  try {
    const j = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: msg, project: "game1" }),
    });
    if (j.goal) chatAppend("sys", "цель: " + j.goal);
    if (j.status === "waiting_human") {
      chatAppend("agent", j.message || "Нужен ответ A/B/C");
      if (j.hitl_pack) {
        renderHitlPack(j.hitl_pack);
        maybeShowHitlInChat(j.hitl_pack);
      } else if (j.verify_plugin) {
        chatAppend("agent", `Проверь плагин ${j.verify_plugin}`);
      }
      setAgentPill("waiting_human");
      setLoopWaiting(true);
      startSnapPoll();
    } else {
      chatAppend("agent", j.message || ("готово · " + (j.plan_action || "ready")));
      if (j.snapshot) renderAgentSnap(j.snapshot);
    }
    if (j.tz_tasks) chatAppend("sys", `TZ draft: ${j.tz_tasks} задач`);
  } catch (e) {
    chatAppend("sys", String(e.message || e));
    toast(String(e.message || e));
  } finally {
    el("btn-chat").disabled = false;
  }
};

async function doStop24h() {
  const j = await api("/api/stop_24h", { method: "POST", body: "{}" });
  chatAppend("sys", "24h stopped");
  renderAgentSnap({ run: j, waiting_human: false });
  syncStartStopButton(false);
  stopSnapPoll();
  stopFilesPoll();
  toast("24h остановлен");
  return j;
}

async function doStart24h() {
  // A20.1: do not pass week_max_steps=5 — that became `--max 5` and killed the week
  // after 5 tasks. Omit max so server uses high default (500); max_cycles stays cycle budget.
  const j = await api("/api/start_24h", {
    method: "POST",
    body: JSON.stringify({ sleep: 5, max_cycles: 48 }),
  });
  chatAppend("sys", "24h loop started");
  renderAgentSnap({
    run: j,
    plugins_closed: 0,
    queue_pending: 0,
    waiting_human: j.status === "waiting_human",
  });
  syncStartStopButton(true);
  startSnapPoll();
  startFilesPoll();
  loadFiles({ autoOpen: false }).catch(() => {});
  toast("24h запущен");
  return j;
}

el("btn-start-24h").onclick = async () => {
  const mode = el("btn-start-24h").dataset.mode || "start";
  try {
    if (mode === "stop" || loop24Active) await doStop24h();
    else await doStart24h();
  } catch (e) {
    toast(String(e.message || e));
  }
};

el("btn-stop-24h").onclick = async () => {
  try { await doStop24h(); }
  catch (e) { toast(String(e.message || e)); }
};

refresh().then(async () => {
  if (lastProgress) setFocus(lastProgress.stage || 1, { scroll: false });
  loadFiles({ autoOpen: true }).catch(() => {});
  startStatusPoll();
  startLogPoll();
  // After reload: if smoke already done, put answers back into panel 5
  const flags = (lastProgress && lastProgress.flags) || {};
  if (flags.smoke_done || (lastProgress && lastProgress.issue_count > 0)) {
    const ok = await restoreSmokeIfSaved();
    if (ok) {
      // keep focus on recommended stage (often 6), but answers stay visible in 5
    }
  }
}).catch(e => toast(String(e.message || e)));
