async function api(path, opts) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

function el(id) { return document.getElementById(id); }

async function refresh() {
  const s = await api("/api/status");
  el("ds-status").textContent = s.deepseek ? "DeepSeek: OK (key)" : "DeepSeek: нет ключа → heuristic";
  el("raw-count").textContent = String(s.raw_count);
  el("projects").innerHTML = (s.projects || []).map(p =>
    `<div class="card"><strong>${p.id}</strong> — ${p.title || ""} · luau ${p.luau_files || 0} · ${p.status || ""}</div>`
  ).join("") || "<p class='muted'>нет проектов</p>";
  el("compact").innerHTML = (s.compact || []).map(c =>
    `<div class="card"><strong>${c.id}</strong> · ${c.chars} chars · promoted=${c.promoted}</div>`
  ).join("");
}

el("btn-activate").onclick = async () => {
  const j = await api("/api/activate", { method: "POST", body: JSON.stringify({ project: "game1" }) });
  el("compress-out").textContent = JSON.stringify(j, null, 2);
};

el("btn-compress").onclick = async () => {
  const raw_id = el("raw-id").value.trim();
  el("compress-out").textContent = "…";
  try {
    const j = await api("/api/compress", { method: "POST", body: JSON.stringify({ raw_id, max_chars: 1200 }) });
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
    el("tz-out").textContent = j.preview || JSON.stringify(j, null, 2);
  } catch (e) {
    el("tz-out").textContent = String(e);
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
  const body = {
    project: "game1",
    answers,
    overall_ok,
    promote_skills: overall_ok ? ["forge-player-attrs", "forge-luau-touch"] : [],
  };
  const j = await api("/api/smoke/submit", { method: "POST", body: JSON.stringify(body) });
  el("smoke-out").textContent = JSON.stringify(j, null, 2);
  await refresh();
};

refresh().catch(e => { el("ds-status").textContent = String(e); });
