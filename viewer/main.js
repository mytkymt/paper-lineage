// paper-lineage viewer — 時間単調レイアウトの WebGL2 描画。
//
// 設計方針(docs/algorithms.md):
//  - ノード数 10^4〜10^5、エッジ 10^5〜10^6 を一度に描く。DOM は使わない。
//  - エッジは**加算合成 + 低 alpha**。重なった場所が明るくなるので、
//    「濃いところ = 太い流れ」が自動的に浮かび上がる。SPC 重みを alpha に載せる。
//  - レイアウトはオフラインで前計算済み(data/viz/*.bin)。ここでは動かさない。

const DATA = '../data/viz/';

const VENUE_COLORS = {
  chi:       [0.42, 0.68, 1.00],
  pacmhci:   [0.55, 0.55, 0.98],
  uist:      [1.00, 0.62, 0.29],
  dis:       [0.36, 0.86, 0.68],
  assets:    [0.98, 0.45, 0.60],
  iui:       [0.85, 0.72, 0.32],
  cscw:      [0.62, 0.78, 0.45],
  tei:       [0.90, 0.52, 0.92],
  imwut:     [0.40, 0.82, 0.92],
  ubicomp:   [0.32, 0.62, 0.72],
  chiplay:   [0.95, 0.80, 0.45],
  mobilehci: [0.70, 0.60, 0.85],
  tochi:     [0.75, 0.75, 0.80],
};
const DEFAULT_COLOR = [0.55, 0.58, 0.65];

// ---------- WebGL ヘルパ ----------

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(s) || 'shader compile failed');
  }
  return s;
}

function program(gl, vs, fs) {
  const p = gl.createProgram();
  gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, vs));
  gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(p) || 'program link failed');
  }
  return p;
}

// view: 正規化座標 [0,1]^2 -> クリップ空間。scale/offset はパン・ズーム。
const VIEW = `
  uniform vec2 uScale;
  uniform vec2 uOffset;
  vec2 toClip(vec2 p) { return (p * uScale + uOffset) * 2.0 - 1.0; }
`;

const EDGE_VS = `#version 300 es
  in vec2 aPos;
  in float aWeight;
  ${VIEW}
  uniform float uThreshold;
  uniform float uAlpha;
  out float vAlpha;
  void main() {
    // 閾値未満のエッジは画面外に飛ばして描画しない(discard より安い)
    if (aWeight < uThreshold) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); vAlpha = 0.0; return; }
    // 重みが大きいほど濃く。重み0のエッジも薄く残す(全体の地形として意味がある)
    vAlpha = uAlpha * (0.25 + 0.75 * aWeight);
    gl_Position = vec4(toClip(aPos), 0.0, 1.0);
  }`;

const EDGE_FS = `#version 300 es
  precision highp float;
  in float vAlpha;
  out vec4 outColor;
  void main() { outColor = vec4(0.35, 0.55, 0.95, 1.0) * vAlpha; }`;

const NODE_VS = `#version 300 es
  in vec2 aPos;
  in vec3 aColor;
  in float aMag;      // log(1 + cited_by) を 0..1 に正規化したもの
  ${VIEW}
  uniform float uPointSize;
  out vec3 vColor;
  void main() {
    gl_Position = vec4(toClip(aPos), 0.0, 1.0);
    gl_PointSize = uPointSize * (0.7 + 1.8 * aMag);
    vColor = aColor;
  }`;

const NODE_FS = `#version 300 es
  precision highp float;
  in vec3 vColor;
  out vec4 outColor;
  void main() {
    vec2 d = gl_PointCoord - vec2(0.5);
    float r = dot(d, d);
    if (r > 0.25) discard;
    outColor = vec4(vColor, 0.85);
  }`;

// ---------- データ読み込み ----------

async function fetchBuffer(name) {
  const res = await fetch(DATA + name);
  if (!res.ok) throw new Error(`${name} を読めません (${res.status})。pipeline の layout.py を先に実行してください。`);
  return res.arrayBuffer();
}

async function load() {
  const [posBuf, edgeBuf, wBuf, metaRes] = await Promise.all([
    fetchBuffer('nodes.bin'),
    fetchBuffer('edges.bin'),
    fetchBuffer('weights.bin'),
    fetch(DATA + 'meta.json'),
  ]);
  if (!metaRes.ok) throw new Error('meta.json を読めません');
  return {
    pos: new Float32Array(posBuf),
    edges: new Uint32Array(edgeBuf),
    weights: new Float32Array(wBuf),
    meta: await metaRes.json(),
  };
}

// ---------- 本体 ----------

const canvas = document.getElementById('canvas');
const statsEl = document.getElementById('stats');
const tooltip = document.getElementById('tooltip');
const axisEl = document.getElementById('axis');

async function main() {
  let data;
  try {
    data = await load();
  } catch (e) {
    statsEl.textContent = e.message;
    return;
  }
  const { pos, edges, weights, meta } = data;
  const n = meta.node_count;
  const yearMin = meta.year_min, yearMax = meta.year_max;
  const yearSpan = Math.max(1, yearMax - yearMin);

  // x(年)を [0,1] に正規化。y は前計算時点で既に [0,1]。
  // 年内 jitter があるので実際の値域から取る(年の境界をわずかに超えるため)。
  let xMin = Infinity, xMax = -Infinity;
  for (let i = 0; i < n; i++) {
    const v = pos[i * 2];
    if (v < xMin) xMin = v;
    if (v > xMax) xMax = v;
  }
  const xSpan = Math.max(1e-6, xMax - xMin);
  const np = new Float32Array(n * 2);
  for (let i = 0; i < n; i++) {
    np[i * 2] = (pos[i * 2] - xMin) / xSpan;
    np[i * 2 + 1] = pos[i * 2 + 1];
  }

  // エッジ用に頂点を展開(LINES は頂点2つで1本)
  const edgeCount = edges.length / 2;
  const edgePos = new Float32Array(edgeCount * 4);
  const edgeW = new Float32Array(edgeCount * 2);
  for (let e = 0; e < edgeCount; e++) {
    const a = edges[e * 2], b = edges[e * 2 + 1];
    edgePos[e * 4] = np[a * 2];     edgePos[e * 4 + 1] = np[a * 2 + 1];
    edgePos[e * 4 + 2] = np[b * 2]; edgePos[e * 4 + 3] = np[b * 2 + 1];
    edgeW[e * 2] = weights[e];      edgeW[e * 2 + 1] = weights[e];
  }

  // ノードの色と大きさ
  const colors = new Float32Array(n * 3);
  const mags = new Float32Array(n);
  let maxMag = 0;
  for (let i = 0; i < n; i++) {
    const m = Math.log1p(meta.nodes[i].c || 0);
    mags[i] = m;
    if (m > maxMag) maxMag = m;
  }
  for (let i = 0; i < n; i++) {
    const c = VENUE_COLORS[meta.nodes[i].v] || DEFAULT_COLOR;
    colors[i * 3] = c[0]; colors[i * 3 + 1] = c[1]; colors[i * 3 + 2] = c[2];
    mags[i] = maxMag > 0 ? mags[i] / maxMag : 0;
  }

  const gl = canvas.getContext('webgl2', { antialias: true, alpha: false });
  if (!gl) { statsEl.textContent = 'WebGL2 が使えません'; return; }

  const edgeProg = program(gl, EDGE_VS, EDGE_FS);
  const nodeProg = program(gl, NODE_VS, NODE_FS);

  function buffer(target, src) {
    const b = gl.createBuffer();
    gl.bindBuffer(target, b);
    gl.bufferData(target, src, gl.STATIC_DRAW);
    return b;
  }

  // --- エッジ VAO ---
  const edgeVao = gl.createVertexArray();
  gl.bindVertexArray(edgeVao);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer(gl.ARRAY_BUFFER, edgePos));
  const eLocPos = gl.getAttribLocation(edgeProg, 'aPos');
  gl.enableVertexAttribArray(eLocPos);
  gl.vertexAttribPointer(eLocPos, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer(gl.ARRAY_BUFFER, edgeW));
  const eLocW = gl.getAttribLocation(edgeProg, 'aWeight');
  gl.enableVertexAttribArray(eLocW);
  gl.vertexAttribPointer(eLocW, 1, gl.FLOAT, false, 0, 0);

  // --- ノード VAO ---
  const nodeVao = gl.createVertexArray();
  gl.bindVertexArray(nodeVao);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer(gl.ARRAY_BUFFER, np));
  const nLocPos = gl.getAttribLocation(nodeProg, 'aPos');
  gl.enableVertexAttribArray(nLocPos);
  gl.vertexAttribPointer(nLocPos, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer(gl.ARRAY_BUFFER, colors));
  const nLocCol = gl.getAttribLocation(nodeProg, 'aColor');
  gl.enableVertexAttribArray(nLocCol);
  gl.vertexAttribPointer(nLocCol, 3, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer(gl.ARRAY_BUFFER, mags));
  const nLocMag = gl.getAttribLocation(nodeProg, 'aMag');
  gl.enableVertexAttribArray(nLocMag);
  gl.vertexAttribPointer(nLocMag, 1, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);

  // --- カメラ ---
  const cam = { zoom: 1, cx: 0.5, cy: 0.5 };  // cx,cy = 画面中心の正規化座標
  const PAD = 0.04;

  function scaleOffset() {
    const sx = cam.zoom * (1 - 2 * PAD), sy = cam.zoom * (1 - 2 * PAD);
    return {
      scale: [sx, sy],
      offset: [0.5 - cam.cx * sx, 0.5 - cam.cy * sy],
    };
  }

  const ui = {
    thresh: document.getElementById('thresh'),
    alpha: document.getElementById('alpha'),
    psize: document.getElementById('psize'),
  };

  function render() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.floor(canvas.clientWidth * dpr), h = Math.floor(canvas.clientHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0.027, 0.031, 0.047, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);

    const { scale, offset } = scaleOffset();
    const threshold = parseFloat(ui.thresh.value);

    // エッジ: 加算合成。重なりが明るくなる = 太い流れが浮かぶ。
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.useProgram(edgeProg);
    gl.uniform2fv(gl.getUniformLocation(edgeProg, 'uScale'), scale);
    gl.uniform2fv(gl.getUniformLocation(edgeProg, 'uOffset'), offset);
    gl.uniform1f(gl.getUniformLocation(edgeProg, 'uThreshold'), threshold);
    gl.uniform1f(gl.getUniformLocation(edgeProg, 'uAlpha'), parseFloat(ui.alpha.value));
    gl.bindVertexArray(edgeVao);
    gl.drawArrays(gl.LINES, 0, edgeCount * 2);

    // ノード: 通常合成で上に重ねる
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(nodeProg);
    gl.uniform2fv(gl.getUniformLocation(nodeProg, 'uScale'), scale);
    gl.uniform2fv(gl.getUniformLocation(nodeProg, 'uOffset'), offset);
    gl.uniform1f(gl.getUniformLocation(nodeProg, 'uPointSize'), parseFloat(ui.psize.value) * dpr);
    gl.bindVertexArray(nodeVao);
    gl.drawArrays(gl.POINTS, 0, n);
    gl.bindVertexArray(null);

    drawAxis();
  }

  let frame = null;
  function schedule() { if (!frame) frame = requestAnimationFrame(() => { frame = null; render(); }); }

  // --- 年軸のラベル ---
  function drawAxis() {
    const { scale, offset } = scaleOffset();
    const step = cam.zoom > 6 ? 1 : cam.zoom > 3 ? 2 : cam.zoom > 1.5 ? 5 : 10;
    const parts = [];
    for (let year = Math.ceil(yearMin / step) * step; year <= yearMax; year += step) {
      const nx = (year - xMin) / xSpan;
      const px = (nx * scale[0] + offset[0]) * canvas.clientWidth;
      if (px < -20 || px > canvas.clientWidth + 20) continue;
      parts.push(`<div style="left:${px.toFixed(1)}px">${year}</div>`);
    }
    axisEl.innerHTML = parts.join('');
  }

  // --- 操作 ---
  let dragging = false, lastX = 0, lastY = 0;
  canvas.addEventListener('pointerdown', (e) => {
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    canvas.classList.add('dragging'); canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointerup', (e) => {
    dragging = false; canvas.classList.remove('dragging'); canvas.releasePointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', (e) => {
    if (dragging) {
      const { scale } = scaleOffset();
      cam.cx -= (e.clientX - lastX) / canvas.clientWidth / scale[0];
      cam.cy -= (e.clientY - lastY) / canvas.clientHeight / scale[1];
      lastX = e.clientX; lastY = e.clientY;
      schedule();
      tooltip.style.display = 'none';
    } else {
      hover(e);
    }
  });
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const { scale, offset } = scaleOffset();
    // カーソル位置を固定してズーム
    const ux = (e.clientX / canvas.clientWidth - offset[0]) / scale[0];
    const uy = (e.clientY / canvas.clientHeight - offset[1]) / scale[1];
    const factor = Math.exp(-e.deltaY * 0.002);
    cam.zoom = Math.min(400, Math.max(0.5, cam.zoom * factor));
    const after = scaleOffset();
    cam.cx = ux - (e.clientX / canvas.clientWidth - 0.5) / after.scale[0];
    cam.cy = uy - (e.clientY / canvas.clientHeight - 0.5) / after.scale[1];
    schedule();
  }, { passive: false });
  window.addEventListener('resize', schedule);

  // --- ホバー(均等グリッドで最近傍探索) ---
  const GRID = 512;
  const grid = new Map();
  for (let i = 0; i < n; i++) {
    const gx = Math.min(GRID - 1, Math.max(0, (np[i * 2] * GRID) | 0));
    const gy = Math.min(GRID - 1, Math.max(0, (np[i * 2 + 1] * GRID) | 0));
    const key = gy * GRID + gx;
    let cell = grid.get(key);
    if (!cell) grid.set(key, (cell = []));
    cell.push(i);
  }

  function hover(e) {
    const { scale, offset } = scaleOffset();
    const ux = (e.clientX / canvas.clientWidth - offset[0]) / scale[0];
    const uy = (e.clientY / canvas.clientHeight - offset[1]) / scale[1];
    // 画面上 12px を正規化座標に直したものを探索半径にする
    const rx = 12 / canvas.clientWidth / scale[0];
    const ry = 12 / canvas.clientHeight / scale[1];
    const g0x = Math.max(0, ((ux - rx) * GRID) | 0), g1x = Math.min(GRID - 1, ((ux + rx) * GRID) | 0);
    const g0y = Math.max(0, ((uy - ry) * GRID) | 0), g1y = Math.min(GRID - 1, ((uy + ry) * GRID) | 0);

    let best = -1, bestD = Infinity;
    for (let gy = g0y; gy <= g1y; gy++) {
      for (let gx = g0x; gx <= g1x; gx++) {
        const cell = grid.get(gy * GRID + gx);
        if (!cell) continue;
        for (const i of cell) {
          const dx = (np[i * 2] - ux) / rx, dy = (np[i * 2 + 1] - uy) / ry;
          const d = dx * dx + dy * dy;
          if (d < bestD) { bestD = d; best = i; }
        }
      }
    }
    if (best < 0 || bestD > 1) { tooltip.style.display = 'none'; return; }
    const nd = meta.nodes[best];
    tooltip.innerHTML =
      `<div class="t">${escapeHtml(nd.t)}</div>` +
      `<div class="m">${nd.y} · ${(nd.v || '?').toUpperCase()} · 被引用 ${nd.c}</div>`;
    tooltip.style.display = 'block';
    tooltip.style.left = Math.min(e.clientX + 14, window.innerWidth - 400) + 'px';
    tooltip.style.top = (e.clientY + 14) + 'px';
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  // --- UI ---
  const fmt = (v) => Number(v).toFixed(2).replace(/^0/, '');
  ui.thresh.addEventListener('input', () => {
    const v = parseFloat(ui.thresh.value);
    document.getElementById('threshVal').textContent = v === 0 ? '全部' : `≥${fmt(v)}`;
    schedule();
  });
  ui.alpha.addEventListener('input', () => {
    document.getElementById('alphaVal').textContent = fmt(ui.alpha.value);
    schedule();
  });
  ui.psize.addEventListener('input', () => {
    document.getElementById('psizeVal').textContent = Number(ui.psize.value).toFixed(1);
    schedule();
  });

  const venueCounts = {};
  for (const nd of meta.nodes) venueCounts[nd.v] = (venueCounts[nd.v] || 0) + 1;
  document.getElementById('legend').innerHTML = Object.entries(venueCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([v, c]) => {
      const col = VENUE_COLORS[v] || DEFAULT_COLOR;
      const rgb = col.map((x) => Math.round(x * 255)).join(',');
      return `<span><i style="background:rgb(${rgb})"></i>${(v || '?').toUpperCase()} ${c}</span>`;
    })
    .join('');

  statsEl.textContent =
    `${n.toLocaleString()} 本 / ${edgeCount.toLocaleString()} 引用 · ${yearMin}–${yearMax} · layout=${meta.mode}`;

  render();
}

main();
