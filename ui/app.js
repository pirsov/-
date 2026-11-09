async function api(path, opts) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText || JSON.stringify(j));
  return j;
}

function el(id) { return document.getElementById(id); }

let pollTimer = null;

function applyStage(progress) {
  const unlocked = (progress && progress.unlocked) || { "1": true };
  const stage = (progress && progress.stage) || 1;
  const labels = (progress && progress.labels) || {};
  el("stage-rail").innerHTML = [1, 2, 3, 4, 5].map(n => {
    const on = !!unlocked[String(n)];
    const cur = n === stage;
    return `<span class="stage-dot ${on ? "on" : ""} ${cur ? "cur" : ""}">${n}. ${labels[n] || ""}</span>`;
  }).join("");
  document.querySelectorAll(".panel[data-stage]").forEach(panel => {
    const n = panel.getAttribute("data-stage");
    const on = !!unlocked[n];
    panel.classList.toggle("locked", !on);
    panel.querySelectorAll("button, textarea, input").forEach(ctrl => {
      if (!on) ctrl.setAttribute("disabled", "disabled");
      else ctrl.removeAttribute("disabled");
    });
  });
}

async function refresh() {
  const s = await api("/api/status");
  el("ds-status").textContent = s.deepseek ? "DeepSeek: OK (key)" : "DeepSeek: нет ключа (TZ fallback)";
  el("raw-count").textContent = String(s.raw_count);
  el("projects").innerHTML = (s.projects || []).map(p =>
    `<div class="card"><strong>${p.id}</strong> — ${p.title || ""} · luau ${p.luau_files || 0}</div>`
  ).join("") || "<p class='muted'>нет проектов</p>";
  el("compact").innerHTML = (s.compact || []).map(c =>
    `<div class="card"><strong>${c.id}</strong> · ${c.chars}c · promoted=${c.promoted}</div>`
  ).join("");
  applyStage(s.progress);
  if (s.run) renderRun(s.run);
}

function renderRun(run) {
  const st = run.status || "idle";
  el("run-status").textContent = st + (run.exit_code != null ? ` · exit ${run.exit_code}` : "");
  el("run-status").className = "pill " + st;
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
  if (run.log_tail) el("run-log").textContent = run.log_tail;
  if (st === "running") startPoll();
  if (st === "done" || st === "error") {
    stopPoll();
    loadFiles();
    refresh();
  }
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const st = await api("/api/run/status");
      renderRun(st);
      if (st.log_tail) {
        const box = el("run-log");
        const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        box.textContent = st.log_tail;
        if (atBottom) box.scrollTop = box.scrollHeight;
      }
    } catch (e) {
      el("run-report").textContent = String(e);
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
    `<button type="button" class="file-btn" data-path="${f.path}">${f.path} <span class="muted">${f.chars}</span></button>`
  ).join("") || "<p class='muted'>нет .luau</p>";
  el("file-list").querySelectorAll(".file-btn").forEach(btn => {
    btn.onclick = async () => {
      const path = btn.getAttribute("data-path");
      el("file-view").textContent = "…";
      const file = await api("/api/run/file?path=" + encodeURIComponent(path));
      el("file-view").textContent = file.content || "";
    };
  });
  if (files[0]) {
    const file = await api("/api/run/file?path=" + encodeURIComponent(files[0].path));
    el("file-view").textContent = file.content || "";
  }
}

el("btn-activate").onclick = async () => {
  const j = await api("/api/activate", { method: "POST", body: JSON.stringify({ project: "game1" }) });
  el("compress-out").textContent = "activated: " + JSON.stringify(j);
  await refresh();
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
    el("compress-out").textContent = String(e);
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
    el("tz-out").textContent = String(e);
  }
};

el("btn-run").onclick = async () => {
  el("run-report").textContent = "starting…";
  el("run-log").textContent = "";
  el("file-view").textContent = "";
  el("file-list").innerHTML = "";
  try {
    const j = await api("/api/run/start", {
      method: "POST",
      body: JSON.stringify({ sleep: 0, hitl: "y" }),
    });
    renderRun(j);
    startPoll();
  } catch (e) {
    el("run-report").textContent = String(e);
  }
};

let smokeQs = [];
el("btn-smoke-load").onclick = async () => {
  const j = await api("/api/smoke/questions?project=game1");
  smokeQs = j.questions || [];
  el("smoke").innerHTML = smokeQs.map(q => `
    <div class="q" data-id="${q.id}">
      <div>${q.prompt}</div>
      <label><input type="radio" name="${q.id}" value="y" /> y</label>
      <label><input type="radio" name="${q.id}" value="n" /> n</label>
    </div>`).join("");
};

el("btn-smoke-submit").onclick = async () => {
  const answers = {};
  let yes = 0, total = 0;
  for (const q of smokeQs) {
    const picked = document.querySelector(`input[name="${q.id}"]:checked`);
    const v = picked ? picked.value : "n";
    answers[q.id] = { answer: v, prompt: q.prompt };
    total += 1;
    if (v === "y") yes += 1;
  }
  const overall_ok = total > 0 && yes / total >= 0.7;
  const j = await api("/api/smoke/submit", {
    method: "POST",
    body: JSON.stringify({
      project: "game1",
      answers,
      overall_ok,
      promote_skills: overall_ok
        ? ["forge-player-attrs", "forge-luau-touch", "forge-ui-modern", "forge-ui-animation"]
        : [],
    }),
  });
  el("smoke-out").textContent = JSON.stringify(j, null, 2);
  await refresh();
};

refresh().catch(e => { el("ds-status").textContent = String(e); });
