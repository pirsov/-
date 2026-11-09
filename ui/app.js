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
let runStartedAt = null;
let timerTick = null;
let smokeQs = [];
let smokeLoaded = false;
let smokeAnswers = {};
let lastFileContent = "";
let focusStage = 1;
let lastProgress = null;

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
  focusStage = Math.max(1, Math.min(5, Number(n) || 1));
  document.querySelectorAll(".panel[data-stage]").forEach(panel => {
    const id = Number(panel.getAttribute("data-stage"));
    panel.classList.toggle("focus", id === focusStage);
  });
  if (scroll) {
    const panel = document.getElementById("panel-" + focusStage);
    if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
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
  el("counts").textContent =
    `TZ ${c.tz_tasks || 0} · Luau ${c.luau_files || 0} · skills ${c.compact_skills || 0}`;

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
  if (st === "running") startPoll();
  if (st === "done" || st === "error") {
    stopPoll();
    loadFiles();
    refreshProgressOnly();
  }
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try { renderRun(await api("/api/run/status")); }
    catch (e) { toast(String(e.message || e)); }
  }, 1500);
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
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
      const file = await api("/api/run/file?path=" + encodeURIComponent(btn.getAttribute("data-path")));
      lastFileContent = file.content || "";
      el("file-view").textContent = lastFileContent;
      el("btn-copy-code").disabled = !lastFileContent;
    };
  });
  const first = el("file-list").querySelector(".file-btn");
  if (first) first.click();
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
        const qid = btn.closest(".q").getAttribute("data-id");
        smokeAnswers[qid] = btn.getAttribute("data-v");
        btn.closest(".yn").querySelectorAll(".yn-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        updateSmokeProgress();
      };
    });
    updateSmokeProgress();
    toast("Отметь Y/N. Best можно N.");
  } catch (e) { toast(String(e.message || e)); }
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
  const overall_ok = total > 0 && yes / total >= 0.7;
  try {
    const j = await api("/api/smoke/submit", {
      method: "POST",
      body: JSON.stringify({
        project: "game1",
        answers,
        notes: el("smoke-notes").value || "",
        overall_ok,
        promote_skills: overall_ok
          ? ["forge-player-attrs", "forge-luau-touch", "forge-ui-modern", "forge-ui-animation"]
          : [],
      }),
    });
    el("smoke-out").textContent = JSON.stringify(j, null, 2);
    toast(overall_ok ? "Smoke сохранён · promote" : "Smoke сохранён");
    await refresh();
  } catch (e) { toast(String(e.message || e)); }
};

refresh().then(() => {
  if (lastProgress) setFocus(lastProgress.stage || 1, { scroll: false });
}).catch(e => toast(String(e.message || e)));
