(() => {
  const STORAGE_KEY = "org-study-progress-v1";
  const data = window.ORG_DATA;

  const state = {
    view: "home",
    day: 1,
    progress: loadProgress(),
    game: null,
  };

  function loadProgress() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch (_) {}
    return {
      xp: 0,
      read: {},
      gamesPlayed: {},
      bestExam: 0,
    };
  }

  function saveProgress() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.progress));
    renderProgressChrome();
  }

  function $(sel, root = document) {
    return root.querySelector(sel);
  }

  function $all(sel, root = document) {
    return [...root.querySelectorAll(sel)];
  }

  function shuffle(arr) {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function dayProgress(dayId) {
    const day = data.days.find((d) => d.id === dayId);
    if (!day) return 0;
    const readCount = day.topics.filter((t) => state.progress.read[t.id]).length;
    return Math.round((readCount / day.topics.length) * 100);
  }

  function overallProgress() {
    const allTopics = data.days.flatMap((d) => d.topics);
    const read = allTopics.filter((t) => state.progress.read[t.id]).length;
    const topicPct = read / allTopics.length;
    const games = ["flash", "quiz", "match", "timeline", "power", "exam"];
    const played = games.filter((g) => state.progress.gamesPlayed[g]).length;
    const gamesPct = played / games.length;
    return Math.round((topicPct * 0.6 + gamesPct * 0.4) * 100);
  }

  function addXp(n, gameId) {
    state.progress.xp += n;
    if (gameId) state.progress.gamesPlayed[gameId] = true;
    saveProgress();
  }

  function setView(view) {
    state.view = view;
    $all(".view").forEach((el) => el.classList.toggle("active", el.id === `view-${view}`));
    $all("[data-nav]").forEach((btn) => btn.classList.toggle("active", btn.dataset.nav === view));
    if (view === "study") renderTopics();
    if (view === "days") renderDays();
    if (view === "home") renderHome();
    if (view === "games") showGameMenu();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderProgressChrome() {
    $("#xpPill").textContent = `${state.progress.xp} XP · ${overallProgress()}%`;
  }

  function renderHome() {
    $("#homeProgress").innerHTML = data.days
      .map(
        (d) => `
      <div class="day-ring">
        <span class="pct" style="color:${d.color}">${dayProgress(d.id)}%</span>
        <small>День ${d.id}</small>
      </div>`
      )
      .join("");

    $("#homeTips").innerHTML = data.examTips.map((t) => `<li>${t}</li>`).join("");
  }

  function renderDays() {
    $("#daysGrid").innerHTML = data.days
      .map((d) => {
        const pct = dayProgress(d.id);
        return `
        <article class="card">
          <div class="meta"><span style="color:${d.color}">День ${d.id}</span><span>${pct}%</span></div>
          <div class="bar"><span style="width:${pct}%;background:linear-gradient(90deg,${d.color},#2a9d8f)"></span></div>
          <h3>${d.title}</h3>
          <p>${d.goal}</p>
          <button class="btn btn-primary" type="button" data-open-day="${d.id}">Открыть темы</button>
        </article>`;
      })
      .join("");
  }

  function renderTopics() {
    const day = data.days.find((d) => d.id === state.day);
    $("#studyTitle").textContent = `День ${day.id}: ${day.title}`;
    $("#studyGoal").textContent = day.goal;

    $all("[data-day-filter]").forEach((b) => {
      b.className = b.dataset.dayFilter == state.day ? "btn btn-accent" : "btn btn-ghost";
    });

    $("#topicsList").innerHTML = day.topics
      .map((t) => {
        const done = !!state.progress.read[t.id];
        return `
        <details class="topic" ${done ? "open" : ""}>
          <summary>${t.title} ${done ? "✓" : ""}</summary>
          <div class="topic-body">
            <p class="summary">${t.summary}</p>
            <ul>${t.points.map((p) => `<li>${p}</li>`).join("")}</ul>
            <div class="mark-row">
              <button class="btn ${done ? "btn-secondary" : "btn-accent"}" type="button" data-mark="${t.id}">
                ${done ? "Прочитано" : "Отметить прочитанным"}
              </button>
            </div>
          </div>
        </details>`;
      })
      .join("");
  }

  function showGameMenu() {
    const menu = $("#gameMenu");
    const stage = $("#gameStage");
    if (menu) menu.classList.remove("hidden");
    if (stage) stage.classList.add("hidden");
    state.game = null;
  }

  function openGame(type) {
    const menu = $("#gameMenu");
    const stage = $("#gameStage");
    if (menu) menu.classList.add("hidden");
    if (stage) stage.classList.remove("hidden");
    $("#gameFeedback")?.classList.add("hidden");
    const runners = {
      flash: runFlash,
      quiz: () => runQuiz(false),
      match: runMatch,
      timeline: runTimeline,
      power: runPower,
      exam: () => runQuiz(true),
    };
    state.game = runners[type]();
    $("#gameAction").textContent = state.game.actionLabel || "Дальше";
    $("#gameScore").textContent = state.game.scoreLabel();
  }

  function runFlash() {
    const cards = shuffle(data.flashcards);
    let i = 0;
    let flipped = false;
    let known = 0;
    const root = $("#gameRoot");

    function paint() {
      const c = cards[i];
      root.innerHTML = `
        <div class="flash-card" id="flashCard">
          <div>
            <div class="label">${flipped ? "Определение" : "Термин"} · ${i + 1}/${cards.length}</div>
            <div class="text">${flipped ? c.a : c.q}</div>
          </div>
        </div>
        <div class="hero-actions" style="margin-top:1rem;justify-content:center">
          <button class="btn btn-secondary" type="button" id="flashFlip">Перевернуть</button>
          <button class="btn btn-accent" type="button" id="flashKnow">Знаю</button>
        </div>`;
      $("#flashFlip").onclick = () => {
        flipped = !flipped;
        paint();
      };
      $("#flashKnow").onclick = () => {
        known++;
        next();
      };
      $("#flashCard").onclick = () => {
        flipped = !flipped;
        paint();
      };
    }

    function next() {
      flipped = false;
      i++;
      if (i >= cards.length) {
        root.innerHTML = `<h3 class="quiz-q">Готово! Узнано карточек: ${known}/${cards.length}</h3>`;
        addXp(8, "flash");
        showFeedback(true, "+8 XP за карточки");
        return;
      }
      paint();
      $("#gameScore").textContent = `${known} знаю`;
    }

    paint();
    return {
      actionLabel: "Пропустить",
      scoreLabel: () => `${known} знаю`,
      next: () => next(),
    };
  }

  function runQuiz(examMode) {
    const pool = examMode ? shuffle(data.quiz).slice(0, 15) : shuffle(data.quiz).slice(0, 10);
    let i = 0;
    let score = 0;
    let locked = false;
    const root = $("#gameRoot");

    function paint() {
      locked = false;
      const item = pool[i];
      root.innerHTML = `
        <div class="meta" style="margin-bottom:0.75rem">
          <span>${examMode ? "Зачёт" : "Викторина"}</span>
          <span>${i + 1}/${pool.length}</span>
        </div>
        <div class="quiz-q">${item.q}</div>
        <div class="options">
          ${item.options
            .map(
              (opt, idx) =>
                `<button class="option" type="button" data-opt="${idx}">${opt}</button>`
            )
            .join("")}
        </div>`;
      $all(".option", root).forEach((btn) => {
        btn.onclick = () => {
          if (locked) return;
          locked = true;
          const chosen = Number(btn.dataset.opt);
          const ok = chosen === item.correct;
          if (ok) score++;
          $all(".option", root).forEach((b) => {
            const n = Number(b.dataset.opt);
            if (n === item.correct) b.classList.add("correct");
            if (n === chosen && !ok) b.classList.add("wrong");
          });
          $("#gameScore").textContent = `${score}/${pool.length}`;
          showFeedback(ok, ok ? "Верно" : `Правильно: ${item.options[item.correct]}`);
        };
      });
    }

    function finish() {
      const pct = Math.round((score / pool.length) * 100);
      root.innerHTML = `
        <h3 class="quiz-q">Результат: ${score}/${pool.length} (${pct}%)</h3>
        <p style="color:var(--ink-soft);margin-bottom:1rem">${
          pct >= 80 ? "Отлично — уровень зачёта." : "Повтори слабые темы и попробуй ещё раз."
        }</p>
        <button class="btn btn-primary" type="button" data-nav="study">К темам</button>`;
      if (examMode) {
        state.progress.bestExam = Math.max(state.progress.bestExam || 0, pct);
        addXp(25, "exam");
      } else {
        addXp(12, "quiz");
      }
      showFeedback(pct >= 80, examMode ? `Зачёт: ${pct}% · +25 XP` : `Викторина: ${pct}% · +12 XP`);
    }

    paint();
    return {
      actionLabel: "Следующий",
      scoreLabel: () => `${score}/${pool.length}`,
      next: () => {
        if (i >= pool.length - 1) return finish();
        i++;
        $("#gameFeedback").classList.add("hidden");
        paint();
      },
    };
  }

  function runMatch() {
    const pairs = shuffle(data.matchPairs).slice(0, 6);
    const left = shuffle(pairs.map((p, idx) => ({ idx, text: p[0], side: "L" })));
    const right = shuffle(pairs.map((p, idx) => ({ idx, text: p[1], side: "R" })));
    let selected = null;
    let matched = 0;
    const root = $("#gameRoot");

    function paint() {
      root.innerHTML = `
        <p style="margin-bottom:0.75rem;color:var(--ink-soft)">Выбери термин и его определение.</p>
        <div class="match-board">
          <div class="options">${left
            .map(
              (item) =>
                `<button class="match-item" type="button" data-side="L" data-idx="${item.idx}">${item.text}</button>`
            )
            .join("")}</div>
          <div class="options">${right
            .map(
              (item) =>
                `<button class="match-item" type="button" data-side="R" data-idx="${item.idx}">${item.text}</button>`
            )
            .join("")}</div>
        </div>`;

      $all(".match-item", root).forEach((btn) => {
        if (btn.classList.contains("done")) return;
        btn.onclick = () => onPick(btn);
      });

      // restore done state visually after repaint isn't needed first time
      markDone();
    }

    const doneSet = new Set();

    function markDone() {
      $all(".match-item", root).forEach((btn) => {
        if (doneSet.has(`${btn.dataset.side}-${btn.dataset.idx}`)) btn.classList.add("done");
      });
    }

    function onPick(btn) {
      if (btn.classList.contains("done")) return;
      const pick = { side: btn.dataset.side, idx: Number(btn.dataset.idx), el: btn };
      if (!selected) {
        selected = pick;
        btn.classList.add("selected");
        return;
      }
      if (selected.side === pick.side) {
        selected.el.classList.remove("selected");
        selected = pick;
        btn.classList.add("selected");
        return;
      }
      if (selected.idx === pick.idx) {
        doneSet.add(`${selected.side}-${selected.idx}`);
        doneSet.add(`${pick.side}-${pick.idx}`);
        matched++;
        selected.el.classList.remove("selected");
        selected = null;
        markDone();
        $("#gameScore").textContent = `${matched}/6`;
        showFeedback(true, "Пара найдена");
        if (matched === 6) {
          addXp(10, "match");
          showFeedback(true, "Все пары собраны · +10 XP");
        }
      } else {
        selected.el.classList.remove("selected");
        selected = null;
        showFeedback(false, "Не пара, попробуй ещё");
      }
    }

    paint();
    return {
      actionLabel: "Подсказка",
      scoreLabel: () => `${matched}/6`,
      next: () => showFeedback(true, "Ищи однокоренные смыслы: орган ↔ функция"),
    };
  }

  function runTimeline() {
    let items = shuffle(data.timeline);
    const root = $("#gameRoot");

    function paint() {
      root.innerHTML = `
        <p style="margin-bottom:0.75rem;color:var(--ink-soft)">Перетасуй кнопками ↑ ↓ в правильном хронологическом порядке.</p>
        <div class="timeline-list" id="timelineList">
          ${items
            .map(
              (it, idx) => `
            <div class="timeline-item" data-id="${it.id}">
              <div class="handle">${idx + 1}</div>
              <div style="flex:1">
                <strong>${it.label}</strong>
                <span>${it.year}</span>
              </div>
              <button class="btn btn-ghost" type="button" data-up="${idx}">↑</button>
              <button class="btn btn-ghost" type="button" data-down="${idx}">↓</button>
            </div>`
            )
            .join("")}
        </div>`;
      $all("[data-up]", root).forEach((b) => {
        b.onclick = () => move(Number(b.dataset.up), -1);
      });
      $all("[data-down]", root).forEach((b) => {
        b.onclick = () => move(Number(b.dataset.down), 1);
      });
    }

    function move(idx, dir) {
      const j = idx + dir;
      if (j < 0 || j >= items.length) return;
      [items[idx], items[j]] = [items[j], items[idx]];
      paint();
    }

    paint();
    return {
      actionLabel: "Проверить",
      scoreLabel: () => "порядок",
      next: () => {
        const ok = items.every((it, idx) => it.id === data.timeline[idx].id);
        if (ok) {
          addXp(10, "timeline");
          showFeedback(true, "Хронология верна · +10 XP");
        } else {
          showFeedback(false, "Ещё не точно. Киевская Русь должна быть первой.");
        }
      },
    };
  }

  function runPower() {
    const slots = [
      { id: "head", title: "Глава государства" },
      { id: "leg", title: "Законодательная власть" },
      { id: "exec", title: "Исполнительная власть" },
      { id: "jud", title: "Судебная власть" },
      { id: "reg", title: "Региональный уровень" },
      { id: "msu", title: "Местный уровень" },
    ];
    const placed = {};
    const remaining = shuffle(data.powerMap);
    const root = $("#gameRoot");

    function paint() {
      root.innerHTML = `
        <div class="power-grid">
          ${slots
            .map((s) => {
              const item = Object.values(placed).find((p) => p.slot === s.id);
              return `<div class="slot" data-slot="${s.id}">
                <h4>${s.title}</h4>
                <div>${item ? `<strong>${item.label}</strong><div style="font-size:0.85rem;color:var(--ink-soft)">${item.hint}</div>` : "—"}</div>
              </div>`;
            })
            .join("")}
        </div>
        <div class="chips" id="powerChips">
          ${remaining
            .filter((r) => !placed[r.id])
            .map((r) => `<button class="chip" type="button" data-chip="${r.id}">${r.label}</button>`)
            .join("")}
        </div>
        <p style="margin-top:0.75rem;color:var(--ink-soft);font-size:0.9rem">Сначала выбери орган, затем кликни по слоту.</p>`;

      let selected = null;
      $all("[data-chip]", root).forEach((btn) => {
        btn.onclick = () => {
          selected = btn.dataset.chip;
          $all("[data-chip]", root).forEach((b) => (b.style.outline = ""));
          btn.style.outline = "3px solid #2a9d8f";
        };
      });
      $all(".slot", root).forEach((slot) => {
        slot.onclick = () => {
          if (!selected) return;
          const item = data.powerMap.find((p) => p.id === selected);
          placed[item.id] = { ...item, slot: slot.dataset.slot };
          selected = null;
          paint();
          $("#gameScore").textContent = `${Object.keys(placed).length}/6`;
        };
      });
    }

    paint();
    return {
      actionLabel: "Проверить",
      scoreLabel: () => `${Object.keys(placed).length}/6`,
      next: () => {
        const ok = data.powerMap.every((p) => placed[p.id] && placed[p.id].slot === p.slot);
        if (ok) {
          addXp(14, "power");
          showFeedback(true, "Схема власти собрана · +14 XP");
        } else {
          showFeedback(false, "Есть ошибки. МСУ — отдельно от госорганов.");
        }
      },
    };
  }

  function showFeedback(ok, text) {
    const el = $("#gameFeedback");
    el.classList.remove("hidden", "ok", "bad");
    el.classList.add(ok ? "ok" : "bad");
    el.textContent = text;
  }

  function bind() {
    document.body.addEventListener("click", (e) => {
      const nav = e.target.closest("[data-nav]");
      if (nav) {
        e.preventDefault();
        const view = nav.dataset.nav;
        if (view === "exam") setView("exam");
        else if (view === "games" || view === "games") setView("games");
        else setView(view);
      }

      const openDay = e.target.closest("[data-open-day]");
      if (openDay) {
        state.day = Number(openDay.dataset.openDay);
        setView("study");
      }

      const dayFilter = e.target.closest("[data-day-filter]");
      if (dayFilter) {
        state.day = Number(dayFilter.dataset.dayFilter);
        renderTopics();
      }

      const mark = e.target.closest("[data-mark]");
      if (mark) {
        const id = mark.dataset.mark;
        state.progress.read[id] = true;
        saveProgress();
        renderTopics();
        renderDays();
      }

      const gameCard = e.target.closest("[data-game]");
      if (gameCard) {
        const type = gameCard.dataset.game;
        if (type === "exam") {
          setView("exam");
          openExam();
        } else {
          setView("games");
          openGame(type);
        }
      }
    });

    $("#backToGames").onclick = showGameMenu;
    $("#gameAction").onclick = () => state.game && state.game.next();
    $("#startExam").onclick = openExam;

    // Mobile quick nav inject
    const mobile = document.createElement("div");
    mobile.className = "wrap mobile-nav";
    mobile.innerHTML = `
      <button type="button" data-nav="home">Главная</button>
      <button type="button" data-nav="days">3 дня</button>
      <button type="button" data-nav="study">Темы</button>
      <button type="button" data-nav="games">Игры</button>
      <button type="button" data-nav="exam">Зачёт</button>`;
    $(".topnav").appendChild(mobile);
  }

  function openExam() {
    setView("exam");
    $("#gameMenu")?.classList.add("hidden");
    // reuse quiz engine inside exam stage
    const stage = $("#examStage");
    stage.innerHTML = `<div id="examRoot"></div><div id="examFeedback" class="feedback hidden"></div>
      <div style="margin-top:1rem"><button class="btn btn-accent" type="button" id="examNext">Следующий</button></div>`;

    // Temporarily map roots
    const originalRoot = $("#gameRoot");
    const originalFeedback = $("#gameFeedback");
    const originalScore = $("#gameScore");

    // Create shim elements expected by runQuiz via IDs used in games view — rewrite exam inline
    const pool = shuffle(data.quiz).slice(0, 15);
    let i = 0;
    let score = 0;
    let locked = false;
    const root = $("#examRoot");
    const feedback = $("#examFeedback");

    function showFb(ok, text) {
      feedback.classList.remove("hidden", "ok", "bad");
      feedback.classList.add(ok ? "ok" : "bad");
      feedback.textContent = text;
    }

    function paint() {
      locked = false;
      const item = pool[i];
      root.innerHTML = `
        <div class="meta" style="margin-bottom:0.75rem"><span>Пробный зачёт</span><span>${i + 1}/15 · ${score} верно</span></div>
        <div class="quiz-q">${item.q}</div>
        <div class="options">${item.options
          .map((opt, idx) => `<button class="option" type="button" data-opt="${idx}">${opt}</button>`)
          .join("")}</div>`;
      $all(".option", root).forEach((btn) => {
        btn.onclick = () => {
          if (locked) return;
          locked = true;
          const chosen = Number(btn.dataset.opt);
          const ok = chosen === item.correct;
          if (ok) score++;
          $all(".option", root).forEach((b) => {
            const n = Number(b.dataset.opt);
            if (n === item.correct) b.classList.add("correct");
            if (n === chosen && !ok) b.classList.add("wrong");
          });
          showFb(ok, ok ? "Верно" : `Ответ: ${item.options[item.correct]}`);
        };
      });
    }

    $("#examNext").onclick = () => {
      if (i >= pool.length - 1) {
        const pct = Math.round((score / pool.length) * 100);
        state.progress.bestExam = Math.max(state.progress.bestExam || 0, pct);
        addXp(25, "exam");
        root.innerHTML = `<h3 class="quiz-q">Итог зачёта: ${score}/15 (${pct}%)</h3>
          <p style="color:var(--ink-soft)">${pct >= 80 ? "Можно идти на зачёт." : "Вернись к темам дня 1–2 и повтори игры."}</p>`;
        showFb(pct >= 80, `Лучший результат сохранён: ${state.progress.bestExam}%`);
        return;
      }
      i++;
      feedback.classList.add("hidden");
      paint();
    };

    paint();
    void originalRoot;
    void originalFeedback;
    void originalScore;
  }

  // Fix CSS typo for games grid on mobile via JS class assurance
  bind();
  renderProgressChrome();
  renderHome();
  renderDays();
  renderTopics();
})();
