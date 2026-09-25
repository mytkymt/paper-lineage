"""外部祖先層による問3: 各サブ帯の初期論文が、コーパスの**外**の何を引いていたか。

data/openalex/external.jsonl(コーパスから 5 回以上引かれた外部論文、掲載先つき)を使う。
掲載先(source)の名前を、名前中の語で分野に粗く分類する。分類は保守的に(当たらなければ other)。
出力: サブ帯ごとの外部参照の分野構成と上位掲載先、年代ごとの HCI 全体の輸入元。"""
from __future__ import annotations
import csv, json, re, sys
from collections import Counter, defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
sub, year = g.sub, g.year
ext = {}
for line in (load.ROOT / "data/openalex/external.jsonl").open():
    w = json.loads(line); ext[w["id"]] = w
print(f"外部祖先 {len(ext):,} 件(取得済みぶん)")

# コーパス論文の重複レコード(OpenAlex が同じ論文を 2 つの work にしているもの)は外部ではない
def _nt(t): return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()
corpus_keys = {(_nt(r["title"]), int(r["year"])) for r in g.rows}
corpus_dois = {(r.get("doi") or "").lower() for r in g.rows} - {""}
dup_ids = {i for i, w in ext.items() if (w.get("doi") or "").lower() in corpus_dois or (_nt(w.get("title")), w.get("year")) in corpus_keys}
print(f"うちコーパス論文の重複レコード {len(dup_ids):,} 件(外部としては数えない)")

# 分類の順: OpenAlex の primary_topic(取得済みなら)→ 掲載先名 → 本などは題名 → unclassified。
# 参照解決のノイズ(書評誌、目次ページ、誤解決の常連)は数えない。
NOISE_TYPES = {"book-review", "paratext", "reference-entry", "erratum", "editorial", "letter"}
NOISE_SOURCES = {"choice reviews online", "medical entomology and zoology"}
BOOK_PLATFORMS = re.compile(r"ebooks?$|ebook platform|^lecture notes|springer|routledge|wiley|sage knowledge|oxford university press|cambridge university press|the mit press|elsevier", re.I)

FIELD_OF_TOPIC = {   # OpenAlex field → ここでの分野
    "Psychology": "psychology", "Neuroscience": "psychology",
    "Social Sciences": "social science", "Arts and Humanities": "arts/humanities",
    "Business, Management and Accounting": "social science", "Economics, Econometrics and Finance": "social science",
    "Decision Sciences": "social science",
    "Medicine": "health/medicine", "Health Professions": "health/medicine", "Nursing": "health/medicine",
    "Engineering": "engineering", "Materials Science": "engineering", "Physics and Astronomy": "engineering",
    "Mathematics": "math/stat", "Environmental Science": "other science", "Biochemistry, Genetics and Molecular Biology": "other science",
    "Agricultural and Biological Sciences": "other science", "Earth and Planetary Sciences": "other science",
    "Chemistry": "other science", "Energy": "engineering", "Immunology and Microbiology": "other science",
    "Pharmacology, Toxicology and Pharmaceutics": "health/medicine", "Veterinary": "other science", "Dentistry": "health/medicine",
}
CS_SUBFIELD = [   # Computer Science の subfield は中を分ける
    ("hci", r"human-computer|human computer"),
    ("graphics", r"graphics|computer vision and pattern"),
    ("ml/ai", r"artificial intelligence|machine learning|information systems$|signal processing"),
    ("software/systems", r"software|computer networks|hardware|theory|computational"),
]
DOI_RULES = [   # 掲載先も巻名も無いときの最後の手がかり(DOI の発行元・会議トークン)
    ("ml/ai", r"10\.1109/(cvpr|iccv|wacv|icassp|icdm|icpr|fg\.|icme)|10\.18653|10\.3115|10\.5555/(nips|aaai)"),
    ("vr/ar", r"10\.1109/(ismar|vr\.|vrst|3dui)"),
    ("robotics/control", r"10\.1109/(icra|iros|roman|hri|humanoids|tro\.|whc)"),
    ("signal/sensing", r"10\.1109/(iswc|percom|sensors|jsen|tmc|infocom|globecom|icc\.)"),
    ("social science", r"10\.1109/hicss|10\.4135|10\.4324|10\.1177|10\.1093/(joc|jcmc)|10\.2307"),
    ("psychology", r"10\.1037|10\.3758|10\.1111/j\.1467-9280|10\.1177/09567976"),
    ("cs general", r"10\.1109|10\.1007/978-3|10\.1145"),
    ("health/medicine", r"10\.2196|10\.1001|10\.1016/s0140|10\.1056"),
]
EA = re.compile(r"extended abstract|\badjunct\b|\bcompanion\b|late.breaking|work.in.progress|poster|demo", re.I)
CORPUS_VENUE = re.compile(r"sigchi conference on human factors|chi conference on human factors|user interface software|conference on computer supported cooperative work|computer supported cooperative work and social computing|conference on ubiquitous computing|tangible, embedded|interactive surfaces|human.computer interaction with mobile|intelligent user interfaces|computers and accessibility|designing interactive systems|chi play|computer.human interaction in play|siggraph|transactions on graphics|human.robot interaction|ieee virtual reality|ismar|mixed and augmented|virtual reality software", re.I)
RULES = [
    ("hci", r"man-machine studies|user modeling|child-computer|multimodal technologies|advanced visual interfaces|eye tracking research|foundations and trends® in human|human-centered informatics|multimodal user interfaces|computer human interaction|human-computer interaction series|human-computer interaction|human computer interaction|computer-human interaction|human factors in computing|user interface software|designing interactive systems|interaction design and children|creativity and cognition|tangible, embedded|interactive surfaces|mobile devices and services|mobilehci|conference on human factors|computer supported cooperative|group work|intelligent user interfaces|assets|accessibility|automotive user interfaces|interactive tabletops|engineering interactive|sigchi|chi \\d{4}|chi '|nordichi|ozchi|interact \\d|interacting with computers|behaviour & information|behaviour and information|international journal of human|human-computer studies|ubiquitous computing|pervasive computing|imwut|computer supported cooperative|cscw|accessible computing|interactions$|computers in human behavior|social robotics|presence"),
    ("vr/ar", r"virtual reality|augmented reality|mixed reality|ismar|presence|3d user interfaces|vrst"),
    ("graphics", r"siggraph|graphics|visualization|eurographics|rendering|geometry|animation|visual computing"),
    ("ml/ai", r"ai magazine|knowledge-based|expert systems|neural information|machine learning|nips|neurips|icml|artificial intelligence|aaai|ijcai|computer vision|cvpr|iccv|eccv|pattern analysis|pattern recognition|natural language|computational linguistics|acl\b|emnlp|naacl|kdd|knowledge discovery|data mining|recommender|information retrieval|sigir|web search|world wide web|web conference|web and social media|fairness, accountability|arxiv|speech|audio|multimedia|multimodal interaction|intelligent systems|knowledge management|cikm"),
    ("psychology", r"psycholog|cognition|cognitive|perception|behavior research|memory|attention|emotion|judgment|decision|neuro|brain|vision research|journal of vision|psychonomic|current biology|personality and individual"),
    ("math/stat", r"statistic|technometrics|biometrika|annals of|mathematic"),
    ("human factors", r"human factors|ergonomic"),
    ("social science", r"sociolog|communication|social|management|organization|information systems|mis quarterly|computer-mediated|new media|political|economic|anthropolog|ethnograph|cultural|feminist|gender|society|internet|policy|public opinion|information science|jasist|journal of documentation|administrative science|consumer research|marketing|business|ssrn|behavioral scientist|broadcasting|human values|ethics and information|first monday|hawaii international conference|law review|urban|geograph"),
    ("health/medicine", r"autism|visual impairment|pubmed|accident analysis|medic|health|clinical|patient|nursing|jama|lancet|bmj|psychiatr|rehabilitation|disabilit|gerontolog|geriatric|pediatric|diabetes|obesity|nutrition|sleep|pain|physiolog|surgery"),
    ("robotics/control", r"robot|automation|control|mechatronic|haptics|iros|icra"),
    ("signal/sensing", r"signal processing|sensors|sensing|mobile computing|wireless|mobicom|sensys|ipsn|embedded|acoustic|antennas|electronics|circuits|optics"),
    ("education", r"educat|learning sciences|instructional|collaborative learning|teaching|learning"),
    ("design", r"design studies|design issues|design research|co-design|codesign|industrial design|architecture|arts|crafts|creativity|leonardo|proceedings of drs|design research society"),
    ("general science", r"^nature$|^science$|pnas|proceedings of the national academy|plos one|scientific reports|nature human|royal society"),
    ("software/systems", r"software|programming|oopsla|icse|pldi|operating systems|sosp|osdi|distributed|networking|security|privacy|usenix|ccs\b|s&p|oakland|database|vldb|sigmod|computing surveys|journal of the acm|theoretical|algorithm"),
    ("games", r"game|play|entertainment|digra|fdg"),
    ("cs general", r"communications of the acm|ieee computer|computer$|acm transactions|ieee transactions|ieee access|ieee|acm|computing|computer science"),
]
TITLE_RULES = [   # 掲載先が無いもの(本など)は題名で保守的に
    ("psychology", r"psycholog|cognit|perception|attention|memory|emotion|affect|mind|brain|behavio"),
    ("social science", r"sociolog|ethnograph|anthropolog|social|society|culture|communit|organization|communication|politic|econom|gender|feminis|discourse|practice"),
    ("design", r"design|architect|craft|aesthetic"),
    ("human factors", r"human factors|ergonomic|usability"),
    ("hci", r"human-computer|user interface|interaction design|interface|computer-supported|groupware|ubiquitous|embodied interaction|situated action|plans and situated|things that make us smart|design of everyday things"),
    ("social science", r"grounded theory|thematic analysis|qualitative|ethnograph|interview|case study research|presentation of self"),
    ("graphics", r"graphics|rendering|visualization"),
    ("ml/ai", r"neural|learning|artificial intelligence|vision|recognition|language|speech|retrieval|statistical"),
    ("software/systems", r"software|programming|operating system|network|security|algorithm|database"),
    ("education", r"educat|teach|school|learn"),
    ("health/medicine", r"health|medic|clinic|patient|disab|therap|rehabilit"),
    ("games", r"game|play"),
    ("robotics/control", r"robot|control|haptic"),
    ("philosophy/theory", r"philosoph|phenomenolog|epistem|being and time|theory of"),
]
def field_of(w: dict) -> str | None:
    """分野名。数えないもの(ノイズ)は None。"""
    if (w.get("type") or "") in NOISE_TYPES: return None
    src = (w.get("source") or "").strip()
    if src.lower() in NOISE_SOURCES: return None
    if not src or BOOK_PLATFORMS.search(src):
        src = (w.get("container") or "").strip()      # Crossref で補った巻名
    tf = w.get("topic_field"); tsf = (w.get("topic_subfield") or "").lower()
    if tf:
        if tf == "Computer Science":
            for name, pat in CS_SUBFIELD:
                if re.search(pat, tsf): return name
            return "cs general"
        return FIELD_OF_TOPIC.get(tf, "other")
    s = src.lower()
    if s and not BOOK_PLATFORMS.search(s):
        for name, pat in RULES:
            if re.search(pat, s):
                if name == "hci":
                    if EA.search(s): return "hci (companion tracks)"
                    if CORPUS_VENUE.search(s): return "hci (corpus venue, not indexed)"
                    return "hci (journals & other venues)"
                return name
        return "other"
    d = (w.get("doi") or "").lower()
    for name, pat in DOI_RULES:
        if re.search(pat, d): return name
    t = (w.get("title") or "").lower()
    for name, pat in TITLE_RULES:
        if re.search(pat, t): return name
    return "unclassified"
def source_label(w: dict) -> str:
    src = (w.get("source") or "").strip()
    if not src or BOOK_PLATFORMS.search(src): src = (w.get("container") or "").strip()
    if src and not BOOK_PLATFORMS.search(src): return re.sub(r"^proceedings of (the )?", "", src, flags=re.I)[:60]
    return "(book / no source)"

n_topic = sum(1 for w in ext.values() if w.get("topic_field"))
print(f"primary_topic あり {n_topic:,} 件(0 なら fetch_external --topics で埋めるまで掲載先名と題名で分類)")

# サブ帯 × 初期論文 → 外部参照
raw_refs = {}
for line in (load.ROOT / "data/openalex/works.jsonl").open():
    w = json.loads(line); raw_refs[w["id"]] = w.get("refs") or []
node_id = [r["id"] for r in g.rows]
rows, top_rows = [], []
overall = defaultdict(Counter)   # decade -> field -> count
for s in range(len(g.sub_name)):
    m = np.flatnonzero(sub == s)
    if len(m) < 20: continue
    order = m[np.argsort(year[m], kind="stable")]; early = order[:max(20, int(0.1 * len(m)))]
    fields, sources = Counter(), Counter(); n_ext = n_seen = 0
    for i in early:
        for r in raw_refs.get(node_id[i], []):
            if r in ext and r not in dup_ids:
                w = ext[r]; fld = field_of(w)
                if fld is None: continue          # ノイズは数えない
                n_seen += 1
                fields[fld] += 1; sources[source_label(w)] += 1
                overall[(int(year[i]) // 10) * 10][fld] += 1
    tot = sum(fields.values())
    if tot < 10: continue
    top = [f"{k} ({v})" for k, v in sources.most_common(5) if not k.startswith("(")][:4]
    fl = fields.most_common(3)
    rows.append([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], len(m), tot] + sum(([k, round(v / tot, 2)] for k, v in fl), []) + [""] * (6 - 2 * len(fl)) + [" / ".join(top)])
with (load.OUT / "external_origins.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["sub", "name", "band", "papers", "external_refs_seen", "f1", "f1_share", "f2", "f2_share", "f3", "f3_share", "top_sources"]); w.writerows(rows)
print("\n各サブ帯の初期論文が引いた外部の分野(上位)と掲載先:")
for r in sorted(rows, key=lambda r: -r[3])[:26]:
    print(f"  {r[1][:28]:28} ← {r[5]}({r[6]}) / {r[7]}({r[8]}) / {r[9]}({r[10]})   {r[11][:110]}")
print("\nHCI 全体の輸入元(初期論文の外部参照、年代別、上位; unclassified は本などで題名からも当たらないもの):")
dec_rows = []
for dec in sorted(overall):
    c = overall[dec]; tot = sum(c.values())
    print(f"  {dec}s (n={tot:,}): " + ", ".join(f"{k} {v/tot:.0%}" for k, v in c.most_common(8)))
    for k, v in c.most_common():
        dec_rows.append([dec, k, v, round(v / tot, 3)])
with (load.OUT / "external_origins_by_decade.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["decade", "field", "refs", "share"]); w.writerows(dec_rows)
# 分類の手段の内訳(論文で述べる)
how = Counter()
for i, w in ext.items():
    if i in dup_ids: how["corpus duplicate (dropped)"] += 1
    elif field_of(w) is None: how["noise (dropped)"] += 1
    elif w.get("topic_field"): how["openalex topic"] += 1
    elif (w.get("source") or "") and not BOOK_PLATFORMS.search(w["source"]): how["source name"] += 1
    elif w.get("container"): how["crossref container"] += 1
    elif field_of(w) != "unclassified": how["title words"] += 1
    else: how["unclassified"] += 1
print("\n分類の根拠(外部祖先の件数ベース):", dict(how))
