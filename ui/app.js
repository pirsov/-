async function api(path, opts) {
  let r;
  try {
    r = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
  } catch (e) {
    const err = new Error("Сервер не отвечает. Запусти: python -u run.py --ui");
    err.code = "offline";
    throw err;
  }
  let j = {};
  try { j = await r.json(); } catch (_) { /* empty */ }
  if (!r.ok) {
    const msg = humanError(j.error || r.statusText || JSON.stringify(j));
    const err = new Error(msg);
    err.code = "http";
    throw err;
  }
  return j;
}

function humanError(raw) {
  const s = String(raw || "");
  if (/DEEPSEEK_API_KEY|deepseek.*unset|нет ключа/i.test(s)) {
    return "Нет ключа DeepSeek. Задай User env DEEPSEEK_API_KEY и перезапусти UI.";
  }
  if (/ollama|11434|Connection refused|URLError/i.test(s)) {
    return "Ollama down. Запусти ollama serve (порт 11434) и обнови страницу.";
  }
  if (/Unauthorized|401/i.test(s)) {
    return "Ключ отклонён (401). Проверь DEEPSEEK_API_KEY / OpenRouter.";
  }
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
let runStartedAt = null;
let timerTick = null;
let smokeQs = [];
let smokeLoaded = false;
let lastFileContent = "";
let lastStage = null;

function formatTimer(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return String(m).padStart(2, "0") + ":" + String(r).padStart(2, "0");
}

function startTimer(iso) {
  runStartedAt = iso ? Date.parse(iso) : Date.now();
  if (timerTick) clearInterval(timerTick);
  const tick = () => {
    el("run-timer").textContent = formatTimer(Date.now() - runStartedAt);
  };
  tick();
  timerTick = setInterval(tick, 1000);
}

function stopTimer() {
  if (timerTick) {
    clearInterval(timerTick);
    timerTick = null;
  }
}

function applyProgress(progress) {
  const stages = (progress && progress.stages) || [];
  const unlocked = (progress && progress.unlocked) || { "1": true };
  const current = (progress && progress.stage) || 1;
  const lockHints = (progress && progress.lock_hints) || {};

  el("stage-rail").innerHTML = stages.map(st => {
    const short = String(st.id);
    return `<button type="button" class="stage-dot ${st.state}" data-stage="${st.id}" title="${st.hint || st.label}">
      <span class="n">${st.state === "done" ? "✓" : short}</span>
      <span class="lbl-full">${st.label}</span>
      <span class="lbl-short">${short}</span>
    </button>`;
  }).join("");

  el("stage-rail").querySelectorAll(".stage-dot").forEach(btn => {
    btn.onclick = () => {
      const n = btn.getAttribute("data-stage");
      const st = stages.find(x => String(x.id) === n);
      if (st && st.state === "locked") {
        toast(st.hint || lockHints[n] || "Сначала заверши предыдущий шаг");
        return;
      }
      const panel = document.getElementById("panel-" + n);
      if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });

  document.querySelectorAll(".panel[data-stage]").forEach(panel => {
    const n = panel.getAttribute("data-stage");
    const on = !!unlocked[n];
    const wasLocked = panel.classList.contains("locked");
    panel.classList.toggle("locked", !on);
    const hint = panel.querySelector(".lock-msg");
    if (hint && lockHints[n]) hint.textContent = lockHints[n];
    if (wasLocked && on) {
      panel.classList.remove("unlocking");
      void panel.offsetWidth;
      panel.classList.add("unlocking");
      setTimeout(() => panel.classList.remove("unlocking"), 320);
    }
    panel.querySelectorAll("button, textarea, input").forEach(ctrl => {
      if (ctrl.id === "btn-smoke-submit") return; // managed separately
      if (ctrl.id === "btn-copy-code") return;
      if (ctrl.id === "log-autoscroll") return;
      if (!on) ctrl.setAttribute("disabled", "disabled");
      else ctrl.removeAttribute("disabled");
    });
  });

  // One primary CTA
  document.querySelectorAll(".btn").forEach(b => b.classList.remove("primary"));
  const next = progress && progress.next_action;
  const nextText = el("next-text");
  const nextBtn = el("btn-next");
  if (next) {
    nextText.textContent = next.label || "—";
    nextBtn.textContent = next.label || "Далее";
    nextBtn.disabled = !next.button;
    nextBtn.onclick = () => {
      if (!next.button) return;
      const target = el(next.button);
      if (target && !target.disabled) target.click();
      else if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
    };
    if (next.button) {
      const primary = el(next.button);
      if (primary) primary.classList.add("primary");
    }
    nextBtn.classList.add("primary");
  }

  const c = (progress && progress.counts) || {};
  el("counts").textContent =
    `TZ ${c.tz_tasks || 0} · Luau ${c.luau_files || 0} · skills ${c.compact_skills || 0}`;

  lastStage = current;
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
    setChip(
      "ollama-status",
      !!ol.ok,
      `Ollama: OK (${ol.count || 0})`,
      "Ollama: down"
    );
    el("raw-count").textContent = String(s.raw_count || 0);
    el("projects").innerHTML = (s.projects || []).map(p =>
      `<div><strong>${p.id}</strong> — ${p.title || ""} · luau ${p.luau_files || 0}</div>`
    ).join("") || "<p class='muted'>нет проектов</p>";
    el("compact").innerHTML = (s.compact || []).map(c =>
      `<div><strong>${c.id}</strong> · ${c.chars}c · promoted=${c.promoted}</div>`
    ).join("");
    applyProgress(s.progress);
    if (s.run) renderRun(s.run);
  } catch (e) {
    setChip("ds-status", false, "", "Сервер: offline");
    setChip("ollama-status", false, "", "—");
    toast(String(e.message || e));
  }
}

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

  if (st === "running") startPoll();
  if (st === "done" || st === "error") {
    stopPoll();
    loadFiles();
    refreshProgressOnly();
  }
}

async function refreshProgressOnly() {
  try {
    const p = await api("/api/progress?smoke_loaded=" + (smokeLoaded ? "1" : "0"));
    applyProgress(p);
  } catch (_) { /* ignore */ }
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const st = await api("/api/run/status");
      renderRun(st);
    } catch (e) {
      el("run-report").textContent = String(e.message || e);
      toast(String(e.message || e));
    }
  }, 1500);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function loadFiles() {
  const j = await api("/api/run/files");
  const files = j.files || [];
  el("file-list").innerHTML = files.map(f =>
    `<button type="button" class="btn file-btn" data-path="${f.path}">${f.path} <span class="muted">${f.chars}</span></button>`
  ).join("") || "<p class='muted'>нет .luau</p>";
  el("file-list").querySelectorAll(".file-btn").forEach(btn => {
    btn.onclick = async () => {
      el("file-list").querySelectorAll(".file-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const path = btn.getAttribute("data-path");
      el("file-view").textContent = "…";
      const file = await api("/api/run/file?path=" + encodeURIComponent(path));
      lastFileContent = file.content || "";
      el("file-view").textContent = lastFileContent;
      el("btn-copy-code").disabled = !lastFileContent;
    };
  });
  if (files[0]) {
    const first = el("file-list").querySelector(".file-btn");
    if (first) first.click();
  }
}

el("btn-copy-code").onclick = async () => {
  if (!lastFileContent) return;
  try {
    await navigator.clipboard.writeText(lastFileContent);
    toast("Скопировано в буфер");
  } catch (_) {
    toast("Не удалось скопировать");
  }
};

el("btn-activate").onclick = async () => {
  try {
    const j = await api("/api/activate", { method: "POST", body: JSON.stringify({ project: "game1" }) });
    el("compress-out").textContent = "activated: " + JSON.stringify(j);
    await refresh();
  } catch (e) {
    toast(String(e.message || e));
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

const smokeAnswers = {};

function setSmokeAnswer(qid, value) {
  smokeAnswers[qid] = value;
  const row = el("smoke").querySelector(`.q[data-id="${qid}"]`);
  if (!row) return;
  row.querySelectorAll(".yn-btn").forEach(b => {
    const on = b.getAttribute("data-v") === value;
    b.classList.toggle("active", on);
  });
  updateSmokeProgress();
}

function updateSmokeProgress() {
  const total = smokeQs.length;
  let answered = 0;
  for (const q of smokeQs) {
    if (smokeAnswers[q.id] === "y" || smokeAnswers[q.id] === "n") answered += 1;
  }
  const pct = total ? Math.round((answered / total) * 100) : 0;
  el("smoke-bar").style.setProperty("--pct", pct + "%");
  el("smoke-count").textContent = `${answered}/${total} ответов`;
  el("btn-smoke-submit").disabled = !(total > 0 && answered === total);
  refreshProgressOnly();
}

el("btn-smoke-load").onclick = async () => {
  try {
    const j = await api("/api/smoke/questions?project=game1");
    smokeQs = j.questions || [];
    smokeLoaded = smokeQs.length > 0;
    Object.keys(smokeAnswers).forEach(k => delete smokeAnswers[k]);
    el("smoke").innerHTML = smokeQs.map((q, i) => `
      <div class="q" data-id="${q.id}">
        <div class="q-prompt"><span class="muted">${String(i + 1).padStart(2, "0")}</span> ${q.prompt}</div>
        <div class="yn">
          <button type="button" class="yn-btn y" data-v="y">Y</button>
          <button type="button" class="yn-btn n" data-v="n">N</button>
        </div>
      </div>`).join("") || "<p class='muted'>нет вопросов</p>";
    el("smoke").querySelectorAll(".yn-btn").forEach(btn => {
      btn.onclick = () => {
        const row = btn.closest(".q");
        setSmokeAnswer(row.getAttribute("data-id"), btn.getAttribute("data-v"));
      };
    });
    updateSmokeProgress();
    toast("Нажми Y или N у каждого пункта. Best можно отметить N.");
  } catch (e) {
    toast(String(e.message || e));
  }
};

el("btn-smoke-submit").onclick = async () => {
  const answers = {};
  let yes = 0, total = 0;
  for (const q of smokeQs) {
    const v = smokeAnswers[q.id];
    if (v !== "y" && v !== "n") {
      toast("Отметь все пункты Y или N");
      return;
    }
    answers[q.id] = { answer: v, prompt: q.prompt };
    total += 1;
    if (v === "y") yes += 1;
  }
  const notes = (el("smoke-notes") && el("smoke-notes").value) || "";
  const overall_ok = total > 0 && yes / total >= 0.7;
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
    el("smoke-out").textContent = JSON.stringify(j, null, 2);
    toast(overall_ok ? "Smoke сохранён · skills promote" : "Smoke сохранён (ниже 70% — без promote)");
    await refresh();
  } catch (e) {
    toast(String(e.message || e));
  }
};

refresh().catch(e => toast(String(e.message || e)));
