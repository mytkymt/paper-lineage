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
const S_NONE = 0, S_UP = 1, S_DOWN = 2, S_SELF = 3, S_MATCH = 4;

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
  const vec3 C_UP    = vec3(0.31, 0.82, 0.76);   // 遡る系譜(過去側)
  const vec3 C_DOWN  = vec3(1.00, 0.60, 0.32);   // その後の系譜(未来側)
  const vec3 C_SELF  = vec3(1.00, 1.00, 1.00);
  const vec3 C_MATCH = vec3(1.00, 0.90, 0.35);   // 検索ヒット
`;

// ラボ(= ラストオーサー)ごとの色。位置が「いつ・どのトレンドか」を既に表しているので、
// 色は位置が表現していない情報 = 誰の系譜かに使う。
//
// 配色は dataviz リファレンスパレットの dark ステップをその順序のまま。
// カテゴリカルは 8 スロットが上限で、9個目以降は色相を作らず「その他のラボ」に畳む。
// 隣接ペア基準では全スロット合格(最悪 CVD ΔE 8.4)。ラボの線は帯ごとに離れて出るので
// この基準で妥当だが、6–8 の帯域は**二次符号化が必須**なので凡例のクリック絞り込みを付ける。
const LAB_HEX = ['#3987e5', '#d95926', '#199e70', '#c98500',
                 '#d55181', '#008300', '#9085e9', '#e66767'];
const LAB_OTHER = '#59617a';   // 9位以下のラボ(色付き8ラボを埋めないよう暗め)
const NON_LAB = [0.16, 0.19, 0.26];  // ラボ線ではないエッジ
const NO_LAB = 0xFFFFFFFF;

// 色を付ける人はユーザーが検索して選ぶ。既定は自己引用系譜が長い順に上位8人。
// 「その人の論文」(点)と「その人のラボ系譜」(線)は別物なので、両方まとめて色を付ける。
let pinned = [];            // [{ai: 著者index, labId: labs index|null}] 最大 8

const hexToRgb = (h) => [
  parseInt(h.slice(1, 3), 16) / 255,
  parseInt(h.slice(3, 5), 16) / 255,
  parseInt(h.slice(5, 7), 16) / 255,
];
const LAB_RGB = [...LAB_HEX, LAB_OTHER].map(hexToRgb);

const EDGE_VS = `#version 300 es
  in vec2 aPos;
  in float aWeight;
  in float aState;
  in float aLab;              // 0..7 = 色付きラボ, 8 = その他のラボ, 255 = ラボ線ではない
  ${VIEW}
  ${LINEAGE_COLORS}
  uniform float uThreshold;
  uniform float uAlpha;
  uniform float uSelActive;   // 0 = 選択なし
  uniform float uOnlyLineage; // 1 = 系譜以外を描かない
  uniform float uColorMode;   // 0 = ラボ, 1 = venue(エッジは単色)
  uniform float uAttrOnly;    // 1 = ラボ線だけ描く
  uniform float uIsolate;     // >=0 のときそのスロットのラボだけ描く
  uniform vec3  uLabColors[9];
  out vec4 vColor;
  void main() {
    bool inLineage = aState > 0.5;
    if (aWeight < uThreshold && !inLineage) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }
    if (uSelActive > 0.5 && uOnlyLineage > 0.5 && !inLineage) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }
    bool isLab = aLab < 254.0;
    if (uAttrOnly > 0.5 && !isLab) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }
    if (uIsolate >= 0.0 && abs(aLab - uIsolate) > 0.5) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }

    // 重みが大きいほど濃く。重み0のエッジも薄く残す(全体の地形として意味がある)
    float a = uAlpha * (0.25 + 0.75 * aWeight);
    vec3 c = vec3(0.35, 0.55, 0.95);
    if (uColorMode < 0.5) {
      c = isLab ? uLabColors[int(aLab)] : vec3(${NON_LAB[0]}, ${NON_LAB[1]}, ${NON_LAB[2]});
      // ラボ線は全体の 4.7% しかなく、等 alpha だと他のエッジの海に埋もれて
      // 「太いライン」として見えない。可視性のための増幅で、量の表現ではない。
      // 「その他のラボ」(2,113 ラボ分)は色付き8ラボを埋めてしまうので抑える。
      a *= aLab < 7.5 ? 4.0 : (isLab ? 0.9 : 0.6);
    }
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

// トーンマッピング用のフルスクリーンパス。
// エッジは float バッファに加算で「重なり量」を貯め、ここで対数圧縮して 0..1 に落とす。
// 0-1 バッファに直接足すと重なり 20 本程度で白飛びし、1980年代(数本)と
// 2020年代(数百本)を同時に見られない。圧縮はデータを間引かずに桁を揃える手段。
const TONE_VS = `#version 300 es
  const vec2 P[3] = vec2[3](vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
  void main() { gl_Position = vec4(P[gl_VertexID], 0.0, 1.0); }`;

const TONE_FS = `#version 300 es
  precision highp float;
  uniform sampler2D uTex;
  uniform float uExposure;
  uniform float uGamma;
  out vec4 outColor;
  void main() {
    vec3 v = texelFetch(uTex, ivec2(gl_FragCoord.xy), 0).rgb;
    // 対数圧縮: 重なり量の桁差を潰しつつ、少数の重なりも見えるようにする
    vec3 mapped = log(1.0 + uExposure * v) / log(1.0 + uExposure);
    mapped = pow(clamp(mapped, 0.0, 1.0), vec3(uGamma));
    outColor = vec4(vec3(0.027, 0.031, 0.047) + mapped, 1.0);
  }`;

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
      else if (aState < 3.5) { vColor = C_SELF; size *= 4.0; }
      else { vColor = C_MATCH; size *= 2.6; }
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
  const [posBuf, edgeBuf, wBuf, attrBuf, nAttrBuf, metaRes] = await Promise.all([
    fetchBuffer('nodes.bin'),
    fetchBuffer('edges.bin'),
    fetchBuffer('weights.bin'),
    fetchBuffer('edge_lab.bin'),
    fetchBuffer('node_lab.bin'),
    fetch(DATA + 'meta.json'),
  ]);
  if (!metaRes.ok) throw new Error('meta.json を読めません');
  return {
    pos: new Float32Array(posBuf),
    edges: new Uint32Array(edgeBuf),
    weights: new Float32Array(wBuf),
    edgeLab: new Uint32Array(attrBuf),     // labs のインデックス, NO_LAB = ラボ線ではない
    nodeLab: new Uint32Array(nAttrBuf),
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
  const { pos, edges, weights, edgeLab, nodeLab, meta } = data;
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
  const edgeA = new Float32Array(edgeCount * 2);   // 頂点ごとの色スロット
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
  const attrColors = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const c = VENUE_COLORS[meta.nodes[i].v] || DEFAULT_COLOR;
    colors[i * 3] = c[0]; colors[i * 3 + 1] = c[1]; colors[i * 3 + 2] = c[2];
    mags[i] = maxMag > 0 ? mags[i] / maxMag : 0;

    // ラボモードの点の色は applyChosenLabs() が埋める(選択で変わるため)
  }

  let edgeSlotBuf = null, attrColorBuf = null;
  // 選んだラボ → 色スロット。選ばれていないラボ線は「その他のラボ」スロット(8)。
  // 著者 -> その人の論文。人での検索と色付けに使う。
  const papersByAuthor = new Map();
  for (let i = 0; i < n; i++) {
    for (const ai of meta.nodes[i].a || []) {
      let arr = papersByAuthor.get(ai);
      if (!arr) papersByAuthor.set(ai, (arr = []));
      arr.push(i);
    }
  }
  const labByAuthor = new Map();
  (meta.labs || []).forEach((lab, id) => { if (lab.ai >= 0) labByAuthor.set(lab.ai, id); });

  function applyPinned() {
    // 当て方は点にも線にも同じ定義を使う:
    //   any  = その人が著者に入っている(共著も拾う)
    //   last = その人がラストオーサー(= その人のラボの仕事)
    // 線はその条件を**エッジの両端**に課したもの。つまり
    //   any  → その人が両方の論文に入っている引用 = その人自身が繋いだ流れ
    //   last → 両端のラストオーサーが一致 = ラボの系譜(前計算と一致する)
    const lastOnly = ui.roleMode && ui.roleMode.value === 'last';

    // 固定した人ごとのビット。スロットは最大8なので Uint8 で足りる。
    const mask = new Uint8Array(n);
    pinned.forEach((p, slot) => {
      for (const i of papersByAuthor.get(p.ai) || []) {
        const as = meta.nodes[i].a || [];
        if (lastOnly && as[as.length - 1] !== p.ai) continue;
        mask[i] |= 1 << slot;
      }
    });

    for (let e = 0; e < edgeCount; e++) {
      const m = mask[edges[e * 2]] & mask[edges[e * 2 + 1]];
      // 複数人が同じエッジに乗ることがあるので、若いスロット(検索で先に固定した人)を優先
      const v = m ? 31 - Math.clz32(m & -m)
                  : (edgeLab[e] === NO_LAB ? 255 : 8);   // 固定していないラボ線は「その他」
      edgeA[e * 2] = v; edgeA[e * 2 + 1] = v;
    }

    for (let i = 0; i < n; i++) {
      const m = mask[i];
      const lc = m ? LAB_RGB[31 - Math.clz32(m & -m)]
                   : (nodeLab[i] === NO_LAB ? NON_LAB : LAB_RGB[8]);
      attrColors[i * 3] = lc[0]; attrColors[i * 3 + 1] = lc[1]; attrColors[i * 3 + 2] = lc[2];
    }

    if (edgeSlotBuf) {
      gl.bindBuffer(gl.ARRAY_BUFFER, edgeSlotBuf);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, edgeA);
      gl.bindBuffer(gl.ARRAY_BUFFER, attrColorBuf);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, attrColors);
    }
    drawLegend();
    schedule();
  }

  function togglePinned(ai) {
    const at = pinned.findIndex((p) => p.ai === ai);
    if (at >= 0) pinned.splice(at, 1);
    else if (pinned.length < LAB_HEX.length) {
      pinned.push({ ai, labId: labByAuthor.has(ai) ? labByAuthor.get(ai) : null });
    } else {
      return false;   // 8スロット使い切り
    }
    applyPinned();
    return true;
  }

  const outAdj = buildCSR(edges, n, true);   // 引用された -> 引用した(未来方向)
  const inAdj = buildCSR(edges, n, false);   // 引用した -> 引用された(過去方向)

  const gl = canvas.getContext('webgl2', { antialias: true, alpha: false });
  if (!gl) { statsEl.textContent = 'WebGL2 が使えません'; return; }

  const edgeProg = program(gl, EDGE_VS, EDGE_FS);
  const nodeProg = program(gl, NODE_VS, NODE_FS);

  // --- HDR 蓄積バッファ ---
  // float バッファが使えない環境では従来どおり直接描く(白飛びはするが動く)。
  const hdrOk = !!(gl.getExtension('EXT_color_buffer_float') ||
                   gl.getExtension('EXT_color_buffer_half_float'));
  const toneProg = hdrOk ? program(gl, TONE_VS, TONE_FS) : null;
  const hdrTex = hdrOk ? gl.createTexture() : null;
  const hdrFbo = hdrOk ? gl.createFramebuffer() : null;
  let hdrW = 0, hdrH = 0;

  function resizeHdr(w, h) {
    if (!hdrOk || (w === hdrW && h === hdrH)) return;
    hdrW = w; hdrH = h;
    gl.bindTexture(gl.TEXTURE_2D, hdrTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.bindFramebuffer(gl.FRAMEBUFFER, hdrFbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, hdrTex, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

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
  edgeSlotBuf = buffer(edgeA, gl.DYNAMIC_DRAW);
  attrib(edgeProg, 'aLab', edgeSlotBuf, 1);

  const nodeVao = gl.createVertexArray();
  gl.bindVertexArray(nodeVao);
  attrib(nodeProg, 'aPos', buffer(np), 2);
  const venueColorBuf = buffer(colors);
  attrColorBuf = buffer(attrColors, gl.DYNAMIC_DRAW);
  attrib(nodeProg, 'aColor', attrColorBuf, 3);
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
    exposure: document.getElementById('exposure'),
    gamma: document.getElementById('gamma'),
    psize: document.getElementById('psize'),
    depth: document.getElementById('depth'),
    only: document.getElementById('only'),
    colorMode: document.getElementById('colorMode'),
    attrOnly: document.getElementById('attrOnly'),
    roleMode: document.getElementById('roleMode'),
  };

  let selected = -1;
  let camBeforeSelect = null;  // 選択解除で元の全体ビューに戻せるように覚えておく
  let searchActive = false;

  // 検索用に小文字化したタイトルを一度だけ作る(毎キーストロークで作り直さない)
  const lowerTitles = meta.nodes.map((nd) => (nd.t || '').toLowerCase());

  function render() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.floor(canvas.clientWidth * dpr), h = Math.floor(canvas.clientHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    resizeHdr(w, h);
    const { scale, offset } = scaleOffset();
    const selActive = selected >= 0 || searchActive ? 1 : 0;
    const onlyLineage = ui.only.checked ? 1 : 0;

    // エッジ: 加算合成で「重なり量」を貯める。HDR バッファがあればそちらへ。
    gl.bindFramebuffer(gl.FRAMEBUFFER, hdrOk ? hdrFbo : null);
    gl.viewport(0, 0, w, h);
    gl.clearColor(...(hdrOk ? [0, 0, 0, 0] : [0.027, 0.031, 0.047, 1]));
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.useProgram(edgeProg);
    gl.uniform2fv(uni(edgeProg, 'uScale'), scale);
    gl.uniform2fv(uni(edgeProg, 'uOffset'), offset);
    gl.uniform1f(uni(edgeProg, 'uThreshold'), parseFloat(ui.thresh.value));
    gl.uniform1f(uni(edgeProg, 'uAlpha'), parseFloat(ui.alpha.value));
    gl.uniform1f(uni(edgeProg, 'uSelActive'), selActive);
    gl.uniform1f(uni(edgeProg, 'uOnlyLineage'), onlyLineage);
    gl.uniform1f(uni(edgeProg, 'uColorMode'), ui.colorMode.value === 'venue' ? 1 : 0);
    gl.uniform1f(uni(edgeProg, 'uAttrOnly'), ui.attrOnly.checked ? 1 : 0);
    gl.uniform1f(uni(edgeProg, 'uIsolate'), isolatedLab);
    gl.uniform3fv(uni(edgeProg, 'uLabColors'), LAB_FLAT);
    gl.bindVertexArray(edgeVao);
    gl.drawArrays(gl.LINES, 0, edgeCount * 2);

    // 蓄積した重なり量を対数圧縮して画面に出す
    if (hdrOk) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, w, h);
      gl.disable(gl.BLEND);
      gl.useProgram(toneProg);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, hdrTex);
      gl.uniform1i(uni(toneProg, 'uTex'), 0);
      gl.uniform1f(uni(toneProg, 'uExposure'), parseFloat(ui.exposure.value));
      gl.uniform1f(uni(toneProg, 'uGamma'), parseFloat(ui.gamma.value));
      gl.bindVertexArray(null);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.enable(gl.BLEND);
    }

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
    drawBands(scale, offset);
  }

  // --- 帯(コミュニティ)の境界とラベル ---
  // ラベルは今のところ代表論文のタイトル。LLM による命名(F3)で置き換える予定。
  const bandsEl = document.getElementById('bands');
  function drawBands(scale, offset) {
    if (!meta.bands) return;
    const H = canvas.clientHeight;
    const toPx = (y) => (y * scale[1] + offset[1]) * H;
    const parts = [];

    for (const band of meta.bands) {
      const top = toPx(band.y0), bottom = toPx(band.y1);
      if (bottom < 0 || top > H) continue;
      parts.push(`<div class="sep" style="top:${top.toFixed(1)}px"></div>`);
      if (bottom - top >= 26) {
        parts.push(`<div class="lbl" style="top:${(Math.max(4, Math.min(H - 16, (top + bottom) / 2 - 7))).toFixed(1)}px">${escapeHtml(bandLabel(band))}</div>`);
      }
      // 拡大してサブ帯が十分な高さになったら、その中の内訳も出す
      for (const si of band.subbands || []) {
        const sub = meta.subbands[si];
        const st = toPx(sub.y0), sb = toPx(sub.y1);
        if (sb < 0 || st > H || sb - st < 22) continue;
        parts.push(`<div class="sep sub" style="top:${st.toFixed(1)}px"></div>`);
        parts.push(`<div class="lbl sub" style="top:${(Math.max(4, Math.min(H - 14, (st + sb) / 2 - 6))).toFixed(1)}px">${escapeHtml(subLabel(sub))}</div>`);
      }
    }
    bandsEl.innerHTML = parts.join('');
  }

  const kw = (o) => (o.keywords || []).join(' · ');
  const bandLabel = (band) => {
    const yrs = band.years ? `${band.years[0]}–${band.years[1]} · ` : '';
    return `${yrs}${band.papers.toLocaleString()}本 · ${kw(band)}`;
  };
  const subLabel = (sub) => `${sub.papers}本 · ${kw(sub)}`;

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

  function uploadStates() {
    gl.bindBuffer(gl.ARRAY_BUFFER, nodeStateBuf);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, nodeState);
    gl.bindBuffer(gl.ARRAY_BUFFER, edgeStateBuf);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, edgeState);
    schedule();
  }

  // 選択中の系譜。トレンド絞り込みのたびにここから描き直す。
  // 以前は nodeState を破壊的に絞っていたので、2つ目のトレンドを押すと
  // 1つ目の結果をさらに絞る(= AND)になって何も残らなかった。
  let lineage = null;   // {i, up:Set, down:Set}
  let highlightedSub = -1;

  function paintLineage(fitCamera) {
    nodeState.fill(0);
    edgeState.fill(0);
    if (!lineage) { uploadStates(); return; }

    const { i, up, down } = lineage;
    // 絞り込み中は、上流・下流の**どちらも**そのサブ分野だけを残す
    const keep = (v) => highlightedSub < 0 || meta.nodes[v].s === highlightedSub;
    const shown = [i];
    for (const v of up) if (keep(v)) { nodeState[v] = S_UP; shown.push(v); }
    for (const v of down) if (keep(v)) { nodeState[v] = S_DOWN; shown.push(v); }
    nodeState[i] = S_SELF;

    // エッジは「両端が残っている系譜ノード」のものだけ
    for (let e = 0; e < edgeCount; e++) {
      const a = edges[e * 2], b = edges[e * 2 + 1];
      const sa = nodeState[a], sb = nodeState[b];
      if (!sa || !sb) continue;
      const st = sa === S_SELF ? sb : (sb === S_SELF ? sa : (sa === sb ? sa : 0));
      if (st) { edgeState[e * 2] = st; edgeState[e * 2 + 1] = st; }
    }

    uploadStates();
    if (fitCamera) fitTo(shown);
    document.querySelectorAll('#lineageLists li.trend').forEach((el) => {
      el.classList.toggle('picked', parseInt(el.dataset.sub, 10) === highlightedSub);
    });
  }

  function select(i, keepCamera) {
    if (i >= 0 && selected < 0) camBeforeSelect = { ...cam };
    selected = i;
    searchActive = false;
    highlightedSub = -1;
    document.body.classList.toggle('has-selection', i >= 0);

    if (i < 0) {
      lineage = null;
      lineageEl.style.display = 'none';
      if (camBeforeSelect) { Object.assign(cam, camBeforeSelect); camBeforeSelect = null; }
      paintLineage(false);
      return;
    }

    const depthRaw = parseInt(ui.depth.value, 10);
    const maxDepth = depthRaw >= 9 ? 1e9 : depthRaw;
    lineage = {
      i,
      up: bfs(i, inAdj, maxDepth),      // 過去方向 = この論文が(間接的に)引用しているもの
      down: bfs(i, outAdj, maxDepth),   // 未来方向 = この論文を(間接的に)引用したもの
    };
    showLineagePanel(i, lineage.up, lineage.down);
    paintLineage(!keepCamera);
  }

  // 系譜の中の1トレンドに絞る。再クリックで系譜全体に戻る。
  // 上流・下流のどちらのリストから押しても、前後の両方をそのサブ分野で絞る。
  function highlightTrend(sub) {
    if (!lineage) return;
    highlightedSub = highlightedSub === sub ? -1 : sub;
    paintLineage(true);
  }

  // --- 検索 ---
  // 全語 AND のサブストリング一致。38k 件の線形走査で十分速い。
  const MAX_MARK = 4000;   // 描画で強調する上限
  const MAX_LIST = 40;     // 一覧に出す件数

  const lowerAuthors = (meta.authors || []).map((a) => a.toLowerCase());

  function runSearch(query) {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    const box = document.getElementById('searchResults');

    if (!terms.length) {
      if (searchActive) { searchActive = false; nodeState.fill(0); edgeState.fill(0); uploadStates(); }
      box.innerHTML = '';
      return;
    }

    // --- 人 ---
    const joined = terms.join(' ');
    const people = [];
    for (let ai = 0; ai < lowerAuthors.length; ai++) {
      if (!lowerAuthors[ai].includes(joined)) continue;
      people.push({ ai, papers: (papersByAuthor.get(ai) || []).length });
    }
    people.sort((a, b) => b.papers - a.papers);

    // --- 論文(全語 AND) ---
    const hits = [];
    for (let i = 0; i < lowerTitles.length; i++) {
      const t = lowerTitles[i];
      let ok = true;
      for (const term of terms) { if (!t.includes(term)) { ok = false; break; } }
      if (ok) hits.push(i);
    }
    hits.sort((a, b) => (meta.nodes[b].c || 0) - (meta.nodes[a].c || 0));

    selected = -1;
    lineageEl.style.display = 'none';
    document.body.classList.remove('has-selection');
    searchActive = hits.length > 0;
    nodeState.fill(0);
    edgeState.fill(0);
    for (const i of hits.slice(0, MAX_MARK)) nodeState[i] = S_MATCH;
    uploadStates();

    // --- 関連語(共起 PMI)。クリックで語を足す。 ---
    let chips = '';
    const rel = (meta.related || {})[terms[terms.length - 1]];
    if (rel && rel.length) {
      chips = '<div class="chips">関連語 ' +
        rel.slice(0, 6).map((w) => `<b data-term="${escapeHtml(w)}">${escapeHtml(w)}</b>`).join('') +
        '</div>';
    }

    const peopleRows = people.slice(0, 6).map((p) => {
      const slot = pinned.findIndex((q) => q.ai === p.ai);
      const lab = labByAuthor.has(p.ai) ? meta.labs[labByAuthor.get(p.ai)] : null;
      const dot = slot >= 0 ? `<i style="background:${LAB_HEX[slot]}"></i>` : '<i class="empty"></i>';
      return `<div class="person" data-ai="${p.ai}">${dot}${escapeHtml(meta.authors[p.ai])}` +
             `<span class="sub">${p.papers}本` +
             (lab ? ` · 自己引用系譜 ${lab.edges}` : ' · 系譜線なし') + '</span></div>';
    }).join('');

    const paperRows = hits.slice(0, MAX_LIST).map((i) => {
      const nd = meta.nodes[i];
      return `<div data-i="${i}"><span class="y">${nd.y}</span>${escapeHtml(nd.t.slice(0, 78))}</div>`;
    }).join('');

    box.innerHTML =
      chips +
      (peopleRows ? `<div class="grp">人(クリックで色を固定)</div>${peopleRows}` : '') +
      `<div class="grp">論文 ${hits.length.toLocaleString()} 件` +
      (hits.length > MAX_LIST ? ` — 上位 ${MAX_LIST} 件` : '') + '</div>' +
      paperRows;
    box.dataset.first = hits.length ? String(hits[0]) : '';
  }

  const searchEl = document.getElementById('search');
  let searchTimer = null;
  searchEl.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => runSearch(searchEl.value), 120);
  });
  searchEl.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const first = document.getElementById('searchResults').dataset.first;
    if (first) select(parseInt(first, 10));
  });

  document.getElementById('searchResults').addEventListener('click', (e) => {
    // 関連語チップ: クリックで検索語に足す
    const term = e.target.closest('b[data-term]');
    if (term) {
      searchEl.value = (searchEl.value.trim() + ' ' + term.dataset.term).trim();
      runSearch(searchEl.value);
      return;
    }
    // 人: クリックで色を固定 / 解除
    const person = e.target.closest('div.person');
    if (person) {
      if (!togglePinned(parseInt(person.dataset.ai, 10))) {
        alert('色は 8 人までです。凡例か検索結果で既に固定した人をクリックすると外せます。');
        return;
      }
      runSearch(searchEl.value);
      return;
    }
    const row = e.target.closest('div[data-i]');
    if (row) select(parseInt(row.dataset.i, 10));
  });

  // 系譜をサブ帯(サブ分野)ごとに数え、上位を出す。
  // 「この論文はどのトレンドの上に乗り、その後どのトレンドへ広がったか」。
  // クラスタは前計算済みのものを再利用しているので、クリックしても計算は走らない。
  function trendHtml(title, ids, kind) {
    if (!meta.subbands || !ids.length) return '';
    const counts = new Map();
    for (const i of ids) {
      const sb = meta.nodes[i].s;
      if (sb == null || sb < 0) continue;
      counts.set(sb, (counts.get(sb) || 0) + 1);
    }
    if (!counts.size) return '';
    const rows = [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([sb, cnt]) => {
        const sub = meta.subbands[sb];
        const pct = Math.round((cnt / ids.length) * 100);
        return `<li class="trend ${kind}" data-sub="${sb}" data-kind="${kind}">` +
               `<span class="n">${cnt}</span><span class="bar" style="width:${pct}%"></span>` +
               `${escapeHtml(kw(sub) || '(その他)')}</li>`;
      })
      .join('');
    return `<h3>${title}(クリックで絞り込み)</h3><ol class="trends">${rows}</ol>`;
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

  // その論文の参照のうち、何本がコーパス内に着地しているか(= 1ホップ上流の本数)
  const countRefsInCorpus = (i) => inAdj.start[i + 1] - inAdj.start[i];

  function showLineagePanel(i, up, down) {
    const nd = meta.nodes[i];
    document.getElementById('selTitle').textContent = nd.t;
    // 系譜が空になるのはデータ欠損ではなく**コーパス境界**のことが多い。
    // 参照 47 本のうちコーパス内は 3 本、のように必ず出して誤解を防ぐ。
    const inCorpus = countRefsInCorpus(i);
    document.getElementById('selMeta').innerHTML =
      `${nd.y} · ${(nd.v || '?').toUpperCase()} · 被引用 ${nd.c}<br>` +
      `<span class="cov">参照 ${nd.r} 本中 <b>${inCorpus} 本</b>がこのコーパス内` +
      (nd.r && !inCorpus ? ' — HCI 13会議の外を引用しているため遡れません' : '') +
      `</span>`;

    // 著者。最後がラストオーサー(= ラボの主宰)なので印を付ける。クリックで色を固定。
    const as = nd.a || [];
    document.getElementById('selAuthors').innerHTML = as.length
      ? as.map((ai, k) => {
          const slot = pinned.findIndex((q) => q.ai === ai);
          const isLast = k === as.length - 1 && as.length > 1;
          return `<span class="au${isLast ? ' last' : ''}" data-ai="${ai}"` +
                 (slot >= 0 ? ` style="color:${LAB_HEX[slot]}"` : '') +
                 `>${escapeHtml(meta.authors[ai] || '?')}${isLast ? ' ◂' : ''}</span>`;
        }).join('')
      : '<span class="au none">著者情報なし</span>';
    document.getElementById('upCount').textContent = up.size.toLocaleString();
    document.getElementById('downCount').textContent = down.size.toLocaleString();

    // 被引用数の多い順に、代表だけ出す(全部出すと数千件になる)
    const byCited = (a, b) => (meta.nodes[b].c || 0) - (meta.nodes[a].c || 0);
    const upIds = [...up].sort(byCited);
    const downIds = [...down].sort(byCited);
    document.getElementById('lineageLists').innerHTML =
      trendHtml('この系譜が乗っているトレンド', upIds, 'up') +
      trendHtml('この系譜が広がったトレンド', downIds, 'down') +
      listHtml('遡る系譜(よく引用されているもの順)', upIds, 12) +
      listHtml('その後の系譜(よく引用されているもの順)', downIds, 12);
    lineageEl.style.display = 'block';
    lineageEl.scrollTop = 0;
  }

  document.getElementById('lineageLists').addEventListener('click', (e) => {
    const trend = e.target.closest('li.trend[data-sub]');
    if (trend) { highlightTrend(parseInt(trend.dataset.sub, 10)); return; }
    const li = e.target.closest('li[data-i]');
    if (li) select(parseInt(li.dataset.i, 10));
  });

  document.getElementById('lineageClose').addEventListener('click', () => select(-1));
  document.getElementById('selAuthors').addEventListener('click', (e) => {
    const au = e.target.closest('.au[data-ai]');
    if (!au) return;
    if (!togglePinned(parseInt(au.dataset.ai, 10))) {
      alert('色は 8 人までです。凡例か検索結果で既に固定した人をクリックすると外せます。');
      return;
    }
    if (selected >= 0) select(selected, true);
  });

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

  // 系譜表示中は系譜内のノードだけを拾う。
  // 沈めて表示しているノードにホバーやクリックが吸われると、系譜を読んでいる最中に
  // 関係のない論文へ飛んでしまうため。副作用として、系譜外をクリックすると
  // 「ヒットなし」になり、そのまま選択解除(全体ビューに復帰)になる。
  function pick(clientX, clientY) {
    const restrict = selected >= 0;
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
          if (restrict && nodeState[i] === S_NONE) continue;
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
  ui.exposure.addEventListener('input', () => {
    document.getElementById('exposureVal').textContent = Number(ui.exposure.value).toFixed(0);
    schedule();
  });
  ui.gamma.addEventListener('input', () => {
    document.getElementById('gammaVal').textContent = Number(ui.gamma.value).toFixed(2);
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
  ui.attrOnly.addEventListener('change', schedule);
  ui.roleMode.addEventListener('change', applyPinned);
  ui.colorMode.addEventListener('change', () => {
    // 点の色は属性バッファを差し替える(毎フレーム分岐させない)
    gl.bindVertexArray(nodeVao);
    attrib(nodeProg, 'aColor', ui.colorMode.value === 'venue' ? venueColorBuf : attrColorBuf, 3);
    gl.bindVertexArray(null);
    drawLegend();
    schedule();
  });

  // 凡例クリックで1ラボに絞り込む(再クリックで解除)。
  // 8色は隣接ペア基準では通るが CVD ΔE 6–8 の帯域なので、色だけに頼らせない二次符号化。
  document.getElementById('legend').addEventListener('click', (e) => {
    const el = e.target.closest('span.lab');
    if (!el) return;
    const slot = parseInt(el.dataset.slot, 10);
    isolatedLab = isolatedLab === slot ? -1 : slot;
    drawLegend();
    schedule();
  });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') select(-1); });

  const venueCounts = {};
  for (const nd of meta.nodes) venueCounts[nd.v] = (venueCounts[nd.v] || 0) + 1;
  let otherLabEdges = 0;
  for (const lv of edgeLab) if (lv !== NO_LAB) otherLabEdges++;
  const LAB_FLAT = new Float32Array(LAB_RGB.flat());
  let isolatedLab = -1;

  function drawLegend() {
    const el = document.getElementById('legend');
    if (ui.colorMode.value === 'venue') {
      el.innerHTML = Object.entries(venueCounts)
        .sort((a, b) => b[1] - a[1])
        .map(([v, c]) => {
          const col = VENUE_COLORS[v] || DEFAULT_COLOR;
          const rgb = col.map((x) => Math.round(x * 255)).join(',');
          return `<span><i style="background:rgb(${rgb})"></i>${(v || '?').toUpperCase()} ${c}</span>`;
        })
        .join('');
      return;
    }
    // 固定した人の凡例。クリックで1人に絞り込む(色だけに identity を負わせない二次符号化)。
    el.innerHTML = pinned
      .map((p, i) => {
        const lab = p.labId != null ? meta.labs[p.labId] : null;
        const on = isolatedLab < 0 || isolatedLab === i;
        return `<span class="lab${on ? '' : ' off'}" data-slot="${i}">` +
               `<i style="background:${LAB_HEX[i]}"></i>${escapeHtml(meta.authors[p.ai])} ` +
               `<b>${lab ? lab.years[0] + '–' + lab.years[1] : '系譜線なし'}</b></span>`;
      })
      .join('') +
      `<span class="lab${isolatedLab < 0 || isolatedLab === 8 ? '' : ' off'}" data-slot="8">` +
      `<i style="background:${LAB_OTHER}"></i>その他のラボ ${otherLabEdges.toLocaleString()}リンク</span>` +
      (pinned.length ? '' : '<span class="hintline">検索欄で人名を引いて色を固定できます</span>');
  }

  // 既定は自己引用系譜が長い順に上位8人。あとは検索で入れ替えられる。
  pinned = (meta.labs || []).slice(0, LAB_HEX.length)
    .map((lab, id) => ({ ai: lab.ai, labId: id }));
  applyPinned();   // 中で drawLegend() まで走る

  statsEl.textContent =
    `${n.toLocaleString()} 本 / ${edgeCount.toLocaleString()} 引用 · ${yearMin}–${yearMax} · layout=${meta.mode}`;

  render();
}

main();
