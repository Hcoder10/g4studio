/* G4 Studio frontend: live 3D obby build streamed from the Gemma-4 swarm. */
(() => {
  "use strict";

  const EXAMPLES = [
    "neon lava parkour with moving platforms and 2 checkpoints",
    "icy mountain climb with slippery ledges and spinning gaps",
    "candy world bounce course with pastel platforms",
    "spooky graveyard obby with crumbling bridges",
    "sci-fi space station with floating panels and laser gaps",
  ];

  // ---- three.js scene -------------------------------------------------------
  const wrap = document.getElementById("canvas-wrap");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070a10);
  scene.fog = new THREE.Fog(0x070a10, 220, 520);

  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 4000);
  camera.position.set(70, 90, -90);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  wrap.appendChild(renderer.domElement);

  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = false;

  scene.add(new THREE.AmbientLight(0x8899bb, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(60, 120, 40);
  scene.add(dir);
  const grid = new THREE.GridHelper(800, 80, 0x1e2a3a, 0x121a26);
  grid.position.y = -0.2;
  scene.add(grid);

  let group = new THREE.Group();
  scene.add(group);
  const bounds = new THREE.Box3();
  let hasBounds = false;
  const popQueue = []; // {mesh, t0}

  function resize() {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h || 1;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);

  function hexColor(hex) {
    if (typeof hex !== "string") return 0x9aa0a6;
    const c = new THREE.Color();
    try { c.set(hex.trim()); } catch (e) { return 0x9aa0a6; }
    return c.getHex();
  }

  function addBox(pos, size, hex, kind) {
    const sx = Math.max(size?.x || 8, 0.2);
    const sy = Math.max(size?.y || 1, 0.2);
    const sz = Math.max(size?.z || 8, 0.2);
    const geo = new THREE.BoxGeometry(sx, sy, sz);
    const col = hexColor(hex);
    let emissive = 0x000000, emiInt = 0.0;
    if (kind === "hazard") { emissive = 0xff5a1f; emiInt = 0.9; }
    else if (kind === "moving") { emissive = 0x4aa3ff; emiInt = 0.6; }
    else if (kind === "checkpoint") { emissive = 0x39d353; emiInt = 0.8; }
    else if (kind === "win") { emissive = 0xffd400; emiInt = 0.9; }
    else if (kind === "spawn") { emissive = 0x39d353; emiInt = 0.5; }
    else { emissive = col; emiInt = 0.18; }
    const mat = new THREE.MeshStandardMaterial({
      color: col, emissive: emissive, emissiveIntensity: emiInt,
      roughness: 0.55, metalness: 0.1,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(pos?.x || 0, pos?.y || 0, pos?.z || 0);
    mesh.scale.setScalar(0.001);
    group.add(mesh);
    popQueue.push({ mesh, t0: performance.now() });

    bounds.expandByPoint(new THREE.Vector3(mesh.position.x, mesh.position.y, mesh.position.z));
    hasBounds = true;
    frameCamera();
    return mesh;
  }

  let lastFrameT = 0;
  function frameCamera() {
    if (!hasBounds) return;
    const now = performance.now();
    if (now - lastFrameT < 120) return; // throttle
    lastFrameT = now;
    const center = new THREE.Vector3();
    bounds.getCenter(center);
    const size = new THREE.Vector3();
    bounds.getSize(size);
    const radius = Math.max(size.length(), 30);
    controls.target.lerp(center, 0.25);
    const desired = new THREE.Vector3(center.x + radius * 0.6, center.y + radius * 0.7, center.z - radius * 0.9);
    camera.position.lerp(desired, 0.15);
  }

  function clearScene() {
    scene.remove(group);
    group.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    group = new THREE.Group();
    scene.add(group);
    bounds.makeEmpty();
    hasBounds = false;
    popQueue.length = 0;
  }

  function animate() {
    requestAnimationFrame(animate);
    const now = performance.now();
    for (let i = popQueue.length - 1; i >= 0; i--) {
      const p = popQueue[i];
      const k = Math.min((now - p.t0) / 180, 1);
      const s = 1 - Math.pow(1 - k, 3); // easeOutCubic
      p.mesh.scale.setScalar(s < 0.01 ? 0.01 : s);
      if (k >= 1) popQueue.splice(i, 1);
    }
    controls.update();
    renderer.render(scene, camera);
  }
  resize();
  animate();

  // ---- HUD + swarm panel ----------------------------------------------------
  const el = (id) => document.getElementById(id);
  const hudTime = el("hud-time"), hudTps = el("hud-tps"), hudParts = el("hud-parts"), hudAgents = el("hud-agents");
  const agentsBox = el("agents"), mTokens = el("m-tokens"), mStages = el("m-stages");
  const resultCard = el("result"), resultTitle = el("result-title"), resultSub = el("result-sub"), dlRbxmx = el("dl-rbxmx");

  let startT = 0, timerRAF = 0, totalTokens = 0, partsCount = 0, agentCount = 0, running = false;

  function tickTimer() {
    if (!running) return;
    hudTime.textContent = Math.round(performance.now() - startT).toLocaleString();
    const secs = (performance.now() - startT) / 1000;
    if (secs > 0) hudTps.textContent = Math.round(totalTokens / secs).toLocaleString();
    timerRAF = requestAnimationFrame(tickTimer);
  }

  function resetUI() {
    clearScene();
    agentsBox.innerHTML = "";
    totalTokens = 0; partsCount = 0; agentCount = 0;
    hudTime.textContent = "0"; hudTps.textContent = "0"; hudParts.textContent = "0"; hudAgents.textContent = "0";
    mTokens.textContent = "0"; mStages.textContent = "0";
    resultCard.classList.add("hidden");
  }

  function addAgentCard(id, name, role, isDirector) {
    const div = document.createElement("div");
    div.className = "agent active" + (isDirector ? " director" : "");
    div.id = "agent-" + id;
    div.innerHTML =
      `<div class="agent-top"><span class="agent-name">${name}</span><span class="agent-role">${role}</span></div>` +
      `<div class="agent-stat"><span class="dotpulse"></span>working…</div>`;
    agentsBox.appendChild(div);
    agentCount++;
    hudAgents.textContent = agentCount;
    return div;
  }

  function finishAgentCard(id, statHtml) {
    const div = el("agent-" + id);
    if (!div) return;
    div.classList.remove("active");
    div.classList.add("done");
    const stat = div.querySelector(".agent-stat");
    if (stat) stat.innerHTML = statHtml;
  }

  function renderElements(els) {
    if (!els) return;
    (els.platforms || []).forEach((p) => addBox(p.pos, p.size, p.color, "platform"));
    (els.hazards || []).forEach((p) => addBox(p.pos, p.size, p.color, "hazard"));
    (els.checkpoints || []).forEach((p) => addBox(p.pos, p.size, p.color, "checkpoint"));
    (els.moving || []).forEach((p) => addBox(p.pos, p.size, p.color, "moving"));
    const n = ["platforms", "hazards", "checkpoints", "moving"].reduce((a, k) => a + ((els[k] || []).length), 0);
    partsCount += n;
    hudParts.textContent = partsCount;
  }

  // ---- WebSocket generation -------------------------------------------------
  function generate() {
    const prompt = el("prompt").value.trim();
    if (!prompt) return;
    const go = el("go");
    go.disabled = true;
    resetUI();
    running = true;
    startT = performance.now();
    tickTimer();

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/generate`);
    ws.onopen = () => ws.send(JSON.stringify({ prompt }));
    ws.onmessage = (msg) => handleEvent(JSON.parse(msg.data));
    ws.onerror = () => { running = false; go.disabled = false; };
    ws.onclose = () => { running = false; go.disabled = false; cancelAnimationFrame(timerRAF); };
  }

  function handleEvent(e) {
    switch (e.type) {
      case "director_started":
        addAgentCard("director", "Director", "design", true);
        break;
      case "director_done":
        totalTokens += e.tokens || 0;
        mStages.textContent = e.stages || 0;
        mTokens.textContent = totalTokens.toLocaleString();
        finishAgentCard("director", `“${e.name || "obby"}” · ${e.stages} stages · <span class="tps">${e.tps}</span> tok/s`);
        break;
      case "builder_started":
        addAgentCard("b" + e.stage, e.name || `Stage ${e.stage + 1}`, "builder");
        break;
      case "builder_done": {
        totalTokens += e.tokens || 0;
        mTokens.textContent = totalTokens.toLocaleString();
        renderElements(e.elements);
        const c = e.counts || {};
        const parts = (c.platforms || 0) + (c.hazards || 0) + (c.checkpoints || 0) + (c.moving || 0);
        finishAgentCard("b" + e.stage, `${parts} parts · <span class="tps">${e.tps}</span> tok/s · ${e.ms} ms`);
        break;
      }
      case "builder_error":
        finishAgentCard("b" + e.stage, `error`);
        break;
      case "assembled":
        if (e.spawn) addBox(e.spawn, { x: 8, y: 1, z: 8 }, "#cfd8dc", "spawn");
        if (e.win) addBox(e.win, { x: 12, y: 1, z: 12 }, "#ffd400", "win");
        break;
      case "done":
        running = false;
        cancelAnimationFrame(timerRAF);
        showResult(e);
        el("go").disabled = false;
        break;
      case "error":
        running = false;
        cancelAnimationFrame(timerRAF);
        resultTitle.textContent = "Generation failed";
        resultSub.textContent = e.error || "unknown error";
        resultCard.classList.remove("hidden");
        el("go").disabled = false;
        break;
    }
  }

  function showResult(e) {
    const m = e.metrics || {};
    hudTime.textContent = (m.wall_ms || 0).toLocaleString();
    hudParts.textContent = m.parts || partsCount;
    resultTitle.textContent = `${m.name || "Your obby"} — built in ${(m.wall_ms || 0).toLocaleString()} ms`;
    resultSub.textContent =
      `${m.agents} agents · ${m.parts} parts ` +
      `(${m.platforms} platforms, ${m.hazards} hazards, ${m.checkpoints} checkpoints, ${m.moving} moving) · ` +
      `${(m.completion_tokens || 0).toLocaleString()} tokens on Gemma-4 / Cerebras`;
    if (e.rbxmx) {
      const blob = new Blob([e.rbxmx], { type: "application/xml" });
      dlRbxmx.href = URL.createObjectURL(blob);
    }
    resultCard.classList.remove("hidden");
  }

  // ---- wire up --------------------------------------------------------------
  el("go").addEventListener("click", generate);
  el("prompt").addEventListener("keydown", (ev) => { if (ev.key === "Enter") generate(); });
  const exBox = el("examples");
  EXAMPLES.forEach((ex) => {
    const s = document.createElement("span");
    s.className = "ex"; s.textContent = ex;
    s.addEventListener("click", () => { el("prompt").value = ex; generate(); });
    exBox.appendChild(s);
  });
})();
