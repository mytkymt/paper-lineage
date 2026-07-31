// paper-lineage viewer — 時間単調レイアウトの WebGL2 描画。
//
// 設計方針(docs/lineage.md、詳細はローカルの docs-dev/algorithms.md):
//  - ノード数 10^4〜10^5、エッジ 10^5〜10^6 を一度に描く。DOM は使わない。
//  - エッジは**加算合成 + 低 alpha**。重なった場所が明るくなるので、
//    「濃いところ = 太い流れ」が自動的に浮かび上がる。SPC 重みを alpha に載せる。
//  - レイアウトはオフラインで前計算済み(data/viz/*.bin)。ここでは動かさない。
//
// 座標系: 正規化座標 (0,0)=左上, (1,1)=右下 の**画面と同じ向き**に統一する。
//   シェーダ側で y を反転して合わせているので、マウス座標(clientY は下向きが正)を
//   そのまま使ってよい。これを揃えないとパン・ズーム・ホバーが全部縦に反転する。

// データセット切り替え: 既定はコア13会場。?venues=related で拡張版
// (引用結合フィルタで部分収録した隣接venue入り)を読む。
// 'peripheral' / 'linked' は旧 URL 互換で残す(共有済みリンクを壊さない)。
const _venuesParam = new URLSearchParams(location.search).get('venues');
const EXT_MODE = _venuesParam === 'related' || _venuesParam === 'peripheral' || _venuesParam === 'linked';
const DATA = EXT_MODE ? '/data/viz-ext/' : '/data/viz/';

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
  // 拡張 venue(引用結合フィルタで部分収録 — 凡例に linked と明示する)
  hri:       [0.85, 0.45, 0.40],
  ieeevr:    [0.30, 0.45, 0.95],
  ismar:     [0.35, 0.90, 0.45],
  siggraph:  [0.95, 0.35, 0.75],
  tog:       [0.75, 0.40, 0.95],
  ijhcs:     [0.55, 0.72, 0.72],
  toh:       [0.95, 0.75, 0.70],
};
// 部分収録の venue(拡張データセットのみ)。凡例で「(linked)」を付ける。
const LINKED_VENUES = new Set(['hri', 'ieeevr', 'ismar', 'siggraph', 'tog', 'ijhcs', 'toh']);
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
                 '#d55181', '#008300', '#9085e9', '#e66767',
                 '#00b2c9', '#94b000', '#ff9d3c', '#c883e8',
                 '#5ad0a0', '#e0d060', '#b76e79'];
const LAB_OTHER = '#59617a';   // 16位以下のラボ(色付きスロットを埋めないよう暗め)
const NON_LAB = [0.16, 0.19, 0.26];  // ラボ線ではないエッジ
const NO_LAB = 0xFFFFFFFF;

// 色を付ける人はユーザーが検索して選ぶ。既定はラボ系譜が長い順に上位5人。
// 「その人の論文」(点)と「その人のラボ系譜」(線)は別物なので、両方まとめて色を付ける。
let pinned = [];            // [{ai: 著者index, labId: labs index|null}] 最大 15

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
  in float aLab;              // 0..14 = 色付きラボ, 15 = その他のラボ, 255 = ラボ線ではない
  ${VIEW}
  ${LINEAGE_COLORS}
  uniform float uThreshold;
  uniform float uAlpha;
  uniform float uSelActive;   // 0 = 選択なし
  uniform float uOnlyLineage; // 1 = 系譜以外を描かない
  uniform float uColorMode;   // 0 = ラボ, 1 = venue(エッジは単色)
  uniform float uAttrOnly;    // 1 = ラボ線だけ描く
  uniform int uIsoMask;       // 0 = 絞り込みなし。bit i = スロット i の人にフォーカス中
  uniform float uClickLines;  // 0 = クリック起因の線(選択系譜・ラボ線)を描かない
  uniform vec3  uLabColors[16];
  out vec4 vColor;
  void main() {
    bool inLineage = aState > 0.5;
    if (aWeight < uThreshold && !inLineage) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }
    if (uSelActive > 0.5 && uOnlyLineage > 0.5 && !inLineage) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }
    bool isLab = aLab < 254.0 && uClickLines > 0.5;
    if (uAttrOnly > 0.5 && !isLab) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }
    int lab = int(aLab);
    if (uClickLines > 0.5 && uIsoMask != 0 && (lab > 15 || (uIsoMask & (1 << lab)) == 0)) { gl_Position = vec4(2.0); vColor = vec4(0.0); return; }

    // 重みが大きいほど濃く。重み0のエッジも薄く残す(全体の地形として意味がある)
    float a = uAlpha * (0.25 + 0.75 * aWeight);
    vec3 c = vec3(0.35, 0.55, 0.95);
    if (uColorMode < 0.5) {
      c = isLab ? uLabColors[int(aLab)] : vec3(${NON_LAB[0]}, ${NON_LAB[1]}, ${NON_LAB[2]});
      // ラボ線は全体の 4.7% しかなく、等 alpha だと他のエッジの海に埋もれて
      // 「太いライン」として見えない。可視性のための増幅で、量の表現ではない。
      // 「その他のラボ」(2,113 ラボ分)は色付き8ラボを埋めてしまうので抑える。
      a *= isLab ? (aLab < 14.5 ? 4.0 : 0.9) : 0.6;
    }
    if (uSelActive > 0.5) {
      if (aState < 0.5 || uClickLines < 0.5) { a *= 0.12; }  // 系譜外(または線オフ)は沈める
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
  in float aBoost;    // 固定した人の論文を拡大(クリックしやすさ)
  in float aFocus;    // 1 = 選択中の著者の論文
  in float aState;
  ${VIEW}
  ${LINEAGE_COLORS}
  uniform float uPointSize;
  uniform float uSelActive;
  uniform float uOnlyLineage;
  uniform float uFocusDim;    // 1 = 著者フォーカス中(他の選択なし)。背景の点をほぼ消す
  out vec3 vColor;
  out float vAlpha;
  void main() {
    bool inLineage = aState > 0.5;
    if (uSelActive > 0.5 && uOnlyLineage > 0.5 && !inLineage) { gl_Position = vec4(2.0); return; }
    gl_Position = vec4(toClip(aPos), 0.0, 1.0);
    float size = uPointSize * (0.7 + 1.8 * aMag) * aBoost;
    vColor = aColor;
    vAlpha = 0.85;
    if (uFocusDim > 0.5 && aFocus < 0.5) vAlpha = 0.07;
    if (uSelActive > 0.5) {
      // 系譜・分野・検索の中でも、**選択中の著者の論文は本人の色のまま**にする。
      // 上流/下流は位置(選択論文の左右)で読めるので、色を人に譲っても向きは失われない。
      bool mine = aFocus > 0.5;
      if (aState < 0.5) { vAlpha = 0.13; }
      else if (aState < 1.5) { if (!mine) vColor = C_UP; size *= 1.5; }
      else if (aState < 2.5) { if (!mine) vColor = C_DOWN; size *= 1.5; }
      else if (aState < 3.5) { vColor = C_SELF; size *= 0.6; }   // 選択論文は小さく(扇の中心なので位置で分かる)
      else { if (!mine) vColor = C_MATCH; size *= 1.35; }   // 分野・検索のヒットは数が多いので控えめに
      if (mine && aState > 0.5) size *= 1.25;   // 人の色は目立たせないと系譜の海に埋もれる
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
  if (!res.ok) throw new Error(`Cannot load ${name} (${res.status}) — run the pipeline's layout.py first`);
  return res.arrayBuffer();
}

async function load() {
  const [posBuf, edgeBuf, wBuf, attrBuf, nAttrBuf, metaRes, namesRes] = await Promise.all([
    fetchBuffer('nodes.bin'),
    fetchBuffer('edges.bin'),
    fetchBuffer('weights.bin'),
    fetchBuffer('edge_lab.bin'),
    fetchBuffer('node_lab.bin'),
    fetch(DATA + 'meta.json'),
    fetch('/viewer/band-names.json'),   // F3 の命名。無い/古い分はキーワード表示に落ちる(絶対パス: ルート URL は rewrite なので相対だと 404)
  ]);
  if (!metaRes.ok) throw new Error('Cannot load meta.json');
  const meta = await metaRes.json();
  applyBandNames(meta, namesRes.ok ? await namesRes.json() : null);
  return {
    pos: new Float32Array(posBuf),
    edges: new Uint32Array(edgeBuf),
    weights: new Float32Array(wBuf),
    edgeLab: new Uint32Array(attrBuf),     // labs のインデックス, NO_LAB = ラボ線ではない
    nodeLab: new Uint32Array(nAttrBuf),
    meta,
    // uint8 ビットマスク: 8 = 引用側を取得済み, |1 background |2 method |4 result, 0 = 未取得
  };
}

// band-names.json の名前を meta に写す。キーワード署名(sig)で照合するので、
// コア/拡張どちらのデータセットにも同じファイルが効く(community 番号や index は
// データセットごとに変わるため使わない)。署名が衝突する帯は 5 語の sig5 で
// 区別する。一致しない帯は黙って古い名前を出さず、キーワード表示に落ちる。
function applyBandNames(meta, names) {
  if (!names) { console.warn('band-names.json not loaded; labels fall back to keywords'); return; }
  const sig3 = (o) => (o.keywords || []).slice(0, 3).join('|');
  const sig5 = (o) => (o.keywords || []).slice(0, 5).join('|');
  const by5 = new Map(), by3 = new Map();
  for (const e of [...(names.bands || []), ...(names.subbands || [])]) {
    if (e.sig5) by5.set(e.sig5, e.name);
    else if (e.sig) by3.set(e.sig, e.name);
  }
  let unnamed = 0;
  for (const o of [...(meta.bands || []), ...(meta.subbands || [])]) {
    const name = by5.get(sig5(o)) ?? by3.get(sig3(o));
    if (name) o.name = name;
    else unnamed++;
  }
  if (unnamed) console.warn(`band-names.json has no entry for ${unnamed} band(s) — labels fall back to keywords`);
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

  let edgeSlotBuf = null, attrColorBuf = null, nodeBoostBuf = null, nodeFocusBuf = null;
  let topIdxBuf = null, topIdxCount = 0;   // 色付きノードを最前面に描く2パス目用
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

  // 各ノードの色スロット(0..7 = 固定した人, 8 = その他のラボ, 255 = なし)。
  // 人を絞り込んだときの pick 制限と、点の拡大に使う。
  const nodeSlot = new Uint8Array(n).fill(255);
  const nodeBoost = new Float32Array(n).fill(1);
  const nodeFocus = new Float32Array(n);   // 1 = 選択中の著者の論文(系譜表示中も色を保つ)

  function applyPinned() {
    // 当て方は点にも線にも同じ定義を使う:
    //   any  = その人が著者に入っている(共著も拾う)
    //   last = その人がラストオーサー(= その人のラボの仕事)
    // 線はその条件を**エッジの両端**に課したもの。つまり
    //   any  → その人が両方の論文に入っている引用 = その人自身が繋いだ流れ
    //   last → 両端のラストオーサーが一致 = ラボの系譜(前計算と一致する)
    const lastOnly = ui.roleMode && ui.roleMode.value === 'last';

    // 固定した人ごとのビット。スロットは最大8なので Uint8 で足りる。
    const mask = new Uint16Array(n);
    pinned.forEach((p, slot) => {
      if (!p) return;   // 空きスロット(色を動かさないために穴を残している)
      for (const i of papersByAuthor.get(p.ai) || []) {
        const as = meta.nodes[i].a || [];
        if (lastOnly && as[as.length - 1] !== p.ai) continue;
        mask[i] |= 1 << slot;
      }
    });

    // 共著論文はビットが複数立つ。通常時は若いスロット(先に固定した人)の色に
    // するが、絞り込み中はその人のビットが立っていれば**その人のスロット**として
    // 扱う — さもないと共著論文が「他人の論文」扱いになり、pick からも外れて
    // クリックできなくなる(実際に起きたバグ)。
    // 複数フォーカス中に両者の共著論文が来たら、フォーカス集合の中で若いスロットを採る
    // (決定論のため。フォーカス外の人しか居なければ従来どおり最小スロット)。
    const focBits = focusBits();      // 誰の色にするか(抑止中も有効)
    const isoBits = isoMask();        // 他を沈めるか(表示中のみ)
    const lowest = (b) => 31 - Math.clz32(b & -b);
    const slotOf = (m, fallback) => {
      if (!m) return fallback;
      const hit = m & focBits;
      return lowest(hit || m);
    };

    // 色が付くのは**選んだ人だけ**。ピンはあくまで候補で、選ぶまでは他のラボと同じ扱い。
    for (let e = 0; e < edgeCount; e++) {
      const m = mask[edges[e * 2]] & mask[edges[e * 2 + 1]];
      let v = slotOf(m, edgeLab[e] === NO_LAB ? 255 : 15);
      if (v < 15 && !(focBits & (1 << v))) v = 15;   // 選んでいない人の線は「その他のラボ」
      edgeA[e * 2] = v; edgeA[e * 2 + 1] = v;
    }

    for (let i = 0; i < n; i++) {
      const slot = slotOf(mask[i], nodeLab[i] === NO_LAB ? 255 : 15);
      nodeSlot[i] = slot;
      // 固定した人の論文は点を大きくして、狙ってクリックできるようにする
      const inFocus = slot < 15 && (focBits & (1 << slot)) !== 0;
      nodeFocus[i] = inFocus ? 1 : 0;
      nodeBoost[i] = inFocus ? 2.4 : 1.0;
      // 選んでいない人の論文は、ピン済みでも色を持たない(選択が唯一の発色条件)
      const lc = inFocus ? LAB_RGB[slot] : NON_LAB;
      attrColors[i * 3] = lc[0]; attrColors[i * 3 + 1] = lc[1]; attrColors[i * 3 + 2] = lc[2];
    }

    if (edgeSlotBuf) {
      gl.bindBuffer(gl.ARRAY_BUFFER, edgeSlotBuf);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, edgeA);
      gl.bindBuffer(gl.ARRAY_BUFFER, attrColorBuf);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, attrColors);
      gl.bindBuffer(gl.ARRAY_BUFFER, nodeBoostBuf);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, nodeBoost);
      gl.bindBuffer(gl.ARRAY_BUFFER, nodeFocusBuf);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, nodeFocus);
      rebuildTopIdx();
    }
    drawLegend();
    schedule();
  }

  // 色はスロット番号で決まるので、**外した人の穴は埋めない**。詰めると後ろの人の色が
  // 全部ずれて、見ていた線が別人の色になる。末尾の空きだけ回収してスロットを枯らさない。
  const pinCount = () => pinned.reduce((t, p) => t + (p ? 1 : 0), 0);
  function unpinSlot(slot) {
    if (!pinned[slot]) return;
    pinned[slot] = null;
    focused = focused.filter((s) => s !== slot);
    while (pinned.length && !pinned[pinned.length - 1]) pinned.pop();
    applyPinned();
  }
  function togglePinned(ai) {
    const at = pinned.findIndex((p) => p && p.ai === ai);
    if (at >= 0) { unpinSlot(at); return true; }
    let slot = pinned.findIndex((p) => !p);
    if (slot < 0) {
      if (pinned.length >= LAB_HEX.length) return false;   // スロット使い切り
      slot = pinned.length;
    }
    pinned[slot] = { ai, labId: labByAuthor.has(ai) ? labByAuthor.get(ai) : null };
    applyPinned();
    return true;
  }

  const outAdj = buildCSR(edges, n, true);   // 引用された -> 引用した(未来方向)
  const inAdj = buildCSR(edges, n, false);   // 引用した -> 引用された(過去方向)

  const gl = canvas.getContext('webgl2', { antialias: true, alpha: false });
  if (!gl) { statsEl.textContent = 'WebGL2 is unavailable'; return; }

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
  nodeBoostBuf = buffer(nodeBoost, gl.DYNAMIC_DRAW);
  attrib(nodeProg, 'aBoost', nodeBoostBuf, 1);
  nodeFocusBuf = buffer(nodeFocus, gl.DYNAMIC_DRAW);
  attrib(nodeProg, 'aFocus', nodeFocusBuf, 1);
  topIdxBuf = gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, topIdxBuf);   // nodeVao に記録される
  attrib(nodeProg, 'aMag', buffer(mags), 1);
  attrib(nodeProg, 'aState', nodeStateBuf, 1);
  gl.bindVertexArray(null);

  const uni = (p, name) => gl.getUniformLocation(p, name);

  // --- カメラ ---
  // 軸ごとに独立したズーム。等方ズームだと「サブ帯を見たい = 時代も拡大」になってしまうため、
  // Shift+ホイールでトピック軸(縦)だけ、Alt+ホイールで時間軸(横)だけを拡大できる。
  const cam = { zx: 1, zy: 1, cx: 0.5, cy: 0.5 };  // cx,cy = 画面中心にくる正規化座標
  const PAD = 0.04;
  const clampZoom = (z) => Math.min(400, Math.max(0.5, z));

  function scaleOffset() {
    const sx = cam.zx * (1 - 2 * PAD);
    const sy = cam.zy * (1 - 2 * PAD);
    return { scale: [sx, sy], offset: [0.5 - cam.cx * sx, 0.5 - cam.cy * sy] };
  }
  // 画面座標(px) -> 正規化座標。逆変換はこの1箇所だけに閉じ込める。
  function screenToNorm(clientX, clientY) {
    const { scale, offset } = scaleOffset();
    return [
      (clientX / canvas.clientWidth - offset[0]) / scale[0],
      (clientY / canvas.clientHeight - offset[1]) / scale[1],
    ];
  }

  const ui = {
    alpha: document.getElementById('alpha'),
    exposure: document.getElementById('exposure'),
    gamma: document.getElementById('gamma'),
    psize: document.getElementById('psize'),
    depth: document.getElementById('depth'),
    clickLines: document.getElementById('clickLines'),
    colorMode: { value: 'attr' },   // セグメントUI(#colorSeg)が書き込む状態
    roleMode: document.getElementById('roleMode'),
  };

  let selected = -1;
  let searchActive = false;

  // 検索用に小文字化したタイトルを一度だけ作る(毎キーストロークで作り直さない)
  const lowerTitles = meta.nodes.map((nd) => (nd.t || '').toLowerCase());

  function render() {
    // 非表示タブ/ペインでは clientWidth/Height が 0 になり、そのまま描くと
    // 座標が全て 0 や NaN の DOM(帯ラベル・軸)を吐いて、表示復帰後も残る。
    // レイアウトが取れるまで描画を延期する(rAF は非表示中は走らないので setTimeout)。
    if (!canvas.clientWidth || !canvas.clientHeight) { setTimeout(schedule, 200); return; }
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.floor(canvas.clientWidth * dpr), h = Math.floor(canvas.clientHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    resizeHdr(w, h);
    const { scale, offset } = scaleOffset();
    const selActive = selected >= 0 || searchActive || fieldSel ? 1 : 0;
    const onlyLineage = 0;   // 「Lineage only」UI は廃止(常に全体を薄く残す)

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
    gl.uniform1f(uni(edgeProg, 'uThreshold'), 0);   // Trunk スライダ廃止(常に all)
    gl.uniform1f(uni(edgeProg, 'uAlpha'), parseFloat(ui.alpha.value));
    gl.uniform1f(uni(edgeProg, 'uSelActive'), selActive);
    gl.uniform1f(uni(edgeProg, 'uOnlyLineage'), onlyLineage);
    gl.uniform1f(uni(edgeProg, 'uColorMode'),
      ui.colorMode.value === 'venue' ? 1 : 0);
    gl.uniform1f(uni(edgeProg, 'uAttrOnly'), 0);    // Lineage lines only UI は廃止
    gl.uniform1i(uni(edgeProg, 'uIsoMask'), isoMask());
    gl.uniform1f(uni(edgeProg, 'uClickLines'), ui.clickLines.checked ? 1 : 0);
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
    gl.uniform1f(uni(nodeProg, 'uFocusDim'),
      focused.length && !(selected >= 0 || searchActive || fieldSel) ? 1 : 0);
    gl.bindVertexArray(nodeVao);
    gl.drawArrays(gl.POINTS, 0, n);
    // 2パス目: 色の付いた点(固定した人・系譜・検索ヒット・選択)を優先順に重ね描き
    if (topIdxCount) {
      gl.drawElements(gl.POINTS, topIdxCount, gl.UNSIGNED_INT, 0);
    }
    gl.bindVertexArray(null);

    drawAxis();
  }

  let frame = null;
  const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = null; render(); }); };

  // --- 年軸のラベル ---
  function drawAxis() {
    const { scale, offset } = scaleOffset();
    const step = cam.zx > 6 ? 1 : cam.zx > 3 ? 2 : cam.zx > 1.5 ? 5 : 10;
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
  // ラベルは band-names.json(F3 の LLM 命名)。名前が無い/古い帯はキーワード表示。
  // --- Fields(帯 = 分野)ブラウザ ---
  // 帯・サブ帯は y 区間なので、所属はノードの y 座標だけで決まる。
  let fieldSel = null;   // {kind: 'band'|'sub', idx}
  let fieldPanelMembers = null;   // 選択中分野のメンバー(被引用順)。ピン変更時の再描画に使う
  let fieldPanelHeader = null;    // 分野パネルの見出し。著者パネルから Esc で戻るとき復元する
  const fieldObj = () =>
    fieldSel && (fieldSel.kind === 'band' ? meta.bands[fieldSel.idx] : meta.subbands[fieldSel.idx]);
  const fieldMembers = (o) => {
    const ids = [];
    for (let i = 0; i < n; i++) {
      const y = np[i * 2 + 1];
      if (y >= o.y0 && y < o.y1) ids.push(i);
    }
    return ids;
  };

  // 分野パネルの本文(論文リスト+著者リスト)。ピンの付け外しで色ドットが変わるので
  // selectField から分離して単独で再描画できるようにしてある。
  // どちらのセクションも折りたたみ可能で、開閉状態は再描画をまたいで保つ。
  // preserve=true(ピン変更の再描画)のときだけ開閉状態を引き継ぐ。新規選択は常に全閉。
  function renderFieldPanel(preserve) {
    if (!fieldPanelMembers) return;
    const counts = new Map();
    for (const i of fieldPanelMembers) {
      for (const ai of meta.nodes[i].a || []) counts.set(ai, (counts.get(ai) || 0) + 1);
    }
    const authors = [...counts.entries()].sort((a, b) =>
      b[1] - a[1] || String(meta.authors[a[0]]).localeCompare(String(meta.authors[b[0]])));
    // 著者は全員出す(スクロール内なので切り捨て不要)。件数はサマリーに明示。
    const auRows = authors.map(([ai, cnt]) => {
      const dot = authorDot(pinned.findIndex((q) => q && q.ai === ai));
      return `<div class="person" data-ai="${ai}">${dot}${escapeHtml(meta.authors[ai] || '?')}` +
             `<span class="sub">${cnt} papers</span></div>`;
    }).join('');
    // 既定はどちらも閉。ピン変更の再描画では明示的に開いた状態だけ引き継ぐ
    const open = preserve
      ? [...document.querySelectorAll('#lineageLists details.fold')].map((d) => d.open)
      : [];
    document.getElementById('lineageLists').innerHTML =
      `<details class="fold"${open[0] === true ? ' open' : ''}>` +
      `<summary>Most cited in this field — click to trace</summary>` +
      `<div class="scroll">` + olRows(fieldPanelMembers, 30) + '</div></details>' +
      `<details class="fold"${open[1] === true ? ' open' : ''}>` +
      `<summary>Authors — click to pin a color (${authors.length.toLocaleString()})</summary>` +
      `<div class="scroll">` +
      (auRows || '<span class="hintline">No author data</span>') + '</div></details>';
  }

  // --- 著者フォーカスとパネル ---
  // ピン = 色を持つ / フォーカス = その中でいま注目している部分集合。著者行のクリックは
  // どこから押しても「ピンを確保してフォーカスをトグル」に統一する(ピン解除は凡例の × だけ)。
  // 複数人を選べるので、パネルは1人目を開いたまま、2人目以降を折りたたみで縦に積む。
  const authorStats = new Map();   // 著者ごとの集計は使い回す(論文数千件の走査)
  function statsFor(ai) {
    if (authorStats.has(ai)) return authorStats.get(ai);
    const byCited = (a, b) => (meta.nodes[b].c || 0) - (meta.nodes[a].c || 0);
    const papers = (papersByAuthor.get(ai) || []).slice().sort(byCited);
    // 著者順の数え方は論文パネルの ◂ 印と同じ定義に揃える: 単著は著者順に意味が無いので
    // first にも last にも数えない(片方だけ単著を含めると2つの数が比べられなくなる)。
    let y0 = Infinity, y1 = -Infinity, firstN = 0, lastN = 0;
    const bySub = new Map();
    for (const i of papers) {
      const nd = meta.nodes[i];
      if (nd.y < y0) y0 = nd.y;
      if (nd.y > y1) y1 = nd.y;
      const as = nd.a || [];
      if (as.length > 1) {
        if (as[0] === ai) firstN++;
        if (as[as.length - 1] === ai) lastN++;
      }
      if (nd.s != null && nd.s >= 0) bySub.set(nd.s, (bySub.get(nd.s) || 0) + 1);
    }
    const st = {
      papers, y0, y1, firstN, lastN,
      lab: labByAuthor.has(ai) ? meta.labs[labByAuthor.get(ai)] : null,
      fields: [...bySub.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]),
    };
    authorStats.set(ai, st);
    return st;
  }

  // 著者名の色づけは全部ここを通す。色が付くのは選択中の人だけ、ピンだけの人は
  // 彩度を落とした候補として出す(凡例と同じ規則)。
  const slotOfAuthor = (ai) => pinned.findIndex((q) => q && q.ai === ai);
  const authorDot = (slot) =>
    slot < 0 ? '<i class="empty"></i>'
             : `<i class="${focused.includes(slot) ? 'on' : 'dim'}" style="background:${LAB_HEX[slot]}"></i>`;
  const isFocusedAuthor = (ai) => { const sl = slotOfAuthor(ai); return sl >= 0 && focused.includes(sl); };

  const metaLineFor = (st) =>
    `${st.papers.length.toLocaleString()} papers` +
    (st.papers.length ? ` · ${st.y0}–${st.y1}` : '') +
    (st.firstN || st.lastN ? ` · first author on ${st.firstN} · last author on ${st.lastN}` : '') +
    (st.lab ? ` · lab lineage${st.lab.gens >= 3 ? ` \u2014 ${st.lab.gens} generations deep` : ''}` : '');

  const TOPF = 10;
  function authorBody(ai, st) {
    const fieldRows = st.fields.slice(0, TOPF).map(([si, cnt]) => {
      const sb = meta.subbands[si];
      return `<div class="person frow" data-fk="sub" data-fi="${si}">` +
             `${escapeHtml(sb.name || (sb.keywords || []).slice(0, 3).join(' · '))}` +
             `<span class="sub">${cnt} papers</span></div>`;
    }).join('');
    return `<details class="fold" open><summary>Fields — click to explore` +
           (st.fields.length > TOPF ? ` (top ${TOPF} of ${st.fields.length})` : '') +
           `</summary>` +
           (fieldRows || '<span class="hintline">No field data</span>') + '</details>' +
           `<details class="fold" open><summary>Papers — most cited first, click to trace</summary>` +
           `<div class="scroll">` + olRows(st.papers, 200) + '</div></details>';
  }

  // 2人目以降のカードの開閉状態。人を足しても既に開いた人は開いたままにする。
  const cardOpen = new Set();

  function renderFocusPanel() {
    if (!focusOn()) return;
    const people = focused.filter((s) => s < 15 && pinned[s]);
    if (!people.length) {   // Other labs だけを選んでいる状態。地図は絞るがパネルは出さない
      lineageEl.style.display = 'none';
      lineageEl.classList.remove('field-mode');
      document.body.classList.remove('has-selection');
      return;
    }
    document.getElementById('selTitle').textContent =
      people.length > 1 ? `${people.length} people` : (meta.authors[pinned[people[0]].ai] || '?');
    document.getElementById('selMeta').innerHTML =
      `<span class="cov">Counting only papers inside this corpus’ venues` +
      (people.length > 1 ? ` · <span class="act" data-clear="1">clear all</span>` : '') + `</span>`;

    // 全員を同じカードにする。1人目も折りたためる(既定は開いた状態)。
    document.getElementById('lineageLists').innerHTML = people.map((slot) => {
      const ai = pinned[slot].ai, st = statsFor(ai);
      return `<details class="acard"${cardOpen.has(ai) ? ' open' : ''} data-ai="${ai}">` +
             `<summary><i style="background:${LAB_HEX[slot]}"></i>` +
             `${escapeHtml(meta.authors[ai] || '?')}` +
             `<em class="drop" data-drop="${slot}" title="Remove from selection">×</em></summary>` +
             `<div class="ameta">${metaLineFor(st)}</div>` + authorBody(ai, st) + '</details>';
    }).join('');
    lineageEl.classList.add('field-mode');   // 論文パネル用の counts / 著者行は使わない
    lineageEl.style.display = 'block';
    lineageEl.scrollTop = 0;
    document.body.classList.add('has-selection');
  }

  // フォーカスの表示が抑止されている(論文・分野・検索が出ている)ときは、
  // パネルを畳んで地図の色も戻す。集合そのものは保持する。
  function refreshFocus() {
    applyPinned();          // 中で drawLegend()、点と線の色・pick 対象が入れ替わる
    if (focusOn()) renderFocusPanel();
    else if (selected < 0 && !fieldSel && !searchActive) {   // -1 は truthy なので比較で書く
      lineageEl.style.display = 'none';
      lineageEl.classList.remove('field-mode');
      document.body.classList.remove('has-selection');
    }
  }

  function toggleFocusSlot(slot) {
    if (slot < 0 || slot > 15) return;
    const at = focused.indexOf(slot);
    if (at >= 0) focused.splice(at, 1);
    else {
      if (!focused.length && pinned[slot]) cardOpen.add(pinned[slot].ai);   // 1人目は開いて出す
      focused.push(slot);
    }
    // 論文・分野の選択は壊さない — 背景で足しておき、Esc で戻ったときに効く。
    // 検索のハイライト(黄)だけは畳む。何を見ているのか分からなくなるため。
    if (focused.length && searchActive) {
      searchActive = false;
      nodeState.fill(0); edgeState.fill(0); uploadStates();
    }
    refreshFocus();
  }

  // 著者行のクリック(検索結果・分野パネル・論文パネルのチップ・凡例)はすべてここへ。
  // 論文を選択中でも**フォーカスには足す**(表示は抑止されたまま、Esc で戻ってくる)。
  function focusAuthor(ai) {
    let slot = pinned.findIndex((p) => p && p.ai === ai);
    if (slot < 0) {
      if (!togglePinned(ai)) return false;   // 15人上限
      slot = pinned.findIndex((p) => p && p.ai === ai);
    }
    toggleFocusSlot(slot);
    return true;
  }

  function clearFocus() {
    if (!focused.length) return;
    focused = [];
    cardOpen.clear();
    refreshFocus();
  }

  function clearField() {
    if (!fieldSel) return;
    fieldSel = null;
    fieldPanelMembers = null;
    fieldPanelHeader = null;
    nodeState.fill(0); edgeState.fill(0); uploadStates();
    lineageEl.style.display = 'none';
    lineageEl.classList.remove('field-mode');
    document.body.classList.remove('has-selection');
    renderFieldTree();
    drawLegend();   // venue チップの選択中マークも消す
    refreshFocus(); // 分野を閉じたら著者フォーカスへ戻る
    schedule();
  }

  function selectField(kind, idx) {
    if (fieldSel && fieldSel.kind === kind && fieldSel.idx === idx) {
      if (kind === 'band') expandedBands.delete(idx);
      clearField();
      return;
    }
    select(-1);                       // 論文選択・検索ハイライトを畳む
    fieldSel = { kind, idx };
    let o, members;
    if (kind === 'venue') {
      // venue は帯ではないので y 区間を持たない。ノードの venue キーで拾う。
      members = [];
      let ymin = Infinity, ymax = -Infinity;
      for (let i = 0; i < n; i++) {
        if (meta.nodes[i].v !== idx) continue;
        members.push(i);
        const yr = meta.nodes[i].y;
        if (yr < ymin) ymin = yr;
        if (yr > ymax) ymax = yr;
      }
      o = { name: (idx || '?').toUpperCase() + (LINKED_VENUES.has(idx) ? ' — related (linked subset)' : ''),
            papers: members.length, years: members.length ? [ymin, ymax] : null, keywords: [] };
    } else {
      o = fieldObj();
      members = fieldMembers(o);
    }
    nodeState.fill(0); edgeState.fill(0);
    for (const i of members) nodeState[i] = S_MATCH;
    // 線は光らせない: 大きな分野では数万本が同時に光って眩しいだけになる。
    // 分野の骨格は点の分布で十分読める(線が見たければ論文を選択する)。
    uploadStates();

    // 右パネルを分野ビューにする
    const label = o.name || (o.keywords || []).slice(0, 4).join(' · ');
    const parent = kind === 'sub' ? meta.bands.find((b) => (b.subbands || []).includes(idx)) : null;
    document.getElementById('selTitle').textContent = label;
    document.getElementById('selMeta').innerHTML =
      `${o.papers.toLocaleString()} papers · ${o.years ? o.years[0] + '\u2013' + o.years[1] : ''}` +
      (parent ? ` · in ${escapeHtml(parent.name || 'band')}` : '') +
      `<br><span class="cov">${escapeHtml((o.keywords || []).join(' \u00b7 '))}</span>`;
    const byCited = (a, b) => (meta.nodes[b].c || 0) - (meta.nodes[a].c || 0);
    fieldPanelHeader = { title: label, meta: document.getElementById('selMeta').innerHTML };
    fieldPanelMembers = members.sort(byCited);
    renderFieldPanel();
    lineageEl.classList.add('field-mode');
    lineageEl.style.display = 'block';
    lineageEl.scrollTop = 0;
    // 右パネルと地図右端の帯ラベルが重なるので、論文選択時と同様にラベルを隠す
    document.body.classList.add('has-selection');
    // 地図ラベル経由でもツリー上で現在地が分かるように、Fields を開いて該当行を見せる。
    // 展開はアコーディオン: 選択中の分野の帯だけ開き、他は畳む(開きっぱなし防止)。
    if (kind !== 'venue') {
      expandedBands.clear();
      if (kind === 'band') expandedBands.add(idx);
      else {
        const bi = meta.bands.findIndex((b) => (b.subbands || []).includes(idx));
        if (bi >= 0) expandedBands.add(bi);
      }
    }
    renderFieldTree();
    if (focused.length) applyPinned();   // 分野表示中はフォーカスの絞り込みを解く
    if (kind !== 'venue') {
      document.getElementById('grpFields').open = true;
      const picked = document.querySelector('#fieldTree .picked');
      if (picked) picked.scrollIntoView({ block: 'nearest' });
    }
    drawLegend();
    schedule();
  }

  // 左パネルのツリー。バンド行クリック = 選択 + サブ展開、再クリックで解除。
  const expandedBands = new Set();
  function renderFieldTree() {
    const box = document.getElementById('fieldTree');
    if (!box || !meta.bands) return;
    const parts = [];
    const bands = [...meta.bands.keys()].sort((a, b) => meta.bands[a].y0 - meta.bands[b].y0);
    for (const bi of bands) {
      const b = meta.bands[bi];
      if (b.community == null) continue;   // 孤立ノードの疑似バンドは選べない
      const bPicked = fieldSel && fieldSel.kind === 'band' && fieldSel.idx === bi;
      parts.push(`<div class="fb${bPicked ? ' picked' : ''}" data-b="${bi}">` +
                 `${expandedBands.has(bi) ? '\u25be' : '\u25b8'} ` +
                 `${escapeHtml(b.name || (b.keywords || []).slice(0, 3).join(' \u00b7 '))}` +
                 `<b>${b.papers.toLocaleString()}</b></div>`);
      if (!expandedBands.has(bi)) continue;
      const subs = [...(b.subbands || [])].sort((x, y2) => meta.subbands[x].y0 - meta.subbands[y2].y0);
      for (const si of subs) {
        const sb = meta.subbands[si];
        const sPicked = fieldSel && fieldSel.kind === 'sub' && fieldSel.idx === si;
        parts.push(`<div class="fs${sPicked ? ' picked' : ''}" data-s="${si}">` +
                   `${escapeHtml(sb.name || (sb.keywords || []).slice(0, 3).join(' \u00b7 '))}` +
                   `<b>${(sb.papers || 0).toLocaleString()}</b></div>`);
      }
    }
    box.innerHTML = parts.join('');
  }
  document.getElementById('fieldTree').addEventListener('click', (e) => {
    const fb = e.target.closest('.fb');
    if (fb) { selectField('band', parseInt(fb.dataset.b, 10)); return; }
    const fs = e.target.closest('.fs');
    if (fs) selectField('sub', parseInt(fs.dataset.s, 10));
  });
  renderFieldTree();   // 起動時に一覧を出す

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
      const mid = (top + bottom) / 2 - 7;
      // 中心が画面外のラベルは出さない。クランプすると画面端に積み重なって読めない。
      if (bottom - top >= 26 && mid >= 4 && mid <= H - 16) {
        parts.push(`<div class="lbl" data-band="${meta.bands.indexOf(band)}" style="top:${mid.toFixed(1)}px" title="${escapeHtml(bandTitle(band))}">${escapeHtml(bandLabel(band))}</div>`);
      }
      // 拡大してサブ帯が十分な高さになったら、その中の内訳も出す
      for (const si of band.subbands || []) {
        const sub = meta.subbands[si];
        const st = toPx(sub.y0), sb = toPx(sub.y1);
        if (sb < 0 || st > H || sb - st < 22) continue;
        parts.push(`<div class="sep sub" style="top:${st.toFixed(1)}px"></div>`);
        const smid = (st + sb) / 2 - 6;
        if (smid < 4 || smid > H - 14) continue;
        parts.push(`<div class="lbl sub" data-sub="${si}" style="top:${smid.toFixed(1)}px" title="${escapeHtml(bandTitle(sub))}">${escapeHtml(subLabel(sub))}</div>`);
      }
    }
    bandsEl.innerHTML = parts.join('');
  }

  bandsEl.addEventListener('click', (e) => {
    const lbl = e.target.closest('.lbl');
    if (!lbl) return;
    if (lbl.dataset.sub != null) selectField('sub', parseInt(lbl.dataset.sub, 10));
    else if (lbl.dataset.band != null) {
      const bi = parseInt(lbl.dataset.band, 10);
      if (meta.bands[bi].community != null) selectField('band', bi);
    }
  });

  const kw = (o) => (o.keywords || []).join(' · ');
  // ラベルは名前だけ(年代はほぼ全帯 2026 までで情報が無く、規模は帯の広さで
  // 読めるため)。年代・件数はツールチップに退避して情報自体は残す。
  const bandLabel = (band) => band.name || kw(band);
  const subLabel = (sub) => sub.name || kw(sub);
  const bandTitle = (o) =>
    `${o.years ? o.years[0] + '\u2013' + o.years[1] + ' \u00b7 ' : ''}` +
    `${(o.papers || 0).toLocaleString()} papers \u2014 ${kw(o)}`;

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
    rebuildTopIdx();   // 選択・検索で色が変わったノードも最前面パスに反映する
    schedule();
  }

  // 最前面に重ね描きするノードのインデックスを、意味のある重なり順で作り直す:
  //   固定した人 < 系譜(上流/下流) < 検索ヒット < 選択した論文(白)
  // 色つき同士が重なったときに、より「注目している」ものが上に来るようにする。
  // 呼ばれるのはピン変更時と選択/検索の変更時のみ(毎フレームではない)。
  function rebuildTopIdx() {
    if (!topIdxBuf) return;
    const buckets = [[], [], [], [], []];
    for (let i = 0; i < n; i++) {
      const st = nodeState[i];
      if (st === S_UP) buckets[1].push(i);
      else if (st === S_DOWN) buckets[1].push(i);
      else if (st === S_MATCH) buckets[2].push(i);
      else if (st === S_SELF) buckets[3].push(i);
      else if (nodeFocus[i]) buckets[0].push(i);
    }
    const idx = new Uint32Array(buckets.reduce((t, b) => t + b.length, 0));
    let off = 0;
    for (const b of buckets) { idx.set(b, off); off += b.length; }
    topIdxCount = idx.length;
    gl.bindVertexArray(nodeVao);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, topIdxBuf);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.DYNAMIC_DRAW);
    gl.bindVertexArray(null);
  }

  // 選択中の系譜。トレンド絞り込みのたびにここから描き直す。
  // 以前は nodeState を破壊的に絞っていたので、2つ目のトレンドを押すと
  // 1つ目の結果をさらに絞る(= AND)になって何も残らなかった。
  let lineage = null;   // {i, up:Set, down:Set}
  let highlightedSub = -1;
  let localClusters = null;      // Re-cluster の結果 [{ids, set, label, name}]
  let highlightedCluster = -1;
  let localRest = { papers: 0, clusters: 0 };   // 表示から漏れた分(必ず件数を出す)

  // カメラには一切触らない(2026-07-30 決定)。クリックのたびに縮尺が変わると
  // 「どこを見ていたか」が失われるため、ズーム/パンはユーザー操作専用。
  function paintLineage() {
    nodeState.fill(0);
    edgeState.fill(0);
    if (!lineage) { uploadStates(); return; }

    const { i, up, down } = lineage;
    // 絞り込み中は、上流・下流の**どちらも**その集合だけを残す
    // (ローカルクラスタ選択 > サブ帯選択 > 絞り込みなし)
    const clSet = highlightedCluster >= 0 && localClusters ? localClusters[highlightedCluster].set : null;
    const keep = (v) => clSet ? clSet.has(v) : (highlightedSub < 0 || meta.nodes[v].s === highlightedSub);
    for (const v of up) if (keep(v)) nodeState[v] = S_UP;
    for (const v of down) if (keep(v)) nodeState[v] = S_DOWN;
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
    document.querySelectorAll('#lineageLists li.trend').forEach((el) => {
      el.classList.toggle('picked', el.classList.contains('local')
        ? parseInt(el.dataset.cl, 10) === highlightedCluster
        : parseInt(el.dataset.sub, 10) === highlightedSub);
    });
  }

  // 選択した論文を見える領域の中心へパンする。ズームは一切変えない
  // (クリックで縮尺が変わらないのは既定の約束)。ドラッグ/ホイールで中断可。
  let camAnim = null;
  function cancelCamAnim() {
    if (camAnim) { cancelAnimationFrame(camAnim); camAnim = null; }
  }
  let pendingPan = -1;   // 非表示中(canvas 0×0)に選択された場合、表示時にパンをやり直す
  function panToNode(i) {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) { pendingPan = i; return; }
    pendingPan = -1;
    const { scale } = scaleOffset();
    // 右の系譜パネルが地図に被るので、パネルを除いた領域の中心に置く。
    // 画面が狭くてパネルが支配的なときは素直に画面中心。
    const panelW = lineageEl.offsetWidth ? lineageEl.offsetWidth + 24 : 344;
    const px = w > panelW * 2 ? (w - panelW) / 2 : w / 2;
    const tx = np[i * 2] - (px / w - 0.5) / scale[0];
    const ty = np[i * 2 + 1];
    cancelCamAnim();
    // 非表示タブでは rAF が発火せずアニメが永久に進まないので、即座に着地させる
    if (document.hidden) { cam.cx = tx; cam.cy = ty; schedule(); return; }
    const sx = cam.cx, sy = cam.cy, t0 = performance.now(), DUR = 450;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / DUR);
      const e = 1 - Math.pow(1 - k, 3);
      cam.cx = sx + (tx - sx) * e;
      cam.cy = sy + (ty - sy) * e;
      schedule();
      camAnim = k < 1 ? requestAnimationFrame(tick) : null;
    };
    camAnim = requestAnimationFrame(tick);
  }

  function select(i) {
    selected = i;
    searchActive = false;
    fieldSel = null;
    renderFieldTree();
    highlightedSub = -1;
    localClusters = null;
    highlightedCluster = -1;
    document.body.classList.toggle('has-selection', i >= 0);

    if (i < 0) {
      lineage = null;
      lineageEl.style.display = 'none';
      paintLineage();
      refreshFocus();   // 論文を閉じたら、選んでいた著者がそのまま戻ってくる
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
    refreshFocus();         // 沈めていた色を焼き直す(系譜表示中は絞り込みを解く)
    runLocalClustering();   // local clusters は常時表示(選択のたびに自動計算、数十ms)
    paintLineage();
    panToNode(i);           // パネル表示後に呼ぶ(パネル幅を差し引いて中心を出すため)
  }

  // 系譜の中の1トレンドに絞る。再クリックで系譜全体に戻る。
  // 上流・下流のどちらのリストから押しても、前後の両方をそのサブ分野で絞る。
  function highlightTrend(sub) {
    if (!lineage) return;
    highlightedSub = highlightedSub === sub ? -1 : sub;
    highlightedCluster = -1;
    paintLineage();
  }

  // --- 系譜のローカル再クラスタリング(オンデマンド・API 不要)---
  // 全体の前計算サブ帯は「分野全体での切り方」なので、1本の系譜の中の流れとは
  // ずれ得る。ボタン押下時だけ、系譜の部分グラフ(高々数千ノード)を Louvain で
  // クラスタリングし直す。ラベル伝播は試したが密な共引用グラフで巨大クラスタに
  // 潰れた(Tangible bits で 5,139→1)ため、パイプラインと同じモジュラリティ系に。
  // 固定順序 + タイは小 ID 優先 → 決定論。選択論文(ハブ)のエッジは除く —
  // 全員がハブと繋がっているので、入れると全体がひと塊になる。
  const STOP = new Set(('the a an of for and in on with to using via from by at is are was were be how '
    + 'what can do does their our your its as toward towards based new between more when why not').split(' '));
  const tokenize = (t) => (t || '').toLowerCase().split(/[^a-z0-9-]+/)
    .filter((w) => w.length >= 3 && !STOP.has(w) && !/^\d+$/.test(w));

  let idf = null;   // 語 -> log(N/df)。初回の再クラスタ時に全タイトルから一度だけ作る
  function ensureIdf() {
    if (idf) return;
    idf = new Map();
    for (const nd of meta.nodes) {
      for (const w of new Set(tokenize(nd.t))) idf.set(w, (idf.get(w) || 0) + 1);
    }
    for (const [w, df] of idf) idf.set(w, Math.log(meta.nodes.length / df));
  }

  // クラスタの暫定ラベル: メンバーのタイトルの TF-IDF 上位語(LLM 命名で置換可能)
  function clusterLabel(g) {
    const score = new Map();
    for (const v of g) {
      for (const w of tokenize(meta.nodes[v].t)) score.set(w, (score.get(w) || 0) + (idf.get(w) || 0));
    }
    return [...score.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4).map(([w]) => w).join(' · ');
  }

  const MAX_LOCAL = 8;   // カテゴリカル上限と同じ8。漏れは件数を必ず表示する

  // 無向重み付きグラフの Louvain。levels ごとに local moving → 集約を繰り返す。
  // 返り値は元ノード index -> コミュニティ番号。
  function louvain(nNodes, links) {
    let mapping = null;
    let curN = nNodes, curLinks = links;
    for (let level = 0; level < 10; level++) {
      const adj = Array.from({ length: curN }, () => []);
      const ki = new Float64Array(curN);
      let m2 = 0;
      for (const [a, b, w] of curLinks) {
        if (a === b) { ki[a] += 2 * w; m2 += 2 * w; continue; }
        adj[a].push([b, w]); adj[b].push([a, w]);
        ki[a] += w; ki[b] += w; m2 += 2 * w;
      }
      if (!m2) break;
      const comm = Int32Array.from({ length: curN }, (_, i) => i);
      const stot = Float64Array.from(ki);
      let improvedAny = false;
      for (let pass = 0; pass < 20; pass++) {
        let moved = 0;
        for (let i = 0; i < curN; i++) {
          const ci = comm[i];
          const wsum = new Map();
          for (const [j, w] of adj[i]) wsum.set(comm[j], (wsum.get(comm[j]) || 0) + w);
          stot[ci] -= ki[i];
          let best = ci, bestGain = (wsum.get(ci) || 0) - stot[ci] * ki[i] / m2;
          for (const [c, w] of wsum) {
            if (c === ci) continue;
            const gain = w - stot[c] * ki[i] / m2;
            if (gain > bestGain + 1e-12 || (Math.abs(gain - bestGain) <= 1e-12 && c < best)) { best = c; bestGain = gain; }
          }
          stot[best] += ki[i];
          if (best !== ci) { comm[i] = best; moved++; }
        }
        if (!moved) break;
        improvedAny = true;
      }
      const remap = new Map(); let next = 0;
      for (let i = 0; i < curN; i++) {
        if (!remap.has(comm[i])) remap.set(comm[i], next++);
        comm[i] = remap.get(comm[i]);
      }
      mapping = mapping ? mapping.map((c) => comm[c]) : Array.from(comm);
      if (!improvedAny || next === curN) break;
      const agg = new Map();
      for (const [a, b, w] of curLinks) {
        const ca = comm[a], cb = comm[b];
        const key = ca <= cb ? ca * next + cb : cb * next + ca;
        agg.set(key, (agg.get(key) || 0) + w);
      }
      curLinks = [...agg.entries()].map(([key, w]) => [Math.floor(key / next), key % next, w]);
      curN = next;
    }
    return mapping;
  }

  function runLocalClustering() {
    if (!lineage) return;
    ensureIdf();
    const hub = lineage.i;
    const ids = [hub, ...lineage.up, ...lineage.down];
    const at = new Map(ids.map((v, k) => [v, k]));

    // 系譜内エッジ(ハブのものは除く)。371k エッジの1パス、数十msで済む。
    const links = [];
    for (let e = 0; e < edgeCount; e++) {
      const u = edges[e * 2], v = edges[e * 2 + 1];
      if (u === hub || v === hub) continue;
      const a = at.get(u), b = at.get(v);
      if (a != null && b != null) links.push([a, b, 1]);
    }

    const mapping = louvain(ids.length, links) || ids.map((_, k) => k);
    const groups = new Map();
    ids.forEach((v, k) => {
      const c = mapping[k];
      if (!groups.has(c)) groups.set(c, []);
      groups.get(c).push(v);
    });
    const sorted = [...groups.values()].sort((a, b) => b.length - a.length);
    const kept = sorted.filter((g) => g.length >= 3).slice(0, MAX_LOCAL);
    localRest = {
      papers: ids.length - kept.reduce((t, g) => t + g.length, 0),
      clusters: sorted.length - kept.length,
    };
    localClusters = kept.map((g) => ({ ids: g, set: new Set(g), label: clusterLabel(g), name: null }));
    highlightedCluster = -1;
    renderLocalClusters();
    paintLineage();
  }

  function renderLocalClusters() {
    const box = document.getElementById('localResults');
    if (!box || !localClusters) return;
    // 自動実行なので小さすぎる系譜は空になりうる。無言で空リストを出さない。
    if (!localClusters.length) {
      box.innerHTML = lineage.up.size + lineage.down.size >= 3
        ? '<span class="hintline">Lineage too small to split into local clusters</span>'
        : '';
      return;
    }
    // グローバルのトレンド行と同じ表記に揃える:
    // 上流/下流の件数(←u/→d)+ 2色の積み上げバー(長さ=合計・色=比率)。
    // 矢印は地図と同じ向き: 時間軸が左→右なので上流は左、下流は右。
    const max = Math.max(...localClusters.map((c) => c.ids.length), 1);
    const rows = localClusters.map((c, k) => {
      let u = 0, d = 0;
      for (const v of c.ids) {
        if (lineage.up.has(v)) u++;
        else if (lineage.down.has(v)) d++;   // ハブ自身はどちらでもないので数えない
      }
      const wu = (u / max) * 100, wd = (d / max) * 100;
      return `<li class="trend local" data-cl="${k}" title="${escapeHtml(c.label)} — ${u} upstream · ${d} downstream">` +
             `<span class="cnt"><em class="u">←${u}</em><em class="d">→${d}</em></span>` +
             `<span class="bar2"><i class="u" style="width:${wu.toFixed(1)}%"></i>` +
             `<i class="d" style="width:${wd.toFixed(1)}%"></i></span>` +
             `${escapeHtml(c.name || c.label)}</li>`;
    }).join('');
    const named = localClusters.some((c) => c.name);
    box.innerHTML =
      `<h3>Local clusters — click to filter</h3><ol class="trends">${rows}</ol>` +
      (localRest.papers > 0
        ? `<span class="hintline">+ ${localRest.papers.toLocaleString()} papers in ${localRest.clusters} smaller clusters (not shown)</span>`
        : '') +
      `<button id="nameBtn" class="mini"${named ? ' disabled' : ''}>` +
      `${named ? 'Named with AI' : 'Name clusters with AI'}</button>` +
      `<span class="hintline" id="nameStatus"></span>`;
  }

  function toggleLocalCluster(k) {
    highlightedCluster = highlightedCluster === k ? -1 : k;
    highlightedSub = -1;
    paintLineage();
  }

  // --- ローカルクラスタの LLM 命名(任意・ボタン押下時のみ)---
  // ビューアで実行時に Anthropic API を呼ぶ唯一の箇所。キーはユーザーが入力し、
  // この端末の localStorage にだけ保存する。結果はクラスタ内容(メンバー ID)の
  // ハッシュでキャッシュし、同じ系譜・同じクラスタなら再呼び出ししない —
  // 「静的・決定論」の原則に対する例外を、明示的なボタンとキャッシュで最小化する。
  const NAME_MODEL = 'claude-opus-5';
  const KEY_STORE = 'plAnthropicKey';
  const hashClusters = (cs) => {
    let h = 5381;
    for (const c of cs) for (const v of c.ids) h = ((h * 33) ^ v) >>> 0;
    return h.toString(36);
  };

  async function nameLocalClusters() {
    if (!localClusters || !localClusters.length) return;
    const status = document.getElementById('nameStatus');

    const cacheKey = `plClusterNames:${NAME_MODEL}:${hashClusters(localClusters)}`;
    const cached = localStorage.getItem(cacheKey);
    if (cached) { applyClusterNames(JSON.parse(cached)); return; }

    let key = localStorage.getItem(KEY_STORE);
    if (!key) {
      key = (prompt("Anthropic API key (stored only in this browser's localStorage):") || '').trim();
      if (!key) return;
      localStorage.setItem(KEY_STORE, key);
    }
    status.textContent = 'naming…';

    const byCited = (a, b) => (meta.nodes[b].c || 0) - (meta.nodes[a].c || 0);
    const desc = localClusters.map((c, k) => {
      const titles = [...c.ids].sort(byCited).slice(0, 8).map((v) => meta.nodes[v].t);
      return `Cluster ${k} (${c.ids.length} papers)\nkeywords: ${c.label}\ntitles:\n- ${titles.join('\n- ')}`;
    }).join('\n\n');

    try {
      const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-api-key': key,
          'anthropic-version': '2023-06-01',
          'anthropic-dangerous-direct-browser-access': 'true',
        },
        body: JSON.stringify({
          model: NAME_MODEL,
          max_tokens: 2048,
          output_config: { format: { type: 'json_schema', schema: {
            type: 'object',
            properties: { names: { type: 'array', items: { type: 'string' } } },
            required: ['names'],
            additionalProperties: false,
          } } },
          messages: [{
            role: 'user',
            content:
              "These are clusters of related HCI papers found within one paper's citation lineage. " +
              'Give each cluster a short English name (2-4 words, Title Case) describing its research thread. ' +
              `Return {"names": [...]} with exactly ${localClusters.length} names, in cluster order.\n\n` + desc,
          }],
        }),
      });
      if (!res.ok) {
        if (res.status === 401) localStorage.removeItem(KEY_STORE);   // 次回入力し直し
        const err = await res.json().catch(() => ({}));
        status.textContent = `error ${res.status}: ${(err.error && err.error.message) || 'request failed'}`;
        return;
      }
      const msg = await res.json();
      if (msg.stop_reason === 'refusal') { status.textContent = 'model declined the request'; return; }
      const text = ((msg.content || []).find((b) => b.type === 'text') || {}).text || '';
      const names = JSON.parse(text).names;
      if (!Array.isArray(names) || names.length !== localClusters.length) {
        status.textContent = 'unexpected response shape';
        return;
      }
      localStorage.setItem(cacheKey, JSON.stringify(names));
      applyClusterNames(names);
    } catch (e) {
      status.textContent = `error: ${e.message}`;
    }
  }

  function applyClusterNames(names) {
    localClusters.forEach((c, k) => { c.name = names[k]; });
    renderLocalClusters();
  }

  // --- 検索 ---
  // 全語 AND のサブストリング一致。38k 件の線形走査で十分速い。
  const MAX_MARK = 4000;   // 描画で強調する上限
  const MAX_LIST = 40;     // 一覧に出す件数

  const lowerAuthors = (meta.authors || []).map((a) => a.toLowerCase());

  // listOnly = 結果リストだけ描き直す。著者をフォーカスした直後に呼ぶ用で、
  // 地図のハイライト(黄)や選択状態には触れない。
  const runSearchList = (q) => runSearch(q, true);
  function runSearch(query, listOnly) {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    const box = document.getElementById('searchResults');

    if (!terms.length) {
      if (searchActive) {
        searchActive = false;
        nodeState.fill(0); edgeState.fill(0); uploadStates();
        refreshFocus();   // 検索を消したら選択中の著者が戻ってくる
      }
      box.innerHTML = '';
      return;
    }

    // --- 語ごとの著者マッチ(2文字以上の語のみ。1文字は全員に当たるため) ---
    const termAuthors = terms.map((t) => {
      if (t.length < 2) return null;
      const set = new Set();
      for (let ai = 0; ai < lowerAuthors.length; ai++) {
        if (lowerAuthors[ai].includes(t)) set.add(ai);
      }
      return set;
    });

    // --- 人(いずれかの語が名前に一致。クリックで色を固定) ---
    const peopleSet = new Set();
    for (const set of termAuthors) if (set) for (const ai of set) peopleSet.add(ai);
    const people = [...peopleSet].map((ai) => ({ ai, papers: (papersByAuthor.get(ai) || []).length }));
    // 一致度を最優先: クエリ全体と完全一致 > 全語が名前に含まれる > 一部の語だけ一致。
    // 論文数だけで並べると「Chun Yu」を検索しても本人が上に来ない(部分一致の多作者が勝つ)。
    const q = terms.join(' ');
    const nameRank = (ai) => {
      const nm = lowerAuthors[ai];
      if (nm === q) return 2;
      if (terms.every((t) => nm.includes(t))) return 1;
      return 0;
    };
    people.sort((a, b) => nameRank(b.ai) - nameRank(a.ai) || b.papers - a.papers);

    // --- 論文: 各語が「タイトルに含まれる」か「その論文の著者名に一致」なら OK。
    //     "wobbrock" → 本人の全論文、"ishii tangible" → Ishii の tangible 論文、が両立する。
    const hitSet = new Set();
    let byAuthor = 0;
    for (let i = 0; i < lowerTitles.length; i++) {
      const t = lowerTitles[i];
      let ok = true, usedAuthor = false;
      for (let k = 0; k < terms.length; k++) {
        if (t.includes(terms[k])) continue;
        const set = termAuthors[k];
        const as = meta.nodes[i].a;
        let am = false;
        if (set && as) { for (const ai of as) { if (set.has(ai)) { am = true; break; } } }
        if (!am) { ok = false; break; }
        usedAuthor = true;
      }
      if (ok) { hitSet.add(i); if (usedAuthor) byAuthor++; }
    }
    const hits = [...hitSet];
    hits.sort((a, b) => (meta.nodes[b].c || 0) - (meta.nodes[a].c || 0));

    if (!listOnly) {
      selected = -1;
      fieldSel = null;
      renderFieldTree();
      lineageEl.style.display = 'none';
      lineageEl.classList.remove('field-mode');
      document.body.classList.remove('has-selection');
      searchActive = hits.length > 0;
      nodeState.fill(0);
      edgeState.fill(0);
      for (const i of hits.slice(0, MAX_MARK)) nodeState[i] = S_MATCH;
      uploadStates();
      // 検索し直したらフォーカスの表示は一旦引っ込む(集合は保持。著者を押せば戻る)
      if (focused.length) applyPinned();
    }

    // --- 関連語(共起 PMI)。クリックで語を足す。 ---
    let chips = '';
    const rel = (meta.related || {})[terms[terms.length - 1]];
    if (rel && rel.length) {
      chips = '<div class="chips">Related terms ' +
        rel.slice(0, 6).map((w) => `<b data-term="${escapeHtml(w)}">${escapeHtml(w)}</b>`).join('') +
        '</div>';
    }

    const peopleRows = people.slice(0, 6).map((p) => {
      const slot = pinned.findIndex((q) => q && q.ai === p.ai);
      const lab = labByAuthor.has(p.ai) ? meta.labs[labByAuthor.get(p.ai)] : null;
      const dot = authorDot(slot);
      return `<div class="person" data-ai="${p.ai}">${dot}${escapeHtml(meta.authors[p.ai])}` +
             `<span class="sub">${p.papers} papers` +
             (lab ? ' · lab lineage' : '') + '</span></div>';
    }).join('');

    // フィールド(帯・サブ帯)も名前・キーワードで検索できるようにする
    const fieldHits = [];
    const fieldText = (o) => ((o.name || '') + ' ' + (o.keywords || []).join(' ')).toLowerCase();
    (meta.bands || []).forEach((b, bi) => {
      if (b.community == null) return;
      if (terms.every((t) => fieldText(b).includes(t))) fieldHits.push({ kind: 'band', idx: bi, o: b });
    });
    (meta.subbands || []).forEach((sb, si) => {
      if (terms.every((t) => fieldText(sb).includes(t))) fieldHits.push({ kind: 'sub', idx: si, o: sb });
    });
    const fieldRows = fieldHits.slice(0, 5).map((f) =>
      `<div class="fieldhit" data-fk="${f.kind}" data-fi="${f.idx}">` +
      `${escapeHtml(f.o.name || (f.o.keywords || []).slice(0, 3).join(' \u00b7 '))}` +
      `<span class="sub" style="float:right;color:#5d6478">${(f.o.papers || 0).toLocaleString()}` +
      `${f.kind === 'band' ? ' \u00b7 band' : ''}</span></div>`).join('');

    const paperRows = hits.slice(0, MAX_LIST).map((i) => {
      const nd = meta.nodes[i];
      return `<div data-i="${i}"><span class="y">${nd.y}</span>${escapeHtml(nd.t.slice(0, 78))}</div>`;
    }).join('');

    box.innerHTML =
      chips +
      (fieldRows ? `<div class="grp">Fields — click to explore${fieldHits.length > 5 ? ` (top 5 of ${fieldHits.length})` : ''}</div>${fieldRows}` : '') +
      (peopleRows ? `<div class="grp">People — click to pin a color${people.length > 6 ? ` (top 6 of ${people.length})` : ''}</div>${peopleRows}` : '') +
      `<div class="grp">Papers ${hits.length.toLocaleString()}` +
      (byAuthor ? ` (${byAuthor.toLocaleString()} via author match)` : '') +
      (hits.length > MAX_LIST ? ` — listing top ${MAX_LIST}` : '') +
      (hits.length > MAX_MARK ? ` (highlighting ${MAX_MARK.toLocaleString()})` : '') + '</div>' +
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
    // フィールド: クリックで選択
    const fh = e.target.closest('div.fieldhit');
    if (fh) {
      selectField(fh.dataset.fk, parseInt(fh.dataset.fi, 10));
      return;
    }
    // 人: クリックで色を確保 + フォーカスをトグル(検索ハイライトは解除して著者へ移る)
    const person = e.target.closest('div.person');
    if (person) {
      const q = searchEl.value;
      const pai = parseInt(person.dataset.ai, 10);
      // 選択中の人をもう一度押したら、フォーカスを外すだけでなく一覧からも消す。
      // 一覧に居るが未選択(既定のピンなど)の場合は、消さずに選択する。
      if (isFocusedAuthor(pai)) {
        togglePinned(pai);
        refreshFocus();
        runSearchList(q);
        return;
      }
      if (!focusAuthor(pai)) {
        alert('Up to 15 people can be pinned. Remove one with the × in the legend first.');
        return;
      }
      runSearchList(q);   // 結果リストは残す(続けて別の人も足せるように)
      return;
    }
    const row = e.target.closest('div[data-i]');
    if (row) select(parseInt(row.dataset.i, 10));
  });

  // 系譜をサブ帯(サブ分野)ごとに数え、上位を出す。
  // 「この論文はどのトレンドの上に乗り、その後どのトレンドへ広がったか」。
  // クラスタは前計算済みのものを再利用しているので、クリックしても計算は走らない。
  // 上流(このサブ分野の上に乗っている)と下流(このサブ分野へ広がった)を
  // 1本の棒に統合する。棒の長さ = 合計(最大行比)、棒の中の色分け = 上流:下流の比率。
  // 数字も両方出す(棒だけだと正確な比が読めないため)。
  function trendHtml(upIds, downIds) {
    if (!meta.subbands || (!upIds.length && !downIds.length)) return '';
    const up = new Map(), down = new Map();
    const tally = (ids, m) => {
      for (const i of ids) {
        const sb = meta.nodes[i].s;
        if (sb != null && sb >= 0) m.set(sb, (m.get(sb) || 0) + 1);
      }
    };
    tally(upIds, up);
    tally(downIds, down);
    const subs = [...new Set([...up.keys(), ...down.keys()])]
      .map((sb) => ({ sb, u: up.get(sb) || 0, d: down.get(sb) || 0 }))
      .sort((a, b) => (b.u + b.d) - (a.u + a.d))
      .slice(0, 8);
    if (!subs.length) return '';
    const max = subs[0].u + subs[0].d;

    const rows = subs.map(({ sb, u, d }) => {
      const sub = meta.subbands[sb];
      const wu = (u / max) * 100, wd = (d / max) * 100;
      return `<li class="trend" data-sub="${sb}" title="${escapeHtml(kw(sub))} — ${u} upstream · ${d} downstream">` +
             `<span class="cnt"><em class="u">←${u}</em><em class="d">→${d}</em></span>` +
             `<span class="bar2"><i class="u" style="width:${wu.toFixed(1)}%"></i>` +
             `<i class="d" style="width:${wd.toFixed(1)}%"></i></span>` +
             `${escapeHtml(sub.name || kw(sub) || '(other)')}</li>`;
    }).join('');
    return `<h3>Trends around this work — <span class="u">← upstream</span> · ` +
           `<span class="d">downstream →</span> — click to filter</h3>` +
           `<ol class="trends">${rows}</ol>`;
  }

  // 行クリックは選択、右端の ↗ だけ DOI へ(クリックハンドラ側で a.doi を除外している)
  const doiLink = (nd) =>
    nd.d ? ` · <a class="doi" href="https://doi.org/${encodeURI(nd.d)}" target="_blank" rel="noopener" title="Open at doi.org">doi ↗</a>` : '';


  function olRows(ids, limit) {
    const rows = ids
      .slice(0, limit)
      .map((v) => {
        const nd = meta.nodes[v];
        return `<li data-i="${v}"><span class="y">${nd.y}</span>${escapeHtml(nd.t.slice(0, 90))}${doiLink(nd)}</li>`;
      })
      .join('');
    const more = ids.length > limit ? `<li style="color:#5d6478">… ${ids.length - limit} more</li>` : '';
    return `<ol>${rows}${more}</ol>`;
  }

  function listHtml(title, ids, limit) {
    if (!ids.length) return '';
    return `<h3>${title}</h3>` + olRows(ids, limit);
  }

  // その論文の参照のうち、何本がコーパス内に着地しているか(= 1ホップ上流の本数)
  const countRefsInCorpus = (i) => inAdj.start[i + 1] - inAdj.start[i];
  // この論文をコーパス内から引用している本数(= 1ホップ下流の本数)
  const countCitersInCorpus = (i) => outAdj.start[i + 1] - outAdj.start[i];

  function showLineagePanel(i, up, down) {
    const nd = meta.nodes[i];
    document.getElementById('selTitle').textContent = nd.t;
    // 系譜が空になるのはデータ欠損ではなく**コーパス境界**のことが多い。
    // 参照 47 本のうちコーパス内は 3 本、のように上下流とも必ず出して誤解を防ぐ。
    const inCorpus = countRefsInCorpus(i);
    const citersIn = countCitersInCorpus(i);
    // 被引用数は S2 の全世界カウントで、エッジは OpenAlex 由来。ソース差で
    // まれに内数が総数を超えるので、分母は大きい方に揃えて矛盾表示を避ける。
    const citedTotal = Math.max(nd.c || 0, citersIn);
    document.getElementById('selMeta').innerHTML =
      `${nd.y} · ${(nd.v || '?').toUpperCase()} · cited by ${nd.c}${doiLink(nd)}<br>` +
      `<span class="cov"><b>${inCorpus}</b> of ${nd.r} references are inside this corpus` +
      (nd.r && !inCorpus
        ? ' — they point outside this map\u2019s venues, so upstream cannot be traced here'
        : '') +
      `<br><b>${citersIn}</b> of ${citedTotal} citing papers are inside this corpus` +
      (citedTotal && !citersIn
        ? ' — the citations come from outside this map\u2019s venues'
        : '') +
      `</span>`;

    // 著者。最後がラストオーサー(= ラボの主宰)なので印を付ける。クリックで色を固定。
    const as = nd.a || [];
    document.getElementById('selAuthors').innerHTML = as.length
      ? as.map((ai, k) => {
          const slot = pinned.findIndex((q) => q && q.ai === ai);
          const isLast = k === as.length - 1 && as.length > 1;
          return `<span class="au${isLast ? ' last' : ''}" data-ai="${ai}"` +
                 (isLast ? ' title="Last author"' : '') +
                 (slot >= 0 && focused.includes(slot) ? ` style="color:${LAB_HEX[slot]}"` : '') +
                 `>${escapeHtml(meta.authors[ai] || '?')}${isLast ? ' ◂' : ''}</span>`;
        }).join('')
      : '<span class="au none">No author data</span>';
    document.getElementById('upCount').textContent = up.size.toLocaleString();
    document.getElementById('downCount').textContent = down.size.toLocaleString();

    // 被引用数の多い順に、代表だけ出す(全部出すと数千件になる)
    const byCited = (a, b) => (meta.nodes[b].c || 0) - (meta.nodes[a].c || 0);
    const upIds = [...up].sort(byCited);
    const downIds = [...down].sort(byCited);
    document.getElementById('lineageLists').innerHTML =
      trendHtml(upIds, downIds) +
      `<div id="localBox"><div id="localResults"></div></div>` +
      listHtml('Upstream — most cited first', upIds, 12) +
      listHtml('Downstream — most cited first', downIds, 12);
    lineageEl.classList.remove('field-mode');
    lineageEl.style.display = 'block';
    lineageEl.scrollTop = 0;
  }

  document.getElementById('lineageLists').addEventListener('click', (e) => {
    if (e.target.closest('a.doi')) return;   // ↗ はブラウザに任せ、行選択にしない
    if (e.target.id === 'nameBtn') { nameLocalClusters(); return; }
    const local = e.target.closest('li.trend.local');
    if (local) { toggleLocalCluster(parseInt(local.dataset.cl, 10)); return; }
    const trend = e.target.closest('li.trend[data-sub]');
    if (trend) { highlightTrend(parseInt(trend.dataset.sub, 10)); return; }
    // 著者パネルの Fields 行: クリックでその分野を選択
    const frow = e.target.closest('div.frow[data-fk]');
    if (frow) { selectField(frow.dataset.fk, parseInt(frow.dataset.fi, 10)); return; }
    // カードの × / clear all
    const drop = e.target.closest('[data-drop]');
    if (drop) { toggleFocusSlot(parseInt(drop.dataset.drop, 10)); return; }
    if (e.target.closest('[data-clear]')) { clearFocus(); return; }
    // 著者行: 色を確保してフォーカスへ(分野パネルからでも著者フォーカスに移る)
    const person = e.target.closest('div.person[data-ai]');
    if (person) {
      if (!focusAuthor(parseInt(person.dataset.ai, 10))) {
        alert('Up to 15 people can be pinned. Remove one with the × in the legend first.');
      }
      return;
    }
    const li = e.target.closest('li[data-i]');
    if (li) select(parseInt(li.dataset.i, 10));
  });

  // 2人目以降のカードの開閉を覚えておく(toggle はバブルしないので捕捉フェーズで拾う)
  document.getElementById('lineageLists').addEventListener('toggle', (e) => {
    const card = e.target;
    if (!card.classList || !card.classList.contains('acard')) return;
    const ai = parseInt(card.dataset.ai, 10);
    if (!Number.isFinite(ai)) return;
    if (card.open) cardOpen.add(ai); else cardOpen.delete(ai);
  }, true);

  // メタ行の「clear all」(著者フォーカスの一括解除)
  document.getElementById('selMeta').addEventListener('click', (e) => {
    if (e.target.closest('[data-clear]')) clearFocus();
  });
  document.getElementById('lineageClose').addEventListener('click', () => {
    if (selected < 0 && focusOn()) { clearFocus(); return; }   // 著者パネルの × は選択解除
    select(-1);
  });
  document.getElementById('selAuthors').addEventListener('click', (e) => {
    const au = e.target.closest('.au[data-ai]');
    if (!au) return;
    // 論文パネルは開いたまま。フォーカスにだけ足しておき、Esc で論文を閉じると
    // その人たちが地図に残る。**色が付いている人をもう一度押したらリストごと外す** —
    // ここには凡例のような × が無いので、これが唯一の取り消し手段になる。
    const ai = parseInt(au.dataset.ai, 10);
    const slot = pinned.findIndex((q) => q && q.ai === ai);
    if (slot >= 0 && focused.includes(slot)) {
      unpinSlot(slot);
      refreshFocus();
    } else if (!focusAuthor(ai)) {
      alert('Up to 15 people can be pinned. Remove one with the × in the legend first.');
      return;
    }
    if (selected >= 0) select(selected);
  });

  // --- 操作 ---
  let dragging = false, lastX = 0, lastY = 0, downX = 0, downY = 0;
  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;   // 右・中クリックはドラッグにも選択にもしない
    dragging = true;
    lastX = downX = e.clientX; lastY = downY = e.clientY;
    canvas.classList.add('dragging'); canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointerup', (e) => {
    if (e.button !== 0 || !dragging) return;
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
      cancelCamAnim();
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
  // 右クリック = 論文のコンテキストメニュー。選択状態は一切変えないので、
  // 系譜を保ったまま論文本体の確認やコピーができる。
  const ctxEl = document.getElementById('ctx');
  let ctxNode = -1;
  function hideCtx() { ctxEl.style.display = 'none'; ctxNode = -1; }
  canvas.addEventListener('contextmenu', (e) => {
    const i = pick(e.clientX, e.clientY);
    if (i < 0) { hideCtx(); return; }   // 何もない場所は通常のコンテキストメニュー
    e.preventDefault();
    const nd = meta.nodes[i];
    ctxNode = i;
    ctxEl.innerHTML =
      `<div class="hd">${escapeHtml(nd.t.slice(0, 90))}` +
      `<div class="m">${nd.y} · ${(nd.v || '?').toUpperCase()} · cited by ${nd.c}</div></div>` +
      (nd.d
        ? `<a class="it" data-act="doi" href="https://doi.org/${encodeURI(nd.d)}" ` +
          `target="_blank" rel="noopener">Open paper (DOI) ↗</a>` +
          `<div class="it" data-act="copydoi">Copy DOI</div>`
        : `<div class="it off">No DOI on record</div>`) +
      `<div class="it" data-act="copytitle">Copy title</div>` +
      (i !== selected ? `<div class="it" data-act="trace">Trace lineage</div>` : '') +
      (nd.d ? `<div class="ft">\u2318/Ctrl+click opens links in the background</div>` : '');
    ctxEl.style.display = 'block';
    // 画面外にはみ出さないように置く(サイズ確定後に測る)
    const r = ctxEl.getBoundingClientRect();
    ctxEl.style.left = Math.min(e.clientX, window.innerWidth - r.width - 8) + 'px';
    ctxEl.style.top = Math.min(e.clientY, window.innerHeight - r.height - 8) + 'px';
    tooltip.style.display = 'none';
  });
  ctxEl.addEventListener('click', (e) => {
    const it = e.target.closest('.it[data-act]');
    if (!it || ctxNode < 0) return;
    const nd = meta.nodes[ctxNode];
    if (it.dataset.act === 'doi') {
      // 本物のアンカーなのでブラウザに任せる(修飾キーもそのまま効く)
      hideCtx(); return;
    } else if (it.dataset.act === 'copydoi' && nd.d) {
      navigator.clipboard?.writeText('https://doi.org/' + nd.d);
    } else if (it.dataset.act === 'copytitle') {
      navigator.clipboard?.writeText(nd.t);
    } else if (it.dataset.act === 'trace') {
      select(ctxNode);
    }
    hideCtx();
  });
  // メニュー外の操作(クリック・ホイール・Esc)で閉じる
  window.addEventListener('pointerdown', (e) => {
    if (ctxEl.style.display !== 'none' && !ctxEl.contains(e.target)) hideCtx();
  }, true);

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    cancelCamAnim();
    hideCtx();
    // カーソル下の正規化座標を固定したままズームする。
    // 無修飾 = 両軸 / Shift = トピック軸(縦)のみ / Alt = 時間軸(横)のみ
    const [ux, uy] = screenToNorm(e.clientX, e.clientY);
    // macOS/Chrome は Shift+ホイールのスクロール量を deltaX に付け替えるため、
    // deltaY だけ見ると Shift ズームが無反応になる。大きい方の軸を採用する。
    const d = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
    const f = Math.exp(-d * 0.002);
    if (!e.altKey) cam.zy = clampZoom(cam.zy * f);
    if (!e.shiftKey) cam.zx = clampZoom(cam.zx * f);
    const s = scaleOffset().scale;
    cam.cx = ux - (e.clientX / canvas.clientWidth - 0.5) / s[0];
    cam.cy = uy - (e.clientY / canvas.clientHeight - 0.5) / s[1];
    schedule();
  }, { passive: false });
  // データセット切り替え(コア13会場 ⇔ +linked venues)。URL パラメータでリロード。
  const venueSet = document.getElementById('venueSet');
  venueSet.checked = EXT_MODE;
  venueSet.addEventListener('change', () => {
    // 今の作業状態(選択・分野・検索・ピン・フォーカス)ごとデータセットを切り替える。
    // viewParams(共有リンクと同じ機構)に載せてリロード後に applyUrlState が復元する。
    const q = viewParams();
    if (venueSet.checked) q.set('venues', 'related');
    else q.delete('venues');
    // カメラの生座標はデータセット間で座標系(帯構成)が違うので使えない。
    // 代わりに「中心の年・見えている年幅・中心の帯 + 帯内位置・縦ズーム」に翻訳して
    // 持ち越し、復元側で新しい座標系に写像する(v2)。計算は切替時の数回だけ。
    q.delete('v');
    const span = yearMax - yearMin;
    const b = (meta.bands || []).find(
      (bb) => bb.community != null && cam.cy >= bb.y0 && cam.cy < bb.y1);
    const r = (x) => Math.round(x * 1e4) / 1e4;
    q.set('v2', [
      r(yearMin + cam.cx * span),                      // 中心の年
      r(span / cam.zx),                                // 見えている年幅
      b ? (fieldName(b) || '').replace(/~/g, '') : '', // 中心の帯(同名で対応付け)
      r(b ? (cam.cy - b.y0) / (b.y1 - b.y0) : cam.cy), // 帯内位置(帯が無ければ絶対値)
      r(cam.zy),
      // 帯の対応付けは名前が違うことがある(データセットごとに再命名される)ので、
      // キーワードでも照合できるように上位語を持ち越す
      b ? (b.keywords || []).slice(0, 8).join('|').replace(/~/g, '') : '',
    ].join('~'));
    location.search = q.toString();
  });

  // 左パネルの折りたたみ。既定は展開。
  const panelToggle = document.getElementById('panelToggle');
  panelToggle.addEventListener('click', () => {
    const c = document.getElementById('controls').classList.toggle('collapsed');
    panelToggle.textContent = c ? '+' : '\u2013';
    panelToggle.title = c ? 'Expand panel' : 'Collapse panel';
  });

  window.addEventListener('resize', schedule);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && pendingPan >= 0 && pendingPan === selected) panToNode(pendingPan);
    schedule();
  });

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
    // 系譜選択中は系譜内、検索ハイライト中は検索ヒットだけを対象にする
    // (どちらも nodeState が非ゼロの点 = 明るく描かれている点に一致する)
    const restrictLineage = selected >= 0 || searchActive || !!fieldSel;
    // 人を絞り込み中は、その人の論文だけをクリック/ホバー対象にする
    // (系譜選択と同じ発想 — 沈めた点に吸われて別の論文へ飛ばないように)
    const isoBits = isoMask();
    const restrictPerson = !restrictLineage && isoBits !== 0 && (isoBits & (1 << 15)) === 0;
    const { scale } = scaleOffset();
    const [ux, uy] = screenToNorm(clientX, clientY);
    // 画面上 12px を正規化座標に直したものを探索半径にする。
    // 人フォーカス中は対象が疎(数十点)で競合もいないので、半径を広げて狙いやすくする。
    // 複数人だと対象が密になり、半径を広げると隣の人の論文を拾ってしまう
    const r = restrictPerson && focused.length === 1 ? 26 : 12;
    const rx = r / canvas.clientWidth / scale[0];
    const ry = r / canvas.clientHeight / scale[1];
    const g0x = Math.max(0, ((ux - rx) * GRID) | 0), g1x = Math.min(GRID - 1, ((ux + rx) * GRID) | 0);
    const g0y = Math.max(0, ((uy - ry) * GRID) | 0), g1y = Math.min(GRID - 1, ((uy + ry) * GRID) | 0);

    let best = -1, bestD = Infinity;
    for (let gy = g0y; gy <= g1y; gy++) {
      for (let gx = g0x; gx <= g1x; gx++) {
        const cell = grid.get(gy * GRID + gx);
        if (!cell) continue;
        for (const i of cell) {
          if (restrictLineage && nodeState[i] === S_NONE) continue;
          if (restrictPerson && (nodeSlot[i] > 15 || (isoBits & (1 << nodeSlot[i])) === 0)) continue;
          const dx = (np[i * 2] - ux) / rx, dy = (np[i * 2 + 1] - uy) / ry;
          const d = dx * dx + dy * dy;
          if (d < bestD) { bestD = d; best = i; }
        }
      }
    }
    return bestD <= 1 ? best : -1;
  }

  function hover(e) {
    if (ctxEl.style.display === 'block') { tooltip.style.display = 'none'; return; }
    const i = pick(e.clientX, e.clientY);
    if (i < 0) { tooltip.style.display = 'none'; return; }
    const nd = meta.nodes[i];
    // 選択中の人はツールチップの中でも本人の色にする(地図のどの色が誰かをここで確かめられる)
    const aIds = nd.a || [];
    const names = aIds.slice(0, 6).map((ai) => {
      const nm = escapeHtml(meta.authors[ai] || '?');
      const sl = slotOfAuthor(ai);
      return sl >= 0 && focused.includes(sl) ? `<b style="color:${LAB_HEX[sl]}">${nm}</b>` : nm;
    });
    const authors = aIds.length
      ? `<div class="m">${names.join(', ')}` +
        (aIds.length > 6 ? ` +${aIds.length - 6} more` : '') + '</div>'
      : '';
    tooltip.innerHTML =
      `<div class="t">${escapeHtml(nd.t)}</div>` + authors +
      `<div class="m">${nd.y} · ${(nd.v || '?').toUpperCase()} · cited by ${nd.c}` +
      ' · right-click for options</div>';
    tooltip.style.display = 'block';
    tooltip.style.left = Math.min(e.clientX + 14, window.innerWidth - 400) + 'px';
    tooltip.style.top = Math.min(e.clientY + 14, window.innerHeight - 80) + 'px';
  }

  // --- UI ---
  const fmt = (v) => Number(v).toFixed(2).replace(/^0/, '');
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
    document.getElementById('depthVal').textContent = v >= 9 ? 'all' : v === 1 ? '1 hop' : `${v} hops`;
    if (selected >= 0) select(selected);
  });
  ui.roleMode.addEventListener('change', applyPinned);
  ui.clickLines.addEventListener('change', schedule);
  document.getElementById('colorSeg').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-v]');
    if (!b || ui.colorMode.value === b.dataset.v) return;
    ui.colorMode.value = b.dataset.v;
    for (const el of document.querySelectorAll('#colorSeg button')) {
      el.classList.toggle('on', el === b);
    }
    // 点の色は属性バッファを差し替える(毎フレーム分岐させない)
    gl.bindVertexArray(nodeVao);
    attrib(nodeProg, 'aColor', ui.colorMode.value === 'venue' ? venueColorBuf : attrColorBuf, 3);
    gl.bindVertexArray(null);
    drawLegend();
    schedule();
  });

  // 凡例チップ = 人の選択。クリックのたびにフォーカス集合へ出し入れする(累積トグル)。
  // 15色は隣接ペア基準では通るが CVD ΔE 6–8 の帯域なので、色だけに頼らせない二次符号化。
  // 凡例パネルはドラッグで移動できる(位置は localStorage に保存)。
  // チップのクリックと共存させるため、5px 以上動いたときだけドラッグ扱いにする。
  const legendEl = document.getElementById('legend');
  try {
    const lp = JSON.parse(localStorage.getItem('plLegendPos') || 'null');
    if (lp && Number.isFinite(lp.left) && Number.isFinite(lp.top)) {
      legendEl.style.left = Math.min(window.innerWidth - 60, Math.max(0, lp.left)) + 'px';
      legendEl.style.top = Math.min(window.innerHeight - 30, Math.max(0, lp.top)) + 'px';
      legendEl.style.right = 'auto';
      legendEl.style.bottom = 'auto';
    }
  } catch { /* 位置が壊れていたら既定のまま */ }
  let lgDrag = null;
  legendEl.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    lgDrag = { x: e.clientX, y: e.clientY, r: legendEl.getBoundingClientRect(), moved: false };
    // ここでは setPointerCapture しない: キャプチャすると後続の click の target が
    // 凡例本体に付け替えられ、チップのクリックが一切効かなくなる(実測)。
  });
  // move/up は window で受ける: キャプチャは click の target を凡例に付け替えて
  // チップを殺し、非キャプチャだとポインタが凡例の外へ出た瞬間に途切れるため。
  window.addEventListener('pointermove', (e) => {
    if (!lgDrag) return;
    const dx = e.clientX - lgDrag.x, dy = e.clientY - lgDrag.y;
    if (!lgDrag.moved && Math.hypot(dx, dy) < 5) return;
    if (!lgDrag.moved) legendEl.classList.add('dragging');
    lgDrag.moved = true;
    legendEl.style.left = Math.min(window.innerWidth - 60, Math.max(0, lgDrag.r.left + dx)) + 'px';
    legendEl.style.top = Math.min(window.innerHeight - 30, Math.max(0, lgDrag.r.top + dy)) + 'px';
    legendEl.style.right = 'auto';
    legendEl.style.bottom = 'auto';
  });
  const lgEnd = () => {
    if (!lgDrag) return;
    legendEl.classList.remove('dragging');
    if (lgDrag.moved) {
      try {
        localStorage.setItem('plLegendPos', JSON.stringify({
          left: parseFloat(legendEl.style.left), top: parseFloat(legendEl.style.top),
        }));
      } catch { /* 保存できなくても移動自体は有効 */ }
      legendEl.dataset.dragged = '1';            // 直後の click を1回だけ無効化
      setTimeout(() => { delete legendEl.dataset.dragged; }, 0);
    }
    lgDrag = null;
  };
  window.addEventListener('pointerup', lgEnd);
  window.addEventListener('pointercancel', lgEnd);

  document.getElementById('legend').addEventListener('click', (e) => {
    if (legendEl.dataset.dragged) return;   // ドラッグの終わりをクリックにしない
    const vch = e.target.closest('span[data-venue]');
    if (vch) { selectField('venue', vch.dataset.venue); drawLegend(); return; }
    const un = e.target.closest('[data-unpin]');
    if (un) {
      unpinSlot(parseInt(un.dataset.unpin, 10));   // スロットは空けたまま(色を動かさない)
      refreshFocus();
      // 一覧の色見本だけ描き直す。runSearch を全実行すると selected を -1 にしてしまい、
      // 論文を見ている最中に人を外すと系譜まで消えていた。
      if (searchEl.value.trim()) runSearchList(searchEl.value);
      if (fieldSel) renderFieldPanel(true);
      return;
    }
    const chip = e.target.closest('span.lab');
    if (!chip) return;
    toggleFocusSlot(parseInt(chip.dataset.slot, 10));
  });
  window.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    // メニューが開いていれば Esc はまずそれだけを閉じる(選択は保持)
    if (ctxEl.style.display !== 'none' && ctxEl.style.display !== '') { hideCtx(); return; }
    if (shareOpen()) { closeShare(); return; }   // 共有シートが開いていれば選択には触れない
    // 具体的なビューから順に1段ずつ戻す。著者フォーカスは最後まで残るので、
    // 論文や分野を閉じると「さっき選んだ人たち」がそのまま戻ってくる。
    if (selected >= 0) { select(-1); return; }
    if (fieldSel) { clearField(); return; }
    if (focused.length) { clearFocus(); return; }
    select(-1);
  });

  const venueCounts = {};
  for (const nd of meta.nodes) venueCounts[nd.v] = (venueCounts[nd.v] || 0) + 1;
  let totalLabEdges = 0;
  for (const lv of edgeLab) if (lv !== NO_LAB) totalLabEdges++;
  const LAB_FLAT = new Float32Array(LAB_RGB.flat());
  // フォーカス中の人(pinned のスロット番号、選択順)。ピン = 色を持つ / フォーカス = その中で
  // いま注目している部分集合、の2段構え。フォーカスは**永続的な選択**で、より具体的な
  // ビュー(論文 > 分野 > 検索)が出ている間は表示だけ抑止し、Esc で戻ってくる。
  let focused = [];
  const focusOn = () => selected < 0 && !searchActive && !fieldSel && focused.length > 0;
  // focusBits = 選ばれている人(表示が抑止されていても有効)。色の帰属はこちらで決める。
  // isoMask = 「その人たちだけを残す」絞り込み。論文・分野・検索が出ている間は 0 にして、
  // 系譜や分野のハイライトを壊さない。
  const focusBits = () => focused.reduce((m, s) => m | (1 << s), 0);
  const isoMask = () => (focusOn() ? focusBits() : 0);

  function drawLegend() {
    const el = document.getElementById('legend');
    if (ui.colorMode.value === 'venue') {
      el.innerHTML = Object.entries(venueCounts)
        .sort((a, b) => b[1] - a[1])
        .map(([v, c]) => {
          const col = VENUE_COLORS[v] || DEFAULT_COLOR;
          const rgb = col.map((x) => Math.round(x * 255)).join(',');
          const linked = LINKED_VENUES.has(v) ? ' <b>related</b>' : '';
          const on = fieldSel && fieldSel.kind === 'venue' && fieldSel.idx === v ? ' class="on"' : '';
          return `<span data-venue="${v}"${on}><i style="background:rgb(${rgb})"></i>${(v || '?').toUpperCase()}${linked} ${c}</span>`;
        })
        .join('');
      return;
    }
    // 固定した人の凡例。クリックで1人に絞り込む(色だけに identity を負わせない二次符号化)。
    const pinnedEdges = pinned.reduce(
      (t, q) => t + (q && q.labId != null ? meta.labs[q.labId].edges : 0), 0);
    const otherEdges = totalLabEdges - pinnedEdges;
    el.innerHTML = pinned
      .map((p, i) => {
        if (!p) return '';   // 空きスロット(色を保つために残してある)
        const lab = p.labId != null ? meta.labs[p.labId] : null;
        const sel = focused.includes(i) ? ' sel' : '';
        // 未選択でも「押したら何色になるか」は分かるように、彩度だけ CSS で落とす
        return `<span class="lab${sel}" data-slot="${i}">` +
               `<i style="background:${LAB_HEX[i]}"></i>` +
               `${escapeHtml(meta.authors[p.ai])}` +
               `<em class="unpin" data-unpin="${i}" title="Unpin">×</em></span>`;
      })
      .join('') +
      `<span class="lab${focused.includes(15) ? ' sel' : ''}" data-slot="15">` +
      `<i style="background:${LAB_OTHER}"></i>Other labs · ${otherEdges.toLocaleString()} links</span>` +
      (pinCount() ? '' : '<span class="hintline">Search for a person to pin their color</span>');
  }

  // 既定は自己引用系譜が長い順に上位8人。あとは検索で入れ替えられる。
  pinned = (meta.labs || []).slice(0, 5)
    .map((lab, id) => ({ ai: lab.ai, labId: id }));
  applyPinned();   // 中で drawLegend() まで走る
  const defaultPins = pinned.map((p) => (p ? meta.authors[p.ai] : '')).join(';');

  // --- 共有リンク(URL に「今見ている状態」を持たせる)---
  // 識別子は**再ビルドで変わらないもの**を使う: 論文は DOI、人と分野は名前。
  // node/author の index はレイアウトを組み直すたびに変わるので、共有された
  // リンクが黙って別の論文を指してしまう。DOI が無い論文だけ i<index> に落とし、
  // 位置指定であることが URL から分かるようにする(将来の再ビルドで壊れうる)。
  let doiIndex = null;
  const paperByDoi = (d) => {
    if (!doiIndex) {
      doiIndex = new Map();
      for (let i = 0; i < n; i++) {
        const dd = meta.nodes[i].d;
        if (dd) doiIndex.set(dd.toLowerCase(), i);
      }
    }
    return doiIndex.has(d.toLowerCase()) ? doiIndex.get(d.toLowerCase()) : -1;
  };
  const fieldName = (o) => o && (o.name || (o.keywords || []).slice(0, 3).join(' · '));

  function viewParams() {
    const q = new URLSearchParams();
    if (EXT_MODE) q.set('venues', 'related');
    if (selected >= 0) {
      const nd = meta.nodes[selected];
      q.set('paper', nd.d || 'i' + selected);
    } else if (fieldSel) {
      if (fieldSel.kind === 'venue') q.set('venue', fieldSel.idx);
      else {
        const nm = fieldName(fieldObj());
        if (nm) q.set(fieldSel.kind === 'band' ? 'band' : 'sub', nm);
      }
    } else if (searchEl.value.trim()) {
      q.set('q', searchEl.value.trim());
    }
    // 選択中の著者は、論文や分野が主役のときも一緒に載せる(Esc で戻ってくる状態なので)
    const foc = focused.filter((sl) => sl < 15 && pinned[sl]).map((sl) => meta.authors[pinned[sl].ai]);
    if (foc.length) q.set('authors', foc.join(';'));
    // ピンは既定と違うときだけ載せる(既定は毎回同じなので URL を汚さない)
    const names = pinned.map((p) => (p ? meta.authors[p.ai] : '')).join(';');
    if (names !== defaultPins) q.set('pins', names);
    const r = (x) => Math.round(x * 1e4) / 1e4;
    q.set('v', [r(cam.cx), r(cam.cy), r(cam.zx), r(cam.zy)].join(','));
    return q;
  }

  // 共有する URL を組み立てる。**アドレスバーは書き換えない** — 既定は素のリンクで、
  // 状態を載せるかどうかは共有シートのチェックボックスで選ぶ(既定はオフ)。
  // 受け取った側の URL はそのまま残す(ブックマークすれば同じビューに戻れる)。
  // 素のリンクは本当に素にする(venues=related も付けない — トップを共有する意図なので)
  const cleanUrl = () => location.origin + location.pathname;
  const shareUrl = (deep) => deep ? location.origin + location.pathname + '?' + viewParams().toString()
                                  : cleanUrl();

  function applyUrlState() {
    const q = new URLSearchParams(location.search);

    const pins = q.get('pins');
    if (pins != null) {
      const want = pins.split(';').map((s) => s.trim()).filter(Boolean);
      const next = [];
      for (const nm of want) {
        const ai = lowerAuthors.indexOf(nm.toLowerCase());
        if (ai >= 0 && next.length < LAB_HEX.length) {
          next.push({ ai, labId: labByAuthor.has(ai) ? labByAuthor.get(ai) : null });
        }
      }
      if (want.length && !next.length) console.warn('share link: none of the pinned names matched');
      pinned = next;
      applyPinned();
    }

    const paper = q.get('paper');
    const author = q.get('authors') || q.get('author');   // author= は旧リンクの互換
    const band = q.get('band'), sub = q.get('sub'), venue = q.get('venue');
    if (paper) {
      const i = /^i\d+$/.test(paper) ? Math.min(n - 1, parseInt(paper.slice(1), 10)) : paperByDoi(paper);
      if (i >= 0) select(i);
      else statsEl.insertAdjacentHTML('beforeend',
        '<span class="ext">Shared link: that paper is not in this corpus</span>');
    } else if (venue) {
      selectField('venue', venue);
    } else if (band || sub) {
      const list = band ? (meta.bands || []) : (meta.subbands || []);
      const idx = list.findIndex((o) => fieldName(o) === (band || sub));
      if (idx >= 0) selectField(band ? 'band' : 'sub', idx);
    } else if (q.get('q')) {
      searchEl.value = q.get('q');
      runSearch(searchEl.value);
    }

    // 著者フォーカスは論文・分野と併存できるので、主選択とは独立に復元する
    if (author) {
      for (const nm of author.split(';').map((x) => x.trim()).filter(Boolean)) {
        const ai = lowerAuthors.indexOf(nm.toLowerCase());
        if (ai >= 0) focusAuthor(ai);
      }
      if (!paper && !venue && !band && !sub && !q.get('q')) refreshFocus();
    }

    // カメラは最後に。選択が走らせた自動パンより共有された画角を優先する。
    const v = (q.get('v') || '').split(',').map(Number);
    if (v.length === 4 && v.every((x) => Number.isFinite(x))) {
      cancelCamAnim();
      pendingPan = -1;
      cam.cx = v[0]; cam.cy = v[1];
      cam.zx = clampZoom(v[2]); cam.zy = clampZoom(v[3]);
    }
    // v2 = データセット切替が持ち越したカメラ(年・帯ベース)。この座標系に写像する。
    const v2 = q.get('v2');
    if (v2) {
      const [yr, win, bandName, fr, zy, kws] = v2.split('~');
      const span = yearMax - yearMin;
      const winYears = parseFloat(win);
      if (Number.isFinite(winYears) && winYears > 0) cam.zx = clampZoom(span / winYears);
      const year = parseFloat(yr);
      if (Number.isFinite(year)) cam.cx = (year - yearMin) / span;
      const zyv = parseFloat(zy);
      if (Number.isFinite(zyv)) cam.zy = clampZoom(zyv);
      const frac = parseFloat(fr);
      const real = (meta.bands || []).filter((bb) => bb.community != null);
      let b = bandName
        ? real.find((bb) => (fieldName(bb) || '').replace(/~/g, '') === bandName)
        : null;
      if (!b && kws) {
        // 同名の帯が無ければキーワードの重なりが最大の帯へ(再命名・再クラスタ対策)
        const want = new Set(kws.split('|').filter(Boolean));
        let best = 0;
        for (const bb of real) {
          const ov = (bb.keywords || []).slice(0, 8).filter((k) => want.has(k)).length;
          if (ov > best) { best = ov; b = bb; }
        }
      }
      if (b && Number.isFinite(frac)) cam.cy = b.y0 + frac * (b.y1 - b.y0);
      else if (Number.isFinite(frac)) cam.cy = frac;   // 同名の帯が無ければ絶対位置で妥協
      cancelCamAnim();
      pendingPan = -1;
      // 復元し終えた v2 は URL から消す(共有・リロードで再適用しない)
      const q2 = new URLSearchParams(location.search);
      q2.delete('v2');
      history.replaceState(null, '', location.pathname + (q2.toString() ? '?' + q2.toString() : ''));
    }
    schedule();
  }

  // --- 共有シート ---
  // 各サービスの intent URL を開くだけで、SNS のスクリプトは一切読み込まない
  // (読み込むと閲覧者がそのサービスに追跡される。静的サイトのままにしておく)。
  const shareEl = document.getElementById('shareLink');
  const shareEls = {
    ovl: document.getElementById('share'),
    what: document.getElementById('shareWhat'),
    url: document.getElementById('shareUrl'),
    copy: document.getElementById('shareCopy'),
    x: document.getElementById('shareX'),
    bsky: document.getElementById('shareBsky'),
    li: document.getElementById('shareIn'),
    mail: document.getElementById('shareMail'),
    native: document.getElementById('shareNative'),
    deep: document.getElementById('shareDeep'),
  };
  const shareOpen = () => shareEls.ovl.style.display === 'flex';

  // 何を共有しているかを1行で言う。宛先アプリの入力欄にもこれが入る。
  function shareText() {
    const site = 'HCI Research Trails';
    if (selected >= 0) {
      const nd = meta.nodes[selected];
      return `“${nd.t}” (${nd.y}, ${(nd.v || '?').toUpperCase()}) — its citation lineage on ${site}`;
    }
    if (focusOn()) {
      const nm = focused.filter((sl) => sl < 15 && pinned[sl]).map((sl) => meta.authors[pinned[sl].ai]);
      if (nm.length) {
        return (nm.length <= 3 ? nm.join(', ') : `${nm.slice(0, 3).join(', ')} and ${nm.length - 3} more`) +
               ` on ${site}`;
      }
    }
    if (fieldSel) {
      const nm = fieldSel.kind === 'venue'
        ? String(fieldSel.idx).toUpperCase() : fieldName(fieldObj());
      if (nm) return `${nm} on ${site}`;
    }
    if (searchEl.value.trim()) return `“${searchEl.value.trim()}” on ${site}`;
    return `${site} — a citation map of 39,000 HCI papers`;
  }

  // チェックボックスの状態だけで URL 欄と各 intent を組み直す。
  function fillShare() {
    // ビュー固有の文面(「〜 on HCI Research Trails」)は Link to this view のときだけ。
    // 素のリンクにビューの説明を付けると、開いた先(トップ)と食い違う。
    const deepOn = shareEls.deep.checked;
    const url = shareUrl(deepOn);
    const text = deepOn ? shareText()
                        : 'HCI Research Trails \u2014 a citation map of 39,000 HCI papers';
    const eu = encodeURIComponent(url), et = encodeURIComponent(text);
    shareEls.what.textContent = text;
    shareEls.url.value = url;
    shareEls.x.href = `https://x.com/intent/post?text=${et}&url=${eu}`;
    shareEls.bsky.href = `https://bsky.app/intent/compose?text=${encodeURIComponent(text + '\n' + url)}`;
    shareEls.li.href = `https://www.linkedin.com/sharing/share-offsite/?url=${eu}`;
    shareEls.mail.href = `mailto:?subject=${et}&body=${encodeURIComponent(text + '\n\n' + url)}`;
  }

  function openShare() {
    shareEls.deep.checked = false;   // 既定は素のリンク。毎回ここから始める
    fillShare();
    shareEls.native.hidden = !navigator.share;
    shareEls.ovl.style.display = 'flex';
    shareEls.url.focus();
    shareEls.url.select();
    shareEls.url.scrollLeft = 0;   // 全選択すると末尾が見えるので、頭出しに戻す
  }
  function closeShare() { shareEls.ovl.style.display = 'none'; }

  shareEl.addEventListener('click', (e) => { e.preventDefault(); openShare(); });
  document.getElementById('shareClose').addEventListener('click', closeShare);
  shareEls.ovl.addEventListener('click', (e) => { if (e.target === shareEls.ovl) closeShare(); });
  shareEls.deep.addEventListener('change', () => {
    fillShare();
    shareEls.url.focus();
    shareEls.url.select();
    shareEls.url.scrollLeft = 0;
  });
  shareEls.copy.addEventListener('click', async () => {
    const btn = shareEls.copy;
    try {
      await navigator.clipboard.writeText(shareEls.url.value);
      btn.textContent = 'Copied';
    } catch {
      shareEls.url.select();       // clipboard 権限が無い環境は手動コピーに落とす
      btn.textContent = '⌘/Ctrl+C';
    }
    setTimeout(() => { btn.textContent = 'Copy'; }, 1600);
  });
  shareEls.native.addEventListener('click', () => {
    navigator.share({ title: 'HCI Research Trails', text: shareText(), url: shareEls.url.value })
      .catch(() => {});            // ユーザーがシートを閉じただけのときも reject する
  });

  // 開発用の覗き窓(スモークチェックが closure 内を検証できるように)
  window.PL = {
    pick, meta, cam,
    nodeSlot: () => nodeSlot,
    focused: () => focused.slice(),
    focusOn,
    pinned: () => pinned,
    // ノード i の画面座標(px)
    screenPos: (i) => {
      const { scale, offset } = scaleOffset();
      return [
        (np[i * 2] * scale[0] + offset[0]) * canvas.clientWidth,
        (np[i * 2 + 1] * scale[1] + offset[1]) * canvas.clientHeight,
      ];
    },
  };

  statsEl.innerHTML =
    `${n.toLocaleString()} papers · ${edgeCount.toLocaleString()} citations · ${yearMin}\u2013${yearMax}` +
    (EXT_MODE
      ? '<span class="ext">+ related venues (papers linked to the core corpus)</span>'
      : '');

  applyUrlState();
  render();
}

// --- チュートリアル動画のオーバーレイ ---
// **自動では出さない**(初回訪問でいきなり動画を被せるのはやめた)。パネルの
// Tutorial リンクからだけ開く。動画は 13MB あるので、開くまで src を与えない。
// main() より先に登録することで、Esc がまず動画を閉じ、選択解除には届かないようにする。
const tutEl = document.getElementById('tut');
const tutVideo = document.getElementById('tutVideo');
function openTutorial(muted) {
  if (!tutVideo.src) tutVideo.src = '/docs/media/tutorial.mp4';
  tutVideo.muted = muted;   // 自動再生はミュートが必要(ブラウザの自動再生方針)
  tutEl.style.display = 'flex';
  tutVideo.play().catch(() => {});   // 再生できなくても controls から開始できる
}
function closeTutorial() { tutVideo.pause(); tutEl.style.display = 'none'; }
document.getElementById('tutClose').addEventListener('click', closeTutorial);
document.getElementById('tutorialLink').addEventListener('click', (e) => {
  e.preventDefault();        // href はフォールバック(中クリックで生の動画が開ける)
  openTutorial(false);       // 明示的な操作なので音声あり
});
tutEl.addEventListener('click', (e) => { if (e.target === tutEl) closeTutorial(); });
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && tutEl.style.display === 'flex') {
    closeTutorial();
    e.stopImmediatePropagation();
  }
});
main();
