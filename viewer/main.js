// paper-lineage viewer — 時間単調レイアウトの WebGL2 描画。
//
// 設計方針(docs/algorithms.md):
//  - ノード数 10^4〜10^5、エッジ 10^5〜10^6 を一度に描く。DOM は使わない。
//  - エッジは**加算合成 + 低 alpha**。重なった場所が明るくなるので、
//    「濃いところ = 太い流れ」が自動的に浮かび上がる。SPC 重みを alpha に載せる。
//  - レイアウトはオフラインで前計算済み(data/viz/*.bin)。ここでは動かさない。
//
// 座標系: 正規化座標 (0,0)=左上, (1,1)=右下 の**画面と同じ向き**に統一する。
//   シェーダ側で y を反転して合わせているので、マウス座標(clientY は下向きが正)を
//   そのまま使ってよい。これを揃えないとパン・ズーム・ホバーが全部縦に反転する。

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

// 選択状態。シェーダにも同じ数値を渡す。
const S_NONE = 0, S_UP = 1, S_DOWN = 2, S_SELF = 3;

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

// 正規化座標(左上原点)-> クリップ空間。y はここで反転する。
const VIEW = `
  uniform vec2 uScale;
  uniform vec2 uOffset;
  vec2 toClip(vec2 p) {
    vec2 f = p * uScale + uOffset;      // 画面上の割合 (0..1, 左上原点)
    return vec2(f.x * 2.0 - 1.0, 1.0 - f.y * 2.0);
  }
`;

const LINEAGE_COLORS = `
  const vec3 C_UP   = vec3(0.31, 0.82, 0.76);   // 遡る系譜(過去側)
  const vec3 C_DOWN = vec3(1.00, 0.60, 0.32);   // その後の系譜(未来側)
  const vec3 C_SELF = vec3(1.00, 1.00, 1.00);
`;

const EDGE_VS = `#version 300 es
  in vec2 aPos;
  in float aWeight;
  in float aState;
  ${VIEW}
  ${LINEAGE_COLORS}
  uniform float uThreshold;
  uniform float uAlpha;
  uniform float uSelActive;   // 0 = 選択なし
  uniform float uOnlyLineage; // 1 = 系譜以外を描かない
  out vec4 vColor;
  void main() {
    bool inLineage = aState > 0.5;
    if (aWeight < uThreshold && !inLineage) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }
    if (uSelActive > 0.5 && uOnlyLineage > 0.5 && !inLineage) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }

    // 重みが大きいほど濃く。重み0のエッジも薄く残す(全体の地形として意味がある)
    float a = uAlpha * (0.25 + 0.75 * aWeight);
    vec3 c = vec3(0.35, 0.55, 0.95);
    if (uSelActive > 0.5) {
      if (aState < 0.5) { a *= 0.12; }                       // 系譜外は沈める
      else {
        c = aState < 1.5 ? C_UP : C_DOWN;
        a = max(a, 0.30) * 2.2;                              // 系譜は必ず見えるように
      }
    }
    vColor = vec4(c, a);
    gl_Position = vec4(toClip(aPos), 0.0, 1.0);
  }`;

const EDGE_FS = `#version 300 es
  precision highp float;
  in vec4 vColor;
  out vec4 outColor;
  void main() { outColor = vec4(vColor.rgb, 1.0) * vColor.a; }`;

const NODE_VS = `#version 300 es
  in vec2 aPos;
  in vec3 aColor;
  in float aMag;      // log(1 + cited_by) を 0..1 に正規化したもの
  in float aState;
  ${VIEW}
  ${LINEAGE_COLORS}
  uniform float uPointSize;
  uniform float uSelActive;
  uniform float uOnlyLineage;
  out vec3 vColor;
  out float vAlpha;
  void main() {
    bool inLineage = aState > 0.5;
    if (uSelActive > 0.5 && uOnlyLineage > 0.5 && !inLineage) { gl_Position = vec4(2.0); return; }
    gl_Position = vec4(toClip(aPos), 0.0, 1.0);
    float size = uPointSize * (0.7 + 1.8 * aMag);
    vColor = aColor;
    vAlpha = 0.85;
    if (uSelActive > 0.5) {
      if (aState < 0.5) { vAlpha = 0.13; }
      else if (aState < 1.5) { vColor = C_UP; size *= 1.5; }
      else if (aState < 2.5) { vColor = C_DOWN; size *= 1.5; }
      else { vColor = C_SELF; size *= 4.0; }
    }
    gl_PointSize = size;
  }`;

const NODE_FS = `#version 300 es
  precision highp float;
  in vec3 vColor;
  in float vAlpha;
  out vec4 outColor;
  void main() {
    vec2 d = gl_PointCoord - vec2(0.5);
    if (dot(d, d) > 0.25) discard;
    outColor = vec4(vColor, vAlpha);
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

// 隣接リストを CSR で持つ(クリック時の BFS 用)。
function buildCSR(edges, n, forward) {
  const m = edges.length / 2;
  const counts = new Uint32Array(n);
  for (let e = 0; e < m; e++) counts[edges[e * 2 + (forward ? 0 : 1)]]++;
  const start = new Uint32Array(n + 1);
  for (let i = 0; i < n; i++) start[i + 1] = start[i] + counts[i];
  const cursor = start.slice(0, n);
  const list = new Uint32Array(m);
  const eid = new Uint32Array(m);
  for (let e = 0; e < m; e++) {
    const from = edges[e * 2 + (forward ? 0 : 1)];
    const to = edges[e * 2 + (forward ? 1 : 0)];
    const at = cursor[from]++;
    list[at] = to;
    eid[at] = e;
  }
  return { start, list, eid };
}

// ---------- 本体 ----------

const canvas = document.getElementById('canvas');
const statsEl = document.getElementById('stats');
const tooltip = document.getElementById('tooltip');
const axisEl = document.getElementById('axis');
const lineageEl = document.getElementById('lineage');

const escapeHtml = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

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

  const outAdj = buildCSR(edges, n, true);   // 引用された -> 引用した(未来方向)
  const inAdj = buildCSR(edges, n, false);   // 引用した -> 引用された(過去方向)

  const gl = canvas.getContext('webgl2', { antialias: true, alpha: false });
  if (!gl) { statsEl.textContent = 'WebGL2 が使えません'; return; }

  const edgeProg = program(gl, EDGE_VS, EDGE_FS);
  const nodeProg = program(gl, NODE_VS, NODE_FS);

  function buffer(src, usage) {
    const b = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, src, usage || gl.STATIC_DRAW);
    return b;
  }
  function attrib(prog, name, buf, size) {
    const loc = gl.getAttribLocation(prog, name);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0);
  }

  // 選択状態(クリックのたびに書き換える)
  const nodeState = new Float32Array(n);
  const edgeState = new Float32Array(edgeCount * 2);
  const nodeStateBuf = buffer(nodeState, gl.DYNAMIC_DRAW);
  const edgeStateBuf = buffer(edgeState, gl.DYNAMIC_DRAW);

  const edgeVao = gl.createVertexArray();
  gl.bindVertexArray(edgeVao);
  attrib(edgeProg, 'aPos', buffer(edgePos), 2);
  attrib(edgeProg, 'aWeight', buffer(edgeW), 1);
  attrib(edgeProg, 'aState', edgeStateBuf, 1);

  const nodeVao = gl.createVertexArray();
  gl.bindVertexArray(nodeVao);
  attrib(nodeProg, 'aPos', buffer(np), 2);
  attrib(nodeProg, 'aColor', buffer(colors), 3);
  attrib(nodeProg, 'aMag', buffer(mags), 1);
  attrib(nodeProg, 'aState', nodeStateBuf, 1);
  gl.bindVertexArray(null);

  const uni = (p, name) => gl.getUniformLocation(p, name);

  // --- カメラ ---
  const cam = { zoom: 1, cx: 0.5, cy: 0.5 };  // cx,cy = 画面中心にくる正規化座標
  const PAD = 0.04;

  function scaleOffset() {
    const s = cam.zoom * (1 - 2 * PAD);
    return { scale: [s, s], offset: [0.5 - cam.cx * s, 0.5 - cam.cy * s] };
  }
  // 画面座標(px) -> 正規化座標。逆変換はこの1箇所だけに閉じ込める。
  function screenToNorm(clientX, clientY) {
    const { scale, offset } = scaleOffset();
    return [
      (clientX / canvas.clientWidth - offset[0]) / scale[0],
      (clientY / canvas.clientHeight - offset[1]) / scale[1],
    ];
  }

  // 指定ノード群が画面に収まるようにカメラを合わせる。
  // 左右のパネルに隠れないよう、使える範囲を実際のパネル幅から決める。
  function fitTo(indices) {
    if (!indices.length) return;
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const i of indices) {
      const x = np[i * 2], y = np[i * 2 + 1];
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const left = (document.getElementById('controls').offsetWidth + 32) / W;
    const right = 1 - (lineageEl.offsetWidth + 32) / W;
    const top = 0.04, bottom = 0.92;

    const dx = Math.max(x1 - x0, 1e-3), dy = Math.max(y1 - y0, 1e-3);
    const s = Math.min((right - left) / dx, (bottom - top) / dy);
    cam.zoom = Math.min(400, Math.max(0.5, s / (1 - 2 * PAD)));

    const sc = scaleOffset().scale;
    cam.cx = (x0 + x1) / 2 - ((left + right) / 2 - 0.5) / sc[0];
    cam.cy = (y0 + y1) / 2 - ((top + bottom) / 2 - 0.5) / sc[1];
  }

  const ui = {
    thresh: document.getElementById('thresh'),
    alpha: document.getElementById('alpha'),
    psize: document.getElementById('psize'),
    depth: document.getElementById('depth'),
    only: document.getElementById('only'),
  };

  let selected = -1;
  let camBeforeSelect = null;  // 選択解除で元の全体ビューに戻せるように覚えておく

  function render() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.floor(canvas.clientWidth * dpr), h = Math.floor(canvas.clientHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0.027, 0.031, 0.047, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);

    const { scale, offset } = scaleOffset();
    const selActive = selected >= 0 ? 1 : 0;
    const onlyLineage = ui.only.checked ? 1 : 0;

    // エッジ: 加算合成。重なりが明るくなる = 太い流れが浮かぶ。
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.useProgram(edgeProg);
    gl.uniform2fv(uni(edgeProg, 'uScale'), scale);
    gl.uniform2fv(uni(edgeProg, 'uOffset'), offset);
    gl.uniform1f(uni(edgeProg, 'uThreshold'), parseFloat(ui.thresh.value));
    gl.uniform1f(uni(edgeProg, 'uAlpha'), parseFloat(ui.alpha.value));
    gl.uniform1f(uni(edgeProg, 'uSelActive'), selActive);
    gl.uniform1f(uni(edgeProg, 'uOnlyLineage'), onlyLineage);
    gl.bindVertexArray(edgeVao);
    gl.drawArrays(gl.LINES, 0, edgeCount * 2);

    // ノード: 通常合成で上に重ねる
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(nodeProg);
    gl.uniform2fv(uni(nodeProg, 'uScale'), scale);
    gl.uniform2fv(uni(nodeProg, 'uOffset'), offset);
    gl.uniform1f(uni(nodeProg, 'uPointSize'), parseFloat(ui.psize.value) * dpr);
    gl.uniform1f(uni(nodeProg, 'uSelActive'), selActive);
    gl.uniform1f(uni(nodeProg, 'uOnlyLineage'), onlyLineage);
    gl.bindVertexArray(nodeVao);
    gl.drawArrays(gl.POINTS, 0, n);
    gl.bindVertexArray(null);

    drawAxis();
  }

  let frame = null;
  const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = null; render(); }); };

  // --- 年軸のラベル ---
  function drawAxis() {
    const { scale, offset } = scaleOffset();
    const step = cam.zoom > 6 ? 1 : cam.zoom > 3 ? 2 : cam.zoom > 1.5 ? 5 : 10;
    const parts = [];
    for (let year = Math.ceil(yearMin / step) * step; year <= yearMax; year += step) {
      const px = (((year - xMin) / xSpan) * scale[0] + offset[0]) * canvas.clientWidth;
      if (px < -20 || px > canvas.clientWidth + 20) continue;
      parts.push(`<div style="left:${px.toFixed(1)}px">${year}</div>`);
    }
    axisEl.innerHTML = parts.join('');
  }

  // --- 系譜(選択した論文の上流・下流)---
  function bfs(startNode, adj, maxDepth) {
    const seen = new Set([startNode]);
    let frontier = [startNode];
    for (let d = 0; d < maxDepth && frontier.length; d++) {
      const next = [];
      for (const v of frontier) {
        for (let k = adj.start[v]; k < adj.start[v + 1]; k++) {
          const u = adj.list[k];
          if (!seen.has(u)) { seen.add(u); next.push(u); }
        }
      }
      frontier = next;
    }
    seen.delete(startNode);
    return seen;
  }

  function select(i, keepCamera) {
    if (i >= 0 && selected < 0) camBeforeSelect = { ...cam };
    selected = i;
    nodeState.fill(0);
    edgeState.fill(0);

    if (i < 0) {
      lineageEl.style.display = 'none';
      if (camBeforeSelect) { Object.assign(cam, camBeforeSelect); camBeforeSelect = null; }
    } else {
      const depthRaw = parseInt(ui.depth.value, 10);
      const maxDepth = depthRaw >= 9 ? 1e9 : depthRaw;
      const up = bfs(i, inAdj, maxDepth);     // 過去方向 = この論文が(間接的に)引用しているもの
      const down = bfs(i, outAdj, maxDepth);  // 未来方向 = この論文を(間接的に)引用したもの

      for (const v of up) nodeState[v] = S_UP;
      for (const v of down) nodeState[v] = S_DOWN;
      nodeState[i] = S_SELF;

      // エッジは「両端がその系譜に属する」ものだけを系譜エッジとする
      const inUp = (v) => v === i || up.has(v);
      const inDown = (v) => v === i || down.has(v);
      for (let e = 0; e < edgeCount; e++) {
        const a = edges[e * 2], b = edges[e * 2 + 1];
        let st = 0;
        if (inUp(a) && inUp(b)) st = S_UP;
        else if (inDown(a) && inDown(b)) st = S_DOWN;
        if (st) { edgeState[e * 2] = st; edgeState[e * 2 + 1] = st; }
      }
      showLineagePanel(i, up, down);
      if (!keepCamera) fitTo([i, ...up, ...down]);
    }

    gl.bindBuffer(gl.ARRAY_BUFFER, nodeStateBuf);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, nodeState);
    gl.bindBuffer(gl.ARRAY_BUFFER, edgeStateBuf);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, edgeState);
    schedule();
  }

  function listHtml(title, ids, limit) {
    if (!ids.length) return '';
    const rows = ids
      .slice(0, limit)
      .map((v) => {
        const nd = meta.nodes[v];
        return `<li data-i="${v}"><span class="y">${nd.y}</span>${escapeHtml(nd.t.slice(0, 90))}</li>`;
      })
      .join('');
    const more = ids.length > limit ? `<li style="color:#5d6478">… 他 ${ids.length - limit} 本</li>` : '';
    return `<h3>${title}</h3><ol>${rows}${more}</ol>`;
  }

  function showLineagePanel(i, up, down) {
    const nd = meta.nodes[i];
    document.getElementById('selTitle').textContent = nd.t;
    document.getElementById('selMeta').textContent =
      `${nd.y} · ${(nd.v || '?').toUpperCase()} · 被引用 ${nd.c}`;
    document.getElementById('upCount').textContent = up.size.toLocaleString();
    document.getElementById('downCount').textContent = down.size.toLocaleString();

    // 被引用数の多い順に、代表だけ出す(全部出すと数千件になる)
    const byCited = (a, b) => (meta.nodes[b].c || 0) - (meta.nodes[a].c || 0);
    const upIds = [...up].sort(byCited);
    const downIds = [...down].sort(byCited);
    document.getElementById('lineageLists').innerHTML =
      listHtml('遡る系譜(よく引用されているもの順)', upIds, 15) +
      listHtml('その後の系譜(よく引用されているもの順)', downIds, 15);
    lineageEl.style.display = 'block';
    lineageEl.scrollTop = 0;
  }

  document.getElementById('lineageLists').addEventListener('click', (e) => {
    const li = e.target.closest('li[data-i]');
    if (li) select(parseInt(li.dataset.i, 10));
  });
  document.getElementById('lineageClose').addEventListener('click', () => select(-1));

  // --- 操作 ---
  let dragging = false, lastX = 0, lastY = 0, downX = 0, downY = 0;
  canvas.addEventListener('pointerdown', (e) => {
    dragging = true;
    lastX = downX = e.clientX; lastY = downY = e.clientY;
    canvas.classList.add('dragging'); canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointerup', (e) => {
    dragging = false;
    canvas.classList.remove('dragging');
    canvas.releasePointerCapture(e.pointerId);
    // ほとんど動いていなければクリックとして扱う
    if (Math.abs(e.clientX - downX) < 4 && Math.abs(e.clientY - downY) < 4) {
      const hit = pick(e.clientX, e.clientY);
      select(hit);
    }
  });
  canvas.addEventListener('pointermove', (e) => {
    if (dragging) {
      const { scale } = scaleOffset();
      // 画面と正規化座標の向きが揃っているので、ドラッグ量をそのまま引けばよい
      cam.cx -= (e.clientX - lastX) / canvas.clientWidth / scale[0];
      cam.cy -= (e.clientY - lastY) / canvas.clientHeight / scale[1];
      lastX = e.clientX; lastY = e.clientY;
      tooltip.style.display = 'none';
      schedule();
    } else {
      hover(e);
    }
  });
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    // カーソル下の正規化座標を固定したままズームする
    const [ux, uy] = screenToNorm(e.clientX, e.clientY);
    cam.zoom = Math.min(400, Math.max(0.5, cam.zoom * Math.exp(-e.deltaY * 0.002)));
    const s = scaleOffset().scale;
    cam.cx = ux - (e.clientX / canvas.clientWidth - 0.5) / s[0];
    cam.cy = uy - (e.clientY / canvas.clientHeight - 0.5) / s[1];
    schedule();
  }, { passive: false });
  window.addEventListener('resize', schedule);

  // --- 最近傍探索(均等グリッド) ---
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

  function pick(clientX, clientY) {
    const { scale } = scaleOffset();
    const [ux, uy] = screenToNorm(clientX, clientY);
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
    return bestD <= 1 ? best : -1;
  }

  function hover(e) {
    const i = pick(e.clientX, e.clientY);
    if (i < 0) { tooltip.style.display = 'none'; return; }
    const nd = meta.nodes[i];
    tooltip.innerHTML =
      `<div class="t">${escapeHtml(nd.t)}</div>` +
      `<div class="m">${nd.y} · ${(nd.v || '?').toUpperCase()} · 被引用 ${nd.c}</div>`;
    tooltip.style.display = 'block';
    tooltip.style.left = Math.min(e.clientX + 14, window.innerWidth - 400) + 'px';
    tooltip.style.top = Math.min(e.clientY + 14, window.innerHeight - 80) + 'px';
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
  ui.depth.addEventListener('input', () => {
    const v = parseInt(ui.depth.value, 10);
    document.getElementById('depthVal').textContent = v >= 9 ? '全部' : `${v}ホップ`;
    if (selected >= 0) select(selected);
  });
  ui.only.addEventListener('change', schedule);
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') select(-1); });

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
