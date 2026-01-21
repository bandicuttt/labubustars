(() => {
  const $ = (sel) => document.querySelector(sel);

  const canvas = $("#game");
  const ctx = canvas.getContext("2d");

  const CAMERA_ZOOM = 1;

  const SPRITE_CFG = {
    planeScale: 0.12,
    planeBottomTrimPx: 8,
    planeDeckInsetPx: 50,
    pierDeckY: 410,
    pierDeckAboveSea: 50,
  };

  const assets = {
    ready: false,
    bgs: [],
    piers: [],
    plane: null,
  };

  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(`Failed to load ${src}`));
      img.src = src;
    });
  }

  async function loadAssets() {
    const [bg1, bg2, bg3, pier1, pier2, plane] = await Promise.all([
      loadImage("air1.png"),
      loadImage("air2.png"),
      loadImage("air3.png"),
      loadImage("pears.png"),
      loadImage("pears2.png"),
      loadImage("plane.png"),
    ]);

    assets.bgs = [bg1, bg2, bg3];
    assets.piers = [pier1, pier2];
    assets.plane = plane;
    assets.ready = true;
  }

  const elMenu = $("#menu");
  const elMenuTitle = $(".menuTitle");
  const elAdBtn = $("#adBtn");
  const MENU_TITLE_TEXT = elMenuTitle ? elMenuTitle.textContent : "";

  const state = {
    running: false,
    phase: "menu",
    lastTs: 0,
    startTs: 0,
    durationMs: 9000,
    u: 0,
    landedAt: 0,
    seed: 0,
    path: null,
    bonuses: [],
    decorBonuses: [],
    fakePiers: [],
    pickupTexts: [],
    score: 1,
    altOffset: 0,
    altTarget: 0,
    engineFailU: -1,
    engineWillFail: false,
    landWillOvershoot: false,
    plane: null,
    particles: [],
    bgImg: null,
    pierImg: null,
    closeTimer: null,
    adMode: false,
    adBlockId: "",
    limitReached: false,
    adController: null,
  };

  function parseLaunchFlags() {
    try {
      const sp = new URLSearchParams(window.location.search);
      state.adMode = sp.get("ad") === "1";
      state.adBlockId = sp.get("abid") || "";
      state.limitReached = sp.get("limit") === "1";
    } catch (_) {
      state.adMode = false;
      state.adBlockId = "";
      state.limitReached = false;
    }
  }

  function getAdController() {
    if (state.adController) return state.adController;
    if (!state.adBlockId) return null;
    const sdk = window.Adsgram;
    if (!sdk || typeof sdk.init !== "function") return null;
    try {
      state.adController = sdk.init({ blockId: state.adBlockId });
      return state.adController;
    } catch (_) {
      return null;
    }
  }

  async function showRewardAd() {
    const ctrl = getAdController();
    if (!ctrl || typeof ctrl.show !== "function") {
      throw new Error("Adsgram not initialized");
    }
    return await ctrl.show();
  }

  function clamp(v, a, b) {
    return Math.max(a, Math.min(b, v));
  }

  function rnd(seed) {
    let t = seed + 0x6d2b79f5;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  function makeRng(seed) {
    let s = seed >>> 0;
    return () => {
      s = (s + 1) >>> 0;
      return rnd(s ^ 0xa5a5a5a5);
    };
  }

  function pick(rng, arr) {
    return arr[Math.floor(rng() * arr.length)];
  }

  function easeInOutCubic(x) {
    const t = clamp(x, 0, 1);
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function spawnExplosion(x, y, seed) {
    const rng = makeRng((seed ^ 0xdeadbeef) >>> 0);
    const n = 34;
    for (let i = 0; i < n; i++) {
      const a = rng() * Math.PI * 2;
      const sp = 80 + rng() * 260;
      state.particles.push({
        x,
        y,
        vx: Math.cos(a) * sp,
        vy: Math.sin(a) * sp,
        r: 2 + rng() * 6,
        life: 520 + rng() * 520,
        t0: 0,
        kind: "explosion",
      });
    }
  }

  function spawnSplash(x, y, seed) {
    const rng = makeRng((seed ^ 0x1234abcd) >>> 0);
    const n = 22;
    for (let i = 0; i < n; i++) {
      const a = (-Math.PI / 2) + (rng() - 0.5) * Math.PI * 0.9;
      const sp = 60 + rng() * 200;
      state.particles.push({
        x,
        y,
        vx: Math.cos(a) * sp,
        vy: Math.sin(a) * sp,
        r: 1 + rng() * 5,
        life: 520 + rng() * 620,
        t0: 0,
        kind: "splash",
      });
    }
  }

  function spawnStars(x, y, good, seed) {
    const rng = makeRng((seed ^ (good ? 0x77aa11cc : 0x33cc55aa)) >>> 0);
    const n = 14;
    for (let i = 0; i < n; i++) {
      const a = (-Math.PI / 2) + (rng() - 0.5) * Math.PI * 1.4;
      const sp = 70 + rng() * 220;
      state.particles.push({
        x,
        y,
        vx: Math.cos(a) * sp,
        vy: Math.sin(a) * sp,
        r: 2 + rng() * 5,
        life: 520 + rng() * 520,
        t0: 0,
        kind: "star",
        good,
      });
    }
  }

  function updateParticles(dtMs) {
    if (!state.particles || state.particles.length === 0) return;

    const dt = clamp(dtMs, 0, 50) / 1000;
    const gravity = 520;

    for (const p of state.particles) {
      p.t0 += dtMs;
      const k = clamp(p.t0 / p.life, 0, 1);

      if (p.kind === "explosion") {
        p.vx *= 0.986;
        p.vy *= 0.986;
      } else if (p.kind === "star") {
        p.vx *= 0.988;
        p.vy *= 0.988;
      } else {
        p.vx *= 0.992;
      }

      if (p.kind === "star") {
        p.vy += (-260) * dt;
      } else {
        p.vy += gravity * dt * (p.kind === "splash" ? 1.0 : 0.6);
      }
      p.x += p.vx * dt;
      p.y += p.vy * dt;

      void k;
    }

    state.particles = state.particles.filter((p) => p.t0 < p.life);
  }

  function renderParticles() {
    if (!state.particles || state.particles.length === 0) return;

    function drawStarShape(x, y, r, rot) {
      const spikes = 5;
      const inner = r * 0.45;
      let a = rot;
      ctx.beginPath();
      for (let i = 0; i < spikes; i++) {
        ctx.lineTo(x + Math.cos(a) * r, y + Math.sin(a) * r);
        a += Math.PI / spikes;
        ctx.lineTo(x + Math.cos(a) * inner, y + Math.sin(a) * inner);
        a += Math.PI / spikes;
      }
      ctx.closePath();
      ctx.fill();
    }

    for (const p of state.particles) {
      const k = clamp(p.t0 / p.life, 0, 1);
      const a = 1 - k;
      if (p.kind === "explosion") {
        ctx.fillStyle = `rgba(255, ${Math.floor(140 + 70 * a)}, 60, ${0.75 * a})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(0.5, p.r * (0.7 + 0.8 * a)), 0, Math.PI * 2);
        ctx.fill();
        continue;
      }
      if (p.kind === "star") {
        ctx.fillStyle = p.good
          ? `rgba(255, 214, 80, ${0.85 * a})`
          : `rgba(255, 255, 255, ${0.55 * a})`;
        drawStarShape(p.x, p.y, Math.max(1.5, p.r * (0.8 + 0.9 * a)), k * 2.6);
        continue;
      } else {
        ctx.fillStyle = `rgba(255, 255, 255, ${0.55 * a})`;
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, Math.max(0.5, p.r * (0.7 + 0.8 * a)), 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function startCrash(reason, ts) {
    const path = state.path;
    const pose = getPlanePose();

    state.phase = "crashing";
    state.score = 0;
    state.altOffset = 0;
    state.altTarget = 0;
    state.pickupTexts = [];

    const dir = Math.cos(pose.ang) >= 0 ? 1 : -1;
    const baseVx = reason === "landing" ? 220 : 160;
    const baseVy = reason === "engine" ? 40 : 0;

    state.plane = {
      x: pose.x,
      y: pose.y,
      vx: dir * baseVx,
      vy: baseVy,
      ang: pose.ang,
      spin: (reason === "engine" ? 2.2 : 1.2) * (dir > 0 ? 1 : -1),
      inWater: false,
      t0: ts,
      reason,
    };

    if (reason === "engine") {
      spawnExplosion(state.plane.x, state.plane.y, state.seed);
    }

    if (path && state.plane.y >= path.seaY) {
      state.plane.inWater = true;
    }
  }

  function resize() {
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.floor(r.width * dpr);
    canvas.height = Math.floor(r.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function showMenu(kind = "start") {
    if (elMenuTitle) {
      if (kind === "result") {
        const v = clamp(state.score, 0, 1);
        elMenuTitle.textContent = `⭐ ${v.toFixed(2)}`;
      } else {
        elMenuTitle.textContent = MENU_TITLE_TEXT;
      }
    }
    elMenu.hidden = false;

    if (kind === "result") {
      if (state.closeTimer) {
        clearTimeout(state.closeTimer);
        state.closeTimer = null;
      }
      state.closeTimer = setTimeout(() => {
        closeApp();
      }, 3000);
    }
  }

  function hideMenu() {
    elMenu.hidden = true;
  }

  function closeApp() {
    const tg = window.Telegram && window.Telegram.WebApp;

    let back = "";
    try {
      const sp = new URLSearchParams(window.location.search);
      back = sp.get("back") || "";
    } catch (_) {}

    try {
      if (tg && typeof tg.close === "function") {
        tg.close();
      }
    } catch (_) {}

    try {
      if (back) {
        window.location.href = back;
        setTimeout(() => {
          try {
            const m = /^(?:https?:\/\/)?t\.me\/(.+)$/i.exec(back);
            const username = m && m[1] ? m[1].replace(/^@/, "") : "";
            if (username) window.location.href = `tg://resolve?domain=${encodeURIComponent(username)}`;
          } catch (_) {}
        }, 150);
      }
    } catch (_) {}

    try {
      window.close();
    } catch (_) {}

    try {
      window.open("", "_self");
      window.close();
    } catch (_) {}

    try {
      history.back();
    } catch (_) {}

    try {
      window.location.replace("about:blank");
    } catch (_) {}
  }

  function buildPath(w, h, seed, flightScale = 1) {
    const rng = makeRng(seed);
    const seaY = h * 0.76;

    const pierW = 240;
    const pierH = 18;
    const pierY = seaY - SPRITE_CFG.pierDeckAboveSea;

    const planeBottomPx = (assets.ready && assets.plane)
      ? (assets.plane.height * SPRITE_CFG.planeScale) / 2 - SPRITE_CFG.planeBottomTrimPx
      : 7;
    const pierContactInsetPx = SPRITE_CFG.planeDeckInsetPx;

    const leftX = 180;
    const baseDx = Math.max(420, w - 360);
    const rightX = leftX + baseDx * Math.max(1, flightScale);

    const startY = pierY - planeBottomPx + pierContactInsetPx;
    const endY = pierY - planeBottomPx + pierContactInsetPx;

    const yMin = 60;
    const flightMaxY = seaY - 120;
    const baseline = h * (0.32 + rng() * 0.10);
    const minAmp = Math.min(h * 0.06, 90);
    const varAmp = Math.min(h * 0.11, 180);

    const knotsCount = 11 + 2 * Math.floor(rng() * 4);
    const uKnots = new Array(knotsCount);
    const yKnots = new Array(knotsCount);
    uKnots[0] = 0;
    uKnots[knotsCount - 1] = 1;
    yKnots[0] = startY;
    yKnots[knotsCount - 1] = endY;

    const segN = knotsCount - 1;
    const segShape = new Array(segN);
    const minStep = 0.04;
    const weights = new Array(segN);
    let wSum = 0;
    for (let s = 0; s < segN; s++) {
      const wgt = 0.5 + rng() * 2.5;
      weights[s] = wgt;
      wSum += wgt;

      segShape[s] = 0.6 + rng() * 1.5;
    }
    const extra = Math.max(0, 1 - segN * minStep);
    let acc = 0;
    for (let i = 1; i < knotsCount; i++) {
      acc += minStep + (extra * weights[i - 1]) / wSum;
      uKnots[i] = clamp(acc, 0, 1);
    }
    uKnots[knotsCount - 1] = 1;

    {
      const minDelta = 60;
      const maxDelta = 230;
      const minEndDelta = 70;

      let prevY = startY;

      for (let i = 1; i < knotsCount - 1; i++) {
        const dir = i % 2 === 1 ? -1 : 1;
        const maxPossible = dir === -1 ? prevY - yMin : flightMaxY - prevY;
        const cap = Math.min(maxDelta, Math.max(0, maxPossible - 4));

        let delta;
        if (cap >= minDelta) delta = minDelta + rng() * (cap - minDelta);
        else delta = Math.max(1, cap);

        delta *= 0.7 + rng() * 0.7;
        let y = prevY + dir * delta;

        if (i === knotsCount - 2) {
          const hardCap = Math.min(prevY - 30, endY - minEndDelta);
          y = Math.min(y, hardCap);
        }

        y = clamp(y, yMin, flightMaxY);

        if (Math.abs(y - prevY) < 18) {
          const nudge = (minDelta * 0.85 + rng() * (maxDelta * 0.6)) * dir;
          y = clamp(prevY + nudge, yMin, flightMaxY);
        }

        yKnots[i] = y;
        prevY = y;
      }
    }

    function yAtU(u) {
      const uu = clamp(u, 0, 1);

      let i1 = 0;
      for (let i = 0; i < knotsCount - 1; i++) {
        if (uu >= uKnots[i] && uu <= uKnots[i + 1]) {
          i1 = i;
          break;
        }
      }

      const u0 = uKnots[i1];
      const u1 = uKnots[i1 + 1];
      const t = u1 > u0 ? (uu - u0) / (u1 - u0) : 0;

      const i0 = clamp(i1 - 1, 0, knotsCount - 1);
      const i2 = clamp(i1 + 1, 0, knotsCount - 1);
      const i3 = clamp(i1 + 2, 0, knotsCount - 1);

      const y0 = yKnots[i1];
      const y1 = yKnots[i1 + 1];
      let s = 0.5 - 0.5 * Math.cos(Math.PI * t);
      s = Math.pow(s, segShape[i1]);
      const y = y0 + (y1 - y0) * s;
      return clamp(y, yMin, pierY);
    }

    function xAtU(u) {
      const uu = clamp(u, 0, 1);
      return leftX + (rightX - leftX) * uu;
    }

    return {
      seaY,
      pierW,
      pierH,
      pierY,
      leftX,
      rightX,
      startY,
      endY,
      xAtU,
      yAtU,
      uKnots,
      yKnots,
    };
  }

  function buildBonuses(path, seed) {
    const rng = makeRng((seed ^ 0x9e3779b9) >>> 0);
    const ups = [
      { op: "+", value: 0.5 },
      { op: "+", value: 1 },
      { op: "+", value: 2 },
      { op: "*", value: 1.15 },
      { op: "*", value: 1.25 },
    ];
    const downs = [
      { op: "-", value: 0.5 },
      { op: "-", value: 1 },
      { op: "-", value: 2 },
      { op: "/", value: 1.15 },
      { op: "/", value: 1.25 },
    ];

    const bonuses = [];
    const uKnots = path.uKnots || [0, 1];
    const yKnots = path.yKnots || [path.startY, path.endY];
    const n = Math.min(uKnots.length, yKnots.length);

    const startUp = n >= 2 ? (yKnots[1] < yKnots[0]) : false;
    if (startUp) {
      const conf = pick(rng, ups);
      bonuses.push({ u: 0.025, op: conf.op, value: conf.value, good: true, taken: false });
    }

    for (let i = 1; i < n - 1; i++) {
      const u = uKnots[i];
      if (u < 0.06 || u > 0.985) continue;

      const yPrev = yKnots[i - 1];
      const y = yKnots[i];
      const yNext = yKnots[i + 1];

      const isPeak = y < yPrev && y < yNext;
      const isValley = y > yPrev && y > yNext;
      if (!isPeak && !isValley) continue;

      const good = isValley;
      const conf = good ? pick(rng, ups) : pick(rng, downs);
      bonuses.push({ u, op: conf.op, value: conf.value, good, taken: false });
    }

    bonuses.sort((a, b) => a.u - b.u);

    function applyToScore(score, b) {
      let s = score;
      if (b.op === "+") s += b.value;
      else if (b.op === "-") s -= b.value;
      else if (b.op === "*") s *= b.value;
      else if (b.op === "/") s /= b.value;
      return clamp(s, 0, 99);
    }

    let s = 1;
    for (const b of bonuses) s = applyToScore(s, b);

    if (s > 1) {
      const need = s - 1;
      const value = Math.ceil(need * 10) / 10;
      bonuses.push({ u: 0.975, op: "-", value, good: false, taken: false });
    }

    return bonuses;
  }

  function buildDecorBonuses(path, seed) {
    const rng = makeRng((seed ^ 0x7f4a7c15) >>> 0);
    const ops = [
      { op: "+", value: 0.5 },
      { op: "+", value: 1 },
      { op: "+", value: 2 },
      { op: "-", value: 0.5 },
      { op: "-", value: 1 },
      { op: "-", value: 2 },
      { op: "*", value: 1.15 },
      { op: "*", value: 1.25 },
      { op: "/", value: 1.15 },
      { op: "/", value: 1.25 },
    ];

    const items = [];
    const count = 100;

    const xMin = path.leftX - 900;
    const xMax = path.rightX + 900;
    const yMin = -Math.max(260, path.seaY * 0.95);
    const yMax = path.seaY - 80;

    const noSpawnDist = 56;
    const dx = path.rightX - path.leftX;

    for (let i = 0; i < count; i++) {
      let x = 0;
      let y = 0;
      let ok = false;
      for (let tries = 0; tries < 40; tries++) {
        x = xMin + (xMax - xMin) * rng();
        y = yMin + (yMax - yMin) * rng();

        if (x >= path.leftX && x <= path.rightX) {
          const u = clamp((x - path.leftX) / dx, 0, 1);
          const yLine = path.yAtU(u);
          if (Math.abs(y - yLine) < noSpawnDist) continue;
        }

        ok = true;
        break;
      }

      if (!ok) {
        x = xMin + (xMax - xMin) * rng();
        y = yMin + (yMax - yMin) * rng();
      }

      const conf = pick(rng, ops);
      const good = conf.op === "+" || conf.op === "*";
      const r = 14;
      items.push({ x, y, op: conf.op, value: conf.value, good, r });
    }

    return items;
  }

  function buildFakePiers(path, seed) {
    const rng = makeRng((seed ^ 0x31415927) >>> 0);
    const piers = [];

    const count = 6;
    const xMin = path.leftX - 260;
    const xMax = path.rightX + 260;
    let yMin = path.pierY + path.pierH + 46;
    const yMax = path.seaY - path.pierH - 2;

    if (yMin > yMax) yMin = path.pierY + path.pierH + 18;

    const gapX = 26;
    const gapY = 10;

    const keepAwayFromRealX = 90;

    function overlaps(a, b) {
      const ax1 = a.x - a.w / 2;
      const ax2 = a.x + a.w / 2;
      const ay1 = a.y;
      const ay2 = a.y + a.h;

      const bx1 = b.x - b.w / 2;
      const bx2 = b.x + b.w / 2;
      const by1 = b.y;
      const by2 = b.y + b.h;

      return ax1 < bx2 + gapX && ax2 > bx1 - gapX && ay1 < by2 + gapY && ay2 > by1 - gapY;
    }

    for (let i = 0; i < count; i++) {
      let placed = false;

      for (let tries = 0; tries < 120; tries++) {
        const w = 170 + rng() * 180;
        const h = path.pierH;
        const x = xMin + (xMax - xMin) * rng();
        const y = yMin + (yMax - yMin) * rng();
        const cand = { x, y, w, h };

        if (Math.abs(cand.x - path.leftX) < (cand.w / 2 + path.pierW / 2 + keepAwayFromRealX)) continue;
        if (Math.abs(cand.x - path.rightX) < (cand.w / 2 + path.pierW / 2 + keepAwayFromRealX)) continue;

        let ok = true;
        for (const p of piers) {
          if (overlaps(cand, p)) {
            ok = false;
            break;
          }
        }

        if (!ok) continue;
        piers.push(cand);
        placed = true;
        break;
      }

      if (!placed) break;
    }

    return piers;
  }

  function formatBonus(b) {
    if (b.op === "+" || b.op === "-") {
      const v = b.value;
      return `⭐${b.op}${Number.isInteger(v) ? v : v.toFixed(1)}`;
    }
    if (b.op === "*") return `⭐×${b.value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}`;
    return `⭐÷${b.value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}`;
  }

  function applyBonus(b) {
    if (b.op === "+") state.score += b.value;
    else if (b.op === "-") state.score -= b.value;
    else if (b.op === "*") state.score *= b.value;
    else if (b.op === "/") state.score /= b.value;

    state.score = clamp(state.score, 0, 99);
  }

  function startGame() {
    state.running = true;
    state.phase = "fly";
    state.lastTs = 0;
    state.startTs = 0;
    state.u = 0;
    state.landedAt = 0;
    state.score = 1;
    state.altOffset = 0;
    state.altTarget = 0;
    state.plane = null;
    state.particles = [];
    state.pickupTexts = [];

    {
      const sp = new URLSearchParams(window.location.search);
      const s = sp.get("seed");
      const n = s ? Number(s) : NaN;
      state.seed = Number.isFinite(n) ? (n >>> 0) : ((Date.now() ^ (Math.random() * 1e9)) >>> 0);
    }
    let flightScale = 1;
    {
      const rng = makeRng((state.seed ^ 0x2c1b3a55) >>> 0);
      state.durationMs = 15000 + rng() * 15000;
      flightScale = state.durationMs / 2000;
    }
    const w = canvas.getBoundingClientRect().width;
    const h = canvas.getBoundingClientRect().height;
    state.path = buildPath(w, h, state.seed, flightScale);
    state.bonuses = buildBonuses(state.path, state.seed);
    state.decorBonuses = buildDecorBonuses(state.path, state.seed);
    state.fakePiers = buildFakePiers(state.path, state.seed);

    if (assets.ready) {
      const rng = makeRng((state.seed ^ 0x55aa33cc) >>> 0);
      state.bgImg = pick(rng, assets.bgs);
      state.pierImg = pick(rng, assets.piers);
    } else {
      state.bgImg = null;
      state.pierImg = null;
    }

    {
      const rng = makeRng((state.seed ^ 0x0f00ba11) >>> 0);
      state.engineWillFail = rng() < 0.10;
      state.engineFailU = state.engineWillFail ? (0.18 + rng() * 0.64) : -1;
      state.landWillOvershoot = rng() < 0.10;
    }

    hideMenu();
  }

  function getPlanePose() {
    if (state.phase === "crashing" && state.plane) {
      return { x: state.plane.x, y: state.plane.y, ang: state.plane.ang };
    }

    const path = state.path;
    const u = clamp(state.u, 0, 1);
    const x = path.xAtU(u);
    const y = path.yAtU(u);

    const du = 0.002;
    const x2 = path.xAtU(u + du);
    const y2 = path.yAtU(u + du);
    const ang = Math.atan2(y2 - y, x2 - x);
    return { x, y, ang };
  }

  function drawPiers(path) {
    const img = state.pierImg;

    if (!img) {
      ctx.fillStyle = "rgba(255,255,255,0.22)";
      ctx.fillRect(path.leftX - path.pierW / 2, path.pierY, path.pierW, path.pierH);
      ctx.fillRect(path.rightX - path.pierW / 2, path.pierY, path.pierW, path.pierH);

      if (state.fakePiers && state.fakePiers.length) {
        for (const p of state.fakePiers) {
          ctx.fillRect(p.x - p.w / 2, p.y, p.w, p.h);
        }
      }
      return;
    }

    ctx.imageSmoothingEnabled = true;

    function drawPierAt(x, deckY, w) {
      const s = w / img.width;
      const dw = img.width * s;
      const dh = img.height * s;
      const deckOff = SPRITE_CFG.pierDeckY * s;
      const y = deckY - deckOff;
      ctx.drawImage(img, x - dw / 2, y, dw, dh);
    }

    drawPierAt(path.leftX, path.pierY, path.pierW);
    drawPierAt(path.rightX, path.pierY, path.pierW);

    if (state.fakePiers && state.fakePiers.length) {
      for (const p of state.fakePiers) {
        drawPierAt(p.x, p.y, p.w);
      }
    }
  }

  function drawTrajectory(path) {
    ctx.save();

    ctx.lineWidth = 6;
    ctx.strokeStyle = "rgba(102,227,255,0.10)";
    ctx.beginPath();
    for (let i = 0; i <= 140; i++) {
      const u = i / 140;
      const x = path.xAtU(u);
      const y = path.yAtU(u);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    ctx.lineWidth = 2;
    ctx.strokeStyle = "rgba(102,227,255,0.28)";
    ctx.beginPath();
    for (let i = 0; i <= 1000; i++) {
      const u = i / 1000;
      const x = path.xAtU(u);
      const y = path.yAtU(u);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    ctx.restore();
  }

  function drawPickupTexts(ts, viewLeft, viewTop, viewRight, viewBottom) {
    if (!state.pickupTexts || state.pickupTexts.length === 0) return;

    const dur = 900;
    const pad = 120;
    const l = viewLeft - pad;
    const r = viewRight + pad;
    const t = viewTop - pad;
    const b = viewBottom + pad;

    ctx.save();
    ctx.font = "800 22px system-ui, -apple-system, Segoe UI, Roboto, Arial";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    for (const p of state.pickupTexts) {
      const age = ts - p.t0;
      if (age < 0 || age > dur) continue;
      if (p.x < l || p.x > r || p.y < t || p.y > b) continue;

      const k = clamp(age / dur, 0, 1);
      const a = 1 - k;
      const lift = 26 * (1 - Math.pow(1 - k, 2));

      ctx.globalAlpha = a;
      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(0,0,0,0.35)";
      ctx.fillStyle = p.good ? "rgba(74, 222, 128, 0.95)" : "rgba(248, 113, 113, 0.95)";

      ctx.strokeText(p.text, p.x, p.y - lift);
      ctx.fillText(p.text, p.x, p.y - lift);
    }

    ctx.restore();
  }

  function drawDecorBonuses(viewLeft, viewTop, viewRight, viewBottom) {
    if (!state.decorBonuses || state.decorBonuses.length === 0) return;

    ctx.save();
    ctx.font = "700 15px system-ui, -apple-system, Segoe UI, Roboto, Arial";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const pad = 80;
    const l = viewLeft - pad;
    const r = viewRight + pad;
    const t = viewTop - pad;
    const b = viewBottom + pad;

    for (const d of state.decorBonuses) {
      if (d.x < l || d.x > r || d.y < t || d.y > b) continue;

      ctx.fillStyle = d.good ? "rgba(74, 222, 128, 0.28)" : "rgba(248, 113, 113, 0.24)";
      ctx.strokeStyle = d.good ? "rgba(74, 222, 128, 0.85)" : "rgba(248, 113, 113, 0.85)";
      ctx.lineWidth = 2;

      ctx.beginPath();
      ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "rgba(255,255,255,0.92)";
      ctx.fillText(formatBonus(d), d.x, d.y + 0.5);
    }

    ctx.restore();
  }

  function drawBonuses(path) {
    if (!state.bonuses || state.bonuses.length === 0) return;

    ctx.save();
    ctx.font = "700 15px system-ui, -apple-system, Segoe UI, Roboto, Arial";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    for (const b of state.bonuses) {
      if (b.taken) continue;
      const x = path.xAtU(b.u);
      const y = path.yAtU(b.u);
      const r = 14;

      ctx.fillStyle = b.good ? "rgba(74, 222, 128, 0.28)" : "rgba(248, 113, 113, 0.24)";
      ctx.strokeStyle = b.good ? "rgba(74, 222, 128, 0.85)" : "rgba(248, 113, 113, 0.85)";
      ctx.lineWidth = 2;

      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "rgba(255,255,255,0.92)";
      ctx.fillText(formatBonus(b), x, y + 0.5);
    }

    ctx.restore();
  }

  function drawPlane(x, y, ang) {
    const img = assets.plane;
    if (!img) {
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(ang);

      ctx.fillStyle = "rgba(102,227,255,0.16)";
      ctx.beginPath();
      ctx.ellipse(-22, 0, 16, 7, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "rgba(255,255,255,0.78)";
      ctx.beginPath();
      ctx.moveTo(-10, -5);
      ctx.lineTo(18, 0);
      ctx.lineTo(-10, 5);
      ctx.closePath();
      ctx.fill();

      ctx.fillStyle = "rgba(255,255,255,0.92)";
      ctx.beginPath();
      ctx.ellipse(-2, 0, 12, 6, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
      return;
    }

    const s = SPRITE_CFG.planeScale;
    const dw = img.width * s;
    const dh = img.height * s;

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(ang);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(img, -dw / 2, -dh / 2, dw, dh);
    ctx.restore();
  }

  function drawImageCover(img, x, y, w, h) {
    const iw = img.width;
    const ih = img.height;
    const s = Math.max(w / iw, h / ih);
    const dw = iw * s;
    const dh = ih * s;
    const dx = x + (w - dw) / 2;
    const dy = y + (h - dh) / 2;
    ctx.drawImage(img, dx, dy, dw, dh);
  }

  function drawScene(ts) {
    const w = canvas.getBoundingClientRect().width;
    const h = canvas.getBoundingClientRect().height;

    ctx.clearRect(0, 0, w, h);

    if (state.bgImg) {
      ctx.imageSmoothingEnabled = true;
      drawImageCover(state.bgImg, 0, 0, w, h);
      ctx.fillStyle = "rgba(0,0,0,0.12)";
      ctx.fillRect(0, 0, w, h);
    } else {
      const sky = ctx.createLinearGradient(0, 0, 0, h);
      sky.addColorStop(0, "rgba(102, 227, 255, 0.10)");
      sky.addColorStop(1, "rgba(0, 0, 0, 0.00)");
      ctx.fillStyle = sky;
      ctx.fillRect(0, 0, w, h);
    }

    if (!state.path) return;

    const path = state.path;
    const pose = getPlanePose();
    const zoom = CAMERA_ZOOM;
    const worldCenterX = pose.x;
    const worldCenterY = pose.y;
    const viewLeft = worldCenterX - w / (2 * zoom);
    const viewTop = worldCenterY - h / (2 * zoom);
    const viewRight = worldCenterX + w / (2 * zoom);
    const viewBottom = worldCenterY + h / (2 * zoom);

    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.scale(zoom, zoom);
    ctx.translate(-worldCenterX, -worldCenterY);

    const seaGrad = ctx.createLinearGradient(0, path.seaY, 0, path.seaY + h / zoom);
    seaGrad.addColorStop(0, "rgba(102, 227, 255, 0.14)");
    seaGrad.addColorStop(1, "rgba(0, 0, 0, 0.45)");
    ctx.fillStyle = seaGrad;
    ctx.fillRect(viewLeft - 600, path.seaY, (w / zoom) + 1200, (h / zoom) + 1200);

    for (let i = 0; i < 16; i++) {
      const u = i / 15;
      const x = viewLeft + u * (w / zoom) + Math.sin((ts / 700) + i) * 7;
      const y = path.seaY + 14 + Math.cos((ts / 900) + i * 0.8) * 6;
      ctx.strokeStyle = "rgba(255,255,255,0.07)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x - 26, y);
      ctx.quadraticCurveTo(x, y - 6, x + 26, y);
      ctx.stroke();
    }

    renderParticles();

    drawDecorBonuses(viewLeft, viewTop, viewRight, viewBottom);

    drawPiers(path);
    drawPickupTexts(ts, viewLeft, viewTop, viewRight, viewBottom);
    drawBonuses(path);

    ctx.restore();

    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.scale(zoom, zoom);
    drawPlane(0, 0, pose.ang);
    ctx.restore();

    if (state.phase !== "menu") {
      ctx.save();
      ctx.font = "900 42px system-ui, -apple-system, Segoe UI, Roboto, Arial";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = "rgba(255,255,255,0.95)";
      ctx.strokeStyle = "rgba(0,0,0,0.35)";
      ctx.lineWidth = 6;
      const txt = `⭐ ${Math.max(0, state.score).toFixed(2)}`;
      ctx.strokeText(txt, w / 2, 18);
      ctx.fillText(txt, w / 2, 18);
      ctx.restore();
    }
  }

  function step(ts) {
    requestAnimationFrame(step);

    if (!state.lastTs) state.lastTs = ts;
    const dt = ts - state.lastTs;
    state.lastTs = ts;

    if (state.running && state.path) {
      if (!state.startTs) state.startTs = ts;

      if (state.phase === "fly") {
        const p = clamp((ts - state.startTs) / state.durationMs, 0, 1);
        state.u = p;

        if (state.engineWillFail && state.engineFailU >= 0 && state.u >= state.engineFailU) {
          startCrash("engine", ts);
        }

        if (state.phase === "fly") {
          const pose = getPlanePose();
          const planeX = pose.x;
          const planeY = pose.y;
          const grabR = 34;

          state.pickupTexts = state.pickupTexts.filter((e) => ts - e.t0 < 900);

          for (const b of state.bonuses) {
            if (b.taken) continue;
            const bx = state.path.xAtU(b.u);
            const by = state.path.yAtU(b.u);
            const dx = bx - planeX;
            const dy = by - planeY;
            if (dx * dx + dy * dy <= grabR * grabR) {
              b.taken = true;
              state.pickupTexts.push({ x: bx, y: by, text: formatBonus(b), good: b.good, t0: ts });
              spawnStars(bx, by, b.good, (state.seed ^ ((b.u * 1000000) | 0)) >>> 0);
              applyBonus(b);
            }
          }

          if (p >= 1) {
            if (state.landWillOvershoot) {
              startCrash("landing", ts);
            } else {
              state.phase = "landed";
              state.landedAt = ts;
            }
          }
        }
      } else if (state.phase === "crashing" && state.plane) {
        const dtS = clamp(dt, 0, 50) / 1000;
        const g = 720;

        state.plane.vy += g * dtS;
        state.plane.x += state.plane.vx * dtS;
        state.plane.y += state.plane.vy * dtS;
        state.plane.ang += state.plane.spin * dtS;

        if (!state.plane.inWater && state.plane.y >= state.path.seaY) {
          state.plane.inWater = true;
          state.plane.vx *= 0.25;
          state.plane.vy = 40;
          spawnSplash(state.plane.x, state.path.seaY + 6, state.seed);
        }

        if (state.plane.inWater) {
          state.plane.vx *= 0.985;
          state.plane.vy = 40;
          state.plane.y += 26 * dtS;
          state.plane.ang += 0.6 * dtS;
        }

        if (state.plane.y > state.path.seaY + 220 || ts - state.plane.t0 > 4200) {
          state.running = false;
          state.phase = "menu";
          showMenu("result");
        }
      } else if (state.phase === "landed") {
        state.u = 1;
        state.altTarget = 0;
        state.altOffset += (state.altTarget - state.altOffset) * 0.18;
        if (ts - state.landedAt > 900) {
          state.running = false;
          state.phase = "menu";
          showMenu("result");
        }
      }
    }

    updateParticles(dt);

    drawScene(ts);
  }

  function init() {
    resize();
    window.addEventListener("resize", resize);

    parseLaunchFlags();

    let started = false;
    loadAssets()
      .catch(() => {
        assets.ready = false;
      })
      .finally(() => {
        if (started) return;
        started = true;

        if (state.limitReached) {
          showMenu("start");
          if (elMenuTitle) elMenuTitle.textContent = "Лимит исчерпан";
          if (elAdBtn) elAdBtn.hidden = true;
          state.closeTimer = setTimeout(() => {
            closeApp();
          }, 2500);
          return;
        }

        if (state.adMode) {
          showMenu("start");
          if (elMenuTitle) elMenuTitle.textContent = "Доп. попытка за рекламу";
          if (elAdBtn) {
            elAdBtn.hidden = false;
            elAdBtn.disabled = false;
            elAdBtn.textContent = "Смотреть рекламу";
            elAdBtn.onclick = async () => {
              if (elAdBtn.disabled) return;
              elAdBtn.disabled = true;
              elAdBtn.textContent = "Загрузка...";
              try {
                await showRewardAd();
              } catch (_) {
                closeApp();
                return;
              }
              elAdBtn.hidden = true;
              startGame();
            };
          } else {
            closeApp();
          }
          return;
        }

        startGame();
      });

    showMenu("start");
    requestAnimationFrame(step);
  }

  init();
})();
