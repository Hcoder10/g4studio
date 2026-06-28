/* G4 Studio web fallback: prompt -> Gemma-4 swarm (live agents + speed) -> .rbxmx.
   No three.js — the visual game lives in Roblox (plugin or Insert From File). */
(() => {
  "use strict";

  const EXAMPLES = [
    "neon lava parkour with moving platforms and 2 checkpoints",
    "icy mountain climb with slippery ledges and spinning gaps",
    "candy world bounce course with pastel platforms",
    "spooky graveyard obby with crumbling bridges",
    "sci-fi space station with floating panels and laser gaps",
  ];

  const el = (id) => document.getElementById(id);
  const hudTime = el("hud-time"), hudTps = el("hud-tps"), hudParts = el("hud-parts"), hudAgents = el("hud-agents");
  const agentsBox = el("agents"), stagesBox = el("stages"), placeholder = el("placeholder");
  const mTokens = el("m-tokens"), mStages = el("m-stages");
  const resultCard = el("result"), resultTitle = el("result-title"), resultSub = el("result-sub"), dlRbxmx = el("dl-rbxmx");

  let startT = 0, timerRAF = 0, totalTokens = 0, partsCount = 0, agentCount = 0, running = false;

  const CHIP = { platforms: ["platform", "▰"], hazards: ["hazard", "▮"], checkpoints: ["checkpoint", "⚑"], moving: ["moving", "⇄"] };

  function tickTimer() {
    if (!running) return;
    hudTime.textContent = Math.round(performance.now() - startT).toLocaleString();
    const secs = (performance.now() - startT) / 1000;
    if (secs > 0) hudTps.textContent = Math.round(totalTokens / secs).toLocaleString();
    timerRAF = requestAnimationFrame(tickTimer);
  }

  function resetUI() {
    agentsBox.innerHTML = ""; stagesBox.innerHTML = "";
    totalTokens = 0; partsCount = 0; agentCount = 0;
    hudTime.textContent = "0"; hudTps.textContent = "0"; hudParts.textContent = "0"; hudAgents.textContent = "0";
    mTokens.textContent = "0"; mStages.textContent = "0";
    resultCard.classList.add("hidden");
    placeholder.classList.add("hidden");
  }

  function addAgentCard(id, name, role, isDirector) {
    const div = document.createElement("div");
    div.className = "agent active" + (isDirector ? " director" : "");
    div.id = "agent-" + id;
    div.innerHTML =
      `<div class="agent-top"><span class="agent-name">${name}</span><span class="agent-role">${role}</span></div>` +
      `<div class="agent-stat"><span class="dotpulse"></span>working…</div>`;
    agentsBox.appendChild(div);
    agentCount++; hudAgents.textContent = agentCount;
  }

  function finishAgentCard(id, statHtml) {
    const div = el("agent-" + id);
    if (!div) return;
    div.classList.remove("active"); div.classList.add("done");
    const stat = div.querySelector(".agent-stat");
    if (stat) stat.innerHTML = statHtml;
  }

  function addStageCard(e) {
    const c = e.counts || {};
    const n = (c.platforms || 0) + (c.hazards || 0) + (c.checkpoints || 0) + (c.moving || 0);
    partsCount += n; hudParts.textContent = partsCount;
    const chips = Object.keys(CHIP)
      .filter((k) => (c[k] || 0) > 0)
      .map((k) => `<span class="chip2 ${CHIP[k][0]}">${CHIP[k][1]} ${c[k]}</span>`)
      .join("");
    const div = document.createElement("div");
    div.className = "stage-card pop";
    div.innerHTML =
      `<div class="stage-name">${e.name || "Stage " + (e.stage + 1)}</div>` +
      `<div class="stage-chips">${chips}</div>` +
      `<div class="stage-meta">${e.tps} tok/s · ${e.ms} ms</div>`;
    stagesBox.appendChild(div);
  }

  function handleEvent(ev) {
    switch (ev.type) {
      case "director_started":
        addAgentCard("director", "Director", "design", true); break;
      case "director_done":
        totalTokens += ev.tokens || 0;
        mStages.textContent = ev.stages || 0;
        mTokens.textContent = totalTokens.toLocaleString();
        finishAgentCard("director", `“${ev.name || "obby"}” · ${ev.stages} stages · <span class="tps">${ev.tps}</span> tok/s`);
        break;
      case "builder_started":
        addAgentCard("b" + ev.stage, ev.name || `Stage ${ev.stage + 1}`, "builder"); break;
      case "builder_done": {
        totalTokens += ev.tokens || 0;
        mTokens.textContent = totalTokens.toLocaleString();
        addStageCard(ev);
        const c = ev.counts || {};
        const parts = (c.platforms || 0) + (c.hazards || 0) + (c.checkpoints || 0) + (c.moving || 0);
        finishAgentCard("b" + ev.stage, `${parts} parts · <span class="tps">${ev.tps}</span> tok/s · ${ev.ms} ms`);
        break;
      }
      case "builder_error":
        finishAgentCard("b" + ev.stage, `error`); break;
      case "agent":
        if (ev.status === "done") finishAgentCard(ev.id, ev.detail || "done");
        else addAgentCard(ev.id, ev.name || ev.id, ev.role || "agent");
        break;
      case "playtest": {
        const card = document.createElement("div");
        card.className = "stage-card vision-card pop";
        const issues = (ev.issues || []).map((i) => `<li>${i}</li>`).join("");
        card.innerHTML =
          `<div class="vision-head">👁 Playtester saw the level — <b>${ev.score}/10</b> · ${ev.fixes} auto-fixes</div>` +
          `<img class="vision-img" src="${ev.image}" alt="playtester view" />` +
          `<div class="vision-verdict">${ev.verdict || ""}</div>` +
          (issues ? `<ul class="vision-issues">${issues}</ul>` : "");
        stagesBox.appendChild(card);
        break;
      }
      case "done":
        running = false; cancelAnimationFrame(timerRAF); showResult(ev); el("go").disabled = false; break;
      case "error":
        running = false; cancelAnimationFrame(timerRAF);
        resultTitle.textContent = "Generation failed";
        resultSub.textContent = ev.error || "unknown error";
        resultCard.classList.remove("hidden"); el("go").disabled = false; break;
    }
  }

  function showResult(ev) {
    const m = ev.metrics || {};
    hudTime.textContent = (m.wall_ms || 0).toLocaleString();
    hudParts.textContent = m.parts || partsCount;
    resultTitle.textContent = `${m.name || "Your obby"} — built in ${(m.wall_ms || 0).toLocaleString()} ms`;
    resultSub.textContent =
      `${m.agents} agents · ${m.parts} parts ` +
      `(${m.platforms} platforms, ${m.hazards} hazards, ${m.checkpoints} checkpoints, ${m.moving} moving) · ` +
      `${(m.completion_tokens || 0).toLocaleString()} tokens on Gemma-4 / Cerebras`;
    if (ev.rbxmx) {
      const blob = new Blob([ev.rbxmx], { type: "application/xml" });
      dlRbxmx.href = URL.createObjectURL(blob);
    }
    resultCard.classList.remove("hidden");
  }

  function generate() {
    const prompt = el("prompt").value.trim();
    if (!prompt) return;
    el("go").disabled = true;
    resetUI();
    running = true; startT = performance.now(); tickTimer();

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/generate`);
    ws.onopen = () => ws.send(JSON.stringify({ prompt }));
    ws.onmessage = (msg) => handleEvent(JSON.parse(msg.data));
    ws.onerror = () => { running = false; el("go").disabled = false; };
    ws.onclose = () => { running = false; el("go").disabled = false; cancelAnimationFrame(timerRAF); };
  }

  el("go").addEventListener("click", generate);
  el("prompt").addEventListener("keydown", (e) => { if (e.key === "Enter") generate(); });
  const exBox = el("examples");
  EXAMPLES.forEach((ex) => {
    const s = document.createElement("span");
    s.className = "ex"; s.textContent = ex;
    s.addEventListener("click", () => { el("prompt").value = ex; generate(); });
    exBox.appendChild(s);
  });
})();
