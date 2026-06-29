/* G4Studio landing — interactions
   The signature piece is the fall canvas: cartoon hardware rains from the
   playful sky and crystallizes into a glowing grid of SO-101 data. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const rand = (a, b) => a + Math.random() * (b - a);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------- nav scroll state ---------------- */
  const nav = $("#nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 24);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* ---------------- scroll reveal ---------------- */
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
  $$(".reveal").forEach((el) => io.observe(el));

  /* ---------------- count-up helper ---------------- */
  function countUp(el, to, dur, dec, suffix) {
    const start = performance.now();
    const fmt = (v) => (dec ? v.toFixed(dec) : Math.round(v).toLocaleString()) + (suffix || "");
    function frame(t) {
      const p = clamp((t - start) / dur, 0, 1);
      const e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(to * e);
      if (p < 1) requestAnimationFrame(frame);
      else el.textContent = fmt(to);
    }
    requestAnimationFrame(frame);
  }
  const statIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const el = e.target, to = parseFloat(el.dataset.count);
      countUp(el, to, 1500, el.dataset.dec ? +el.dataset.dec : 0, el.dataset.suffix || "");
      statIO.unobserve(el);
    });
  }, { threshold: 0.5 });
  $$("[data-count]").forEach((el) => statIO.observe(el));

  /* ---------------- hero parallax ---------------- */
  const floaties = $$(".floatie");
  if (!reduceMotion && window.matchMedia("(pointer:fine)").matches) {
    window.addEventListener("mousemove", (e) => {
      const cx = e.clientX / window.innerWidth - 0.5;
      const cy = e.clientY / window.innerHeight - 0.5;
      floaties.forEach((f) => {
        const d = +f.dataset.depth || 20;
        f.style.translate = `${-cx * d}px ${-cy * d}px`;
      });
    }, { passive: true });
  }

  /* ---------------- hero → studio ---------------- */
  $("#hero-go")?.addEventListener("click", () => {
    const v = $("#hero-input").value.trim();
    if (v) $("#demo-input").value = v;
    setTimeout(runStudio, 650);
  });

  /* =====================================================================
     STUDIO — scripted replay of a real Gemma-4 swarm run
     ===================================================================== */
  const hud = { time: $("#hud-time"), tps: $("#hud-tps"), parts: $("#hud-parts"), agents: $("#hud-agents") };
  const agentsBox = $("#agents"), feed = $("#stage-feed"), feedEmpty = $("#stage-empty");
  const mTokens = $("#m-tokens"), mStages = $("#m-stages");
  const resultCard = $("#studio-result"), resultTitle = $("#result-title"), resultSub = $("#result-sub");
  let studioRunning = false, studioTimers = [];

  const SCRIPT = {
    name: "Bolt Drop Derby", task: "so101_color_sort", skill: "sort + place", rounds: 3,
    director: { tps: 1910, ms: 690, tokens: 540 },
    builders: [
      { name: "Workcell", chips: [["platform", "table"], ["checkpoint", "2 bins"]], parts: 6, tps: 1840, ms: 96, tokens: 470 },
      { name: "Bolt spawner", chips: [["moving", "8 bolts/round"], ["hazard", "timer"]], parts: 8, tps: 1880, ms: 88, tokens: 520 },
      { name: "Scoring + juice", chips: [["checkpoint", "combo"], ["moving", "speed-up"]], parts: 4, tps: 1955, ms: 102, tokens: 430 },
      { name: "Win / lose logic", chips: [["platform", "reward shaping"], ["hazard", "fail @ miss×3"]], parts: 3, tps: 1798, ms: 110, tokens: 610 },
    ],
    playtest: { score: 9, fixes: 2, ms: 540, tokens: 360, verdict: "Bins reachable, bolts spawn in-reach, scoring reads cleanly." },
  };

  function clearStudio() {
    studioTimers.forEach(clearTimeout); studioTimers = [];
    agentsBox.innerHTML = ""; 
    $$(".stage-card", feed).forEach((n) => n.remove());
    hud.time.textContent = "0"; hud.tps.textContent = "0"; hud.parts.textContent = "0"; hud.agents.textContent = "0";
    mTokens.textContent = "0"; mStages.textContent = "0";
    resultCard.classList.remove("show");
    feedEmpty.style.display = "none";
  }
  const after = (ms, fn) => studioTimers.push(setTimeout(fn, ms));

  function addAgent(id, name, role, kind) {
    const d = document.createElement("div");
    d.className = "agent active" + (kind ? " " + kind : ""); d.id = "ag-" + id;
    d.innerHTML = `<div class="agent-top"><span class="agent-name">${name}</span><span class="agent-role">${role}</span></div>
      <div class="agent-stat"><span class="pulse"></span>working…</div>`;
    agentsBox.appendChild(d);
    hud.agents.textContent = agentsBox.children.length;
  }
  function doneAgent(id, html, kind) {
    const d = $("#ag-" + id); if (!d) return;
    d.classList.remove("active"); d.classList.add("done"); if (kind) d.classList.add(kind);
    d.querySelector(".agent-stat").innerHTML = html;
  }
  function addStage(name, chips, meta, vision) {
    const d = document.createElement("div");
    d.className = "stage-card" + (vision ? " vision" : "");
    const cs = chips.map(([k, t]) => `<span class="chip2 ${k}">${t}</span>`).join("");
    d.innerHTML = `<div class="sc-name">${name}</div>${cs ? `<div class="sc-chips">${cs}</div>` : ""}${meta ? `<div class="sc-meta">${meta}</div>` : ""}`;
    feed.appendChild(d); feed.scrollTop = feed.scrollHeight;
  }

  let tokAcc = 0, partAcc = 0;
  function bumpTokens(n) { tokAcc += n; mTokens.textContent = tokAcc.toLocaleString(); }
  function bumpParts(n) { partAcc += n; hud.parts.textContent = partAcc; }

  function runStudio() {
    if (studioRunning) return;
    studioRunning = true; clearStudio();
    tokAcc = 0; partAcc = 0;
    const go = $("#demo-go"); go.disabled = true; go.style.opacity = ".6";

    // running timer + jittery tok/s
    const t0 = performance.now();
    const tick = () => {
      if (!studioRunning) return;
      hud.time.textContent = Math.round(performance.now() - t0).toLocaleString();
      hud.tps.textContent = Math.round(rand(1780, 1960)).toLocaleString();
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);

    addAgent("dir", "Director", "design", "director");
    after(SCRIPT.director.ms, () => {
      bumpTokens(SCRIPT.director.tokens); mStages.textContent = SCRIPT.rounds + 1;
      doneAgent("dir", `“${SCRIPT.name}” · ${SCRIPT.skill} · <span class="tps">${SCRIPT.director.tps}</span> tok/s`, "director");
    });

    let t = SCRIPT.director.ms + 120;
    SCRIPT.builders.forEach((b, i) => {
      after(t, () => addAgent("b" + i, b.name, "builder"));
      after(t + b.ms + 260, () => {
        bumpTokens(b.tokens); bumpParts(b.parts);
        addStage(b.name, b.chips, `${b.tps} tok/s · ${b.ms} ms`);
        doneAgent("b" + i, `${b.parts} parts · <span class="tps">${b.tps}</span> tok/s · ${b.ms} ms`);
      });
      t += 480;
    });

    after(t, () => addAgent("pt", "Playtester", "vision", "vision"));
    after(t + SCRIPT.playtest.ms + 300, () => {
      bumpTokens(SCRIPT.playtest.tokens);
      doneAgent("pt", `saw it — <b style="color:var(--gold-600)">${SCRIPT.playtest.score}/10</b> · ${SCRIPT.playtest.fixes} auto-fixes`, "vision");
      addStage(`Playtester · ${SCRIPT.playtest.score}/10`, [["checkpoint", `${SCRIPT.playtest.fixes} fixes`]], SCRIPT.playtest.verdict, true);
    });

    after(t + SCRIPT.playtest.ms + 700, () => {
      studioRunning = false;
      const ms = Math.round(performance.now() - t0);
      hud.time.textContent = ms.toLocaleString();
      hud.tps.textContent = "1,900";
      resultTitle.textContent = `“${SCRIPT.name}” — built in ${ms.toLocaleString()} ms`;
      resultSub.innerHTML = `${agentsBox.children.length} agents · ${partAcc} objects · ${SCRIPT.skill} · ${tokAcc.toLocaleString()} tokens on Gemma-4 / Cerebras → <span class="mono">${SCRIPT.task}.jsonl</span>`;
      resultCard.classList.add("show");
      go.disabled = false; go.style.opacity = "1";
    });
  }

  $("#demo-go")?.addEventListener("click", runStudio);
  // auto-run once when the studio scrolls into view
  const studioIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { studioIO.disconnect(); after(400, runStudio); } });
  }, { threshold: 0.4 });
  if ($("#studio")) studioIO.observe($("#studio"));

  /* =====================================================================
     TRACE viewer — append JSONL-ish steps, color-coded subgoals
     ===================================================================== */
  const traceView = $("#trace-view");
  if (traceView) {
    const PHASES = ["reach", "reach", "grasp", "transport", "transport", "sort", "place"];
    let t = 41, ji = [6, 18, -42, 6, 0], grip = 1, pi = 0, score = 1240, combo = 6;
    const gScore = $("#g-score"), gCombo = $("#g-combo"), gTime = $("#g-time");
    function step() {
      const phase = PHASES[pi % PHASES.length];
      ji = ji.map((v, k) => clamp(v + rand(-8, 8), -110, 110) * (k < 3 ? 1 : 0.5));
      grip = (phase === "grasp" || phase === "transport" || phase === "sort") ? clamp(grip - 0.25, 0, 1) : clamp(grip + 0.3, 0, 1);
      const reward = phase === "place" ? "1.00" : (-rand(0.02, 0.3)).toFixed(2);
      const j = ji.map((v) => v.toFixed(1)).join(", ");
      const line = document.createElement("div");
      line.className = "ln";
      line.innerHTML = `{<span class="k">"t"</span>:<span class="n">${t}</span>, <span class="k">"joints"</span>:[<span class="n">${j}</span>], <span class="k">"grip"</span>:<span class="n">${grip.toFixed(2)}</span>, <span class="k">"r"</span>:<span class="n">${reward}</span>, <span class="k">"sg"</span>:<span class="g">"</span><span class="sg ${phase}">${phase}</span><span class="g">"</span>}`;
      traceView.appendChild(line);
      while (traceView.children.length > 11) traceView.removeChild(traceView.firstChild);
      t += Math.round(rand(2, 5)); pi++;
      if (phase === "place") { score += Math.round(rand(80, 160)); combo++; if (gScore) gScore.textContent = score.toLocaleString(); if (gCombo) gCombo.textContent = "x" + combo; }
      if (gTime) { const s = 42 + Math.floor(t / 10) % 60; gTime.textContent = "0:" + String(s % 60).padStart(2, "0"); }
    }
    for (let i = 0; i < 6; i++) step();
    if (!reduceMotion) setInterval(step, 850);
  }

  /* ---------------- game cube tween ---------------- */
  const cube = $("#g-cube");
  if (cube && !reduceMotion) {
    const path = [
      { x: 44, y: 30, c: "#5cc6f5,#2f86c9" }, // spawn
      { x: 58, y: 40, c: "#5cc6f5,#2f86c9" }, // reach
      { x: 60, y: 52, c: "#5cc6f5,#2f86c9" }, // grasp
      { x: 40, y: 46, c: "#5cc6f5,#2f86c9" }, // transport
      { x: 30, y: 60, c: "#5cc6f5,#2f86c9" }, // into blue bin
    ];
    let k = 0;
    setInterval(() => {
      k = (k + 1) % path.length;
      const p = path[k];
      cube.style.transition = "left .8s cubic-bezier(.4,0,.2,1), top .8s cubic-bezier(.4,0,.2,1), opacity .4s";
      cube.style.left = p.x + "%"; cube.style.top = p.y + "%";
      cube.style.opacity = k === 0 ? "0" : "1";
      cube.style.background = `linear-gradient(150deg,${p.c})`;
    }, 1000);
  }

  /* =====================================================================
     SHAPE YOUR DATA — pills drive the coverage bars
     ===================================================================== */
  const pills = $$("#skill-pills .skill-pill");
  const barRows = $$("#bars .bar-row");
  const shapeCode = $("#shape-code");
  const BASE = { grasp: 22, place: 18, sort: 9, stack: 7, insert: 4, transport: 14 };
  function recomputeBars() {
    const sel = pills.filter((p) => p.classList.contains("on")).map((p) => p.dataset.skill);
    const target = {};
    barRows.forEach((r) => {
      const sk = r.dataset.skill;
      const boosted = sel.includes(sk);
      const base = BASE[sk] || 8;
      // selected skills converge toward a high collected share; others lag
      const val = boosted ? clamp(base + 46 / Math.max(1, sel.length) + 22, 30, 96)
                          : clamp(base - 2, 3, 30);
      target[sk] = Math.round(val);
    });
    barRows.forEach((r) => {
      const sk = r.dataset.skill, v = target[sk];
      r.querySelector(".bar-fill").style.right = (100 - v) + "%";
      r.querySelector(".bv").textContent = v + "%";
      r.querySelector(".bar-fill").style.opacity = pills.find((p) => p.dataset.skill === sk)?.classList.contains("on") ? "1" : ".5";
    });
    if (shapeCode) shapeCode.textContent = (sel.length ? sel.slice(0, 3).join(" + ") : "balanced") + (sel.length > 3 ? " …" : "");
  }
  pills.forEach((p) => p.addEventListener("click", () => { p.classList.toggle("on"); recomputeBars(); }));
  // fill bars when they scroll into view
  const barIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { recomputeBars(); barIO.disconnect(); } });
  }, { threshold: 0.4 });
  if ($("#bars")) barIO.observe($("#bars"));

  /* =====================================================================
     HEATMAP — episodes/day, 52 weeks
     ===================================================================== */
  const heat = $("#heatmap");
  if (heat) {
    const weeks = 52, days = 7; let total = 0;
    const cells = [];
    for (let w = 0; w < weeks; w++) {
      for (let d = 0; d < days; d++) {
        // growth trend + weekly burstiness + weekend dips
        const trend = w / weeks;
        const burst = Math.sin(w / 3) * 0.25 + 0.6;
        const weekend = (d === 0 || d === 6) ? 0.55 : 1;
        let v = Math.random() * burst * weekend * (0.25 + trend);
        v = clamp(v, 0, 1);
        const eps = Math.round(v * 320 * (0.5 + trend));
        total += eps;
        const c = document.createElement("div");
        c.className = "heat-cell";
        const a = v < 0.12 ? 0.07 : v < 0.32 ? 0.3 : v < 0.55 ? 0.55 : v < 0.78 ? 0.8 : 1;
        c.style.background = a <= 0.07 ? "rgba(255,221,170,.07)" : (a >= 1 ? "#f0cf6e" : `rgba(226,174,64,${a})`);
        c.title = `${eps} episodes`;
        cells.push(c); heat.appendChild(c);
      }
    }
    const totalEl = $("#heat-total");
    if (totalEl) totalEl.textContent = total.toLocaleString() + " episodes this year";
  }

  /* =====================================================================
     FALL CANVAS — cartoon hardware falls and crystallizes into data
     ===================================================================== */
  const canvas = $("#fall-canvas");
  if (canvas) initFall(canvas);

  function initFall(canvas) {
    const ctx = canvas.getContext("2d");
    const SRC = ["bolt", "nut", "screw", "gear", "washer"].map((n) => "assets/" + n + ".png");
    const imgs = [];
    let loaded = 0;
    SRC.forEach((src) => { const im = new Image(); im.onload = () => loaded++; im.src = src; imgs.push(im); });

    let W = 0, H = 0, dpr = 1;
    let cols = 0, rows = 0, cell = 26, gap = 4, gridTop = 0, gridLeft = 0, mergeY = 0;
    let grid = [], colFill = [];
    const particles = [], pops = [];
    let active = false, lastT = 0, spawnAcc = 0;

    function resize() {
      const r = canvas.getBoundingClientRect();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      W = r.width; H = r.height;
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // data grid occupies the bottom ~42%
      const bandTop = H * 0.6;
      mergeY = bandTop;
      cell = clamp(Math.round(W / 46), 16, 30); gap = Math.max(3, Math.round(cell * 0.16));
      cols = Math.floor(W / (cell + gap));
      gridLeft = Math.round((W - cols * (cell + gap) + gap) / 2);
      rows = Math.max(4, Math.floor((H - bandTop - 30) / (cell + gap)));
      gridTop = Math.round(H - rows * (cell + gap));
      grid = new Array(cols * rows).fill(0);
      colFill = new Array(cols).fill(0);
    }
    resize();
    window.addEventListener("resize", () => { clearTimeout(resize._t); resize._t = setTimeout(resize, 150); });

    function spawn() {
      if (particles.length > 130) return;
      const im = imgs[(Math.random() * imgs.length) | 0];
      const size = rand(26, 56);
      particles.push({
        x: rand(0.04 * W, 0.96 * W), y: rand(-80, -10),
        vx: rand(-14, 14), vy: rand(20, 60), size,
        rot: rand(0, Math.PI * 2), vrot: rand(-1.4, 1.4),
        img: im, state: "fall", tx: 0, ty: 0, col: 0, life: 1,
      });
    }

    function targetCell(x) {
      let c = clamp(Math.round((x - gridLeft) / (cell + gap)), 0, cols - 1);
      // find a column with room; drift to neighbour if full
      let tries = 0;
      while (colFill[c] >= rows && tries < cols) { c = (c + 1) % cols; tries++; }
      const row = rows - 1 - colFill[c];
      colFill[c] = Math.min(rows, colFill[c] + 1);
      return { c, row, cx: gridLeft + c * (cell + gap) + cell / 2, cy: gridTop + row * (cell + gap) + cell / 2 };
    }

    function update(dt) {
      spawnAcc += dt;
      const interval = 0.085;
      while (spawnAcc > interval) { spawnAcc -= interval; if (active) spawn(); }

      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        if (p.state === "fall") {
          p.vy += 240 * dt; p.y += p.vy * dt; p.x += p.vx * dt; p.rot += p.vrot * dt;
          if (p.x < -60 || p.x > W + 60) { particles.splice(i, 1); continue; }
          if (p.y >= mergeY) {
            const tgt = targetCell(p.x);
            p.state = "merge"; p.tx = tgt.cx; p.ty = tgt.cy; p.gi = tgt.row * cols + tgt.c;
            p.t0 = 0;
          }
        } else {
          p.t0 += dt * 3.2;
          const e = clamp(p.t0, 0, 1);
          const ee = e * e * (3 - 2 * e);
          p.x += (p.tx - p.x) * ee * 0.5;
          p.y += (p.ty - p.y) * ee * 0.5;
          p.size *= (1 - 0.04 * (dt * 60));
          p.life = 1 - e;
          p.rot += p.vrot * dt * 2;
          if (e >= 1) {
            if (p.gi != null && p.gi >= 0 && p.gi < grid.length) grid[p.gi] = 1;
            pops.push({ x: p.tx, y: p.ty, life: 1 });
            particles.splice(i, 1);
          }
        }
      }
      // decay grid so it breathes and recycles
      for (let i = 0; i < grid.length; i++) if (grid[i] > 0) grid[i] = Math.max(0, grid[i] - 0.06 * dt);
      // recompute column fills from decayed grid occasionally
      for (let c = 0; c < cols; c++) {
        let f = 0;
        for (let r = rows - 1; r >= 0; r--) { if (grid[r * cols + c] > 0.12) f++; else break; }
        colFill[c] = f;
      }
      for (let i = pops.length - 1; i >= 0; i--) { pops[i].life -= dt * 1.6; pops[i].y -= 30 * dt; if (pops[i].life <= 0) pops.splice(i, 1); }
    }

    function draw() {
      ctx.clearRect(0, 0, W, H);
      // data grid
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const v = grid[r * cols + c];
          const x = gridLeft + c * (cell + gap), y = gridTop + r * (cell + gap);
          if (v <= 0.001) {
            ctx.fillStyle = "rgba(255,221,170,0.05)";
          } else {
            const a = 0.18 + v * 0.82;
            ctx.fillStyle = `rgba(${226 + v * 20},${174 + v * 30},${64 + v * 40},${a})`;
            if (v > 0.6) { ctx.shadowColor = "rgba(240,207,110,0.7)"; ctx.shadowBlur = 10 * v; }
          }
          roundRect(ctx, x, y, cell, cell, 4); ctx.fill(); ctx.shadowBlur = 0;
        }
      }
      // falling + merging sprites
      for (const p of particles) {
        ctx.save();
        ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.globalAlpha = p.state === "merge" ? clamp(p.life, 0, 1) : 1;
        if (p.img && p.img.complete) {
          const iw = p.img.width || 1, ih = p.img.height || 1, s = p.size / Math.max(iw, ih);
          const w = iw * s, h = ih * s;
          if (p.state === "fall") { ctx.shadowColor = "rgba(8,30,50,0.25)"; ctx.shadowBlur = 12; ctx.shadowOffsetY = 8; }
          ctx.drawImage(p.img, -w / 2, -h / 2, w, h);
        }
        ctx.restore();
      }
      ctx.globalAlpha = 1; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
      // +1 pops
      ctx.font = "700 12px 'JetBrains Mono', monospace"; ctx.textAlign = "center";
      for (const pop of pops) {
        ctx.globalAlpha = clamp(pop.life, 0, 1);
        ctx.fillStyle = "#f0cf6e";
        ctx.fillText("+1 step", pop.x, pop.y);
      }
      ctx.globalAlpha = 1;
    }

    function roundRect(c, x, y, w, h, r) {
      c.beginPath(); c.moveTo(x + r, y);
      c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
      c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
    }

    function loop(t) {
      const dt = Math.min(0.05, (t - lastT) / 1000 || 0); lastT = t;
      update(dt); draw();
      requestAnimationFrame(loop);
    }

    if (reduceMotion) {
      // static-ish: seed a partly-filled grid, no falling
      resize();
      for (let c = 0; c < cols; c++) { const f = Math.floor(rand(0, rows)); for (let r = rows - 1; r >= rows - f; r--) grid[r * cols + c] = rand(0.4, 1); }
      draw();
    } else {
      const vis = new IntersectionObserver((es) => es.forEach((e) => { active = e.isIntersecting; }), { threshold: 0.02 });
      vis.observe(canvas);
      requestAnimationFrame((t) => { lastT = t; loop(t); });
    }
  }
})();
