#!/usr/bin/env python3
"""
船舶研究动态监测 v2 - 数据采集 + 统计分析 + 趋势可视化
数据源: arXiv + Semantic Scholar + OpenAlex
涵盖: 期刊论文、预印本、会议论文
"""

import json, os, re, time, sys
from datetime import datetime, timedelta
from xml.etree import ElementTree
from urllib.request import urlopen, Request
from urllib.parse import quote
from collections import defaultdict, Counter

# ─── 路径 ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DATA_PATH = os.path.join(BASE_DIR, "data", "papers.json")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
OUTPUT_HTML = os.path.join(DOCS_DIR, "index.html")

# ─── 研究方向分类 ──────────────────────────────────────
TOPICS = {
    "船舶水动力学": [
        "hydrodynam", "resistance", "propeller", "cavitation", "seakeeping",
        "maneuvering", "hull form", "ship wave", "ship wake", "slamming",
        "added resistance", "propulsion", "drag reduction", "air lubrication",
        "propulsor", "bow shape", "stern", "ship flow", "wetted surface",
        "ship squat", "marine propeller", "ship speed loss"
    ],
    "船舶结构力学与安全": [
        "ship structural", "hull strength", "girder", "ship fatigue",
        "ultimate strength", "ship collision", "ship grounding",
        "buckling ship", "ship fracture", "structural health monit",
        "hull vibration", "ship vibration", "ship stress", "FEM ship",
        "stiffened panel", "crack propagation", "ship damage",
        "hull integrity", "fatigue life"
    ],
    "船舶推进与节能": [
        "ship propulsion", "marine engine", "fuel consumption",
        "waste heat", "emission reduction", "LNG fuel", "alternative fuel marine",
        "ship decarboni", "shaft generator", "ship power",
        "energy saving ship", "EEDI", "ship efficiency",
        "ship electrical", "hybrid propulsion", "SCR"
    ],
    "海洋工程结构物": [
        "offshore platform", "floating production", "FPSO", "semi-submersible",
        "jack-up", "riser", "mooring", "subsea pipeline", "deepwater structure",
        "jacket platform", "floating offshore", "TLP platform", "spar platform",
        "subsea system", "marine pipeline", "offshore structure",
        "compliant tower", "gravity base"
    ],
    "船舶设计与优化": [
        "ship design", "hull form optimization", "parametric design",
        "multi-objective optimization", "conceptual design", "ship layout",
        "ship CAD", "ship CAM", "multidisciplinary optimization",
        "naval architecture", "ship lines", "ship lofting"
    ],
    "船舶智能制造": [
        "shipbuilding", "digital twin", "smart manufacturing",
        "ship welding", "block assembly", "shipyard", "production planning",
        "ship outfitting", "panel line", "ship painting", "modular ship",
        "ship assembly", "steel cutting"
    ],
    "海洋可再生能源": [
        "wave energy", "tidal current", "offshore wind turbine",
        "floating wind", "marine current", "ocean thermal",
        "oscillating water column", "point absorber", "tidal stream",
        "wave power", "wave converter"
    ],
    "船舶噪声与水下辐射": [
        "ship noise", "underwater radiated noise", "ship acoustic",
        "propeller noise", "vibration noise", "acoustic signature",
        "hydroacoustic", "noise reduction", "flow noise",
        "underwater noise emission"
    ],
    "自主船舶与智能航行": [
        "autonomous ship", "unmanned surface", "MASS", "collision avoidance",
        "intelligent navigation", "path planning", "COLREG",
        "situational awareness", "vessel traffic", "smart ship",
        "decision support ship", "autonomous navigation ship"
    ],
    "水下航行器与海洋机器人": [
        "autonomous underwater", "AUV", "ROV", "underwater glider",
        "marine robot", "underwater manipulation", "underwater vehicle",
        "unmanned underwater", "deep sea vehicle", "subsea vehicle",
        "underwater drone"
    ],
    "船舶与海洋工程数值方法": [
        "CFD", "panel method", "boundary element", "SPH",
        "smoothed particle", "lattice Boltzmann", "RANS", "DES ship",
        "LES marine", "numerical simulation", "fluid structure inter",
        "FSI ship", "potential flow", "vortex method"
    ],
}


# ─── 细粒度关键词（每个方向下的研究热点） ────────
SUB_KEYWORDS = {
    "船舶水动力学": {
        "阻力预测": ["resistance prediction","drag prediction","resistance estimat","ship drag"],
        "螺旋桨设计": ["propeller design","propeller optimization","propeller performance","marine propeller"],
        "兴波阻力": ["wave resistance","wave-making","wave making","wave pattern"],
        "粘性流": ["viscous","turbulence model","boundary layer","RANS","wake field"],
        "CFD模拟": ["CFD","computational fluid","numerical simulation","RANS","LES","DES"],
        "船型优化": ["hull form optim","hull optimization","ship hull design","parametric hull"],
        "耐波性": ["seakeeping","sea keeping","ship motion","wave load","response amplitude"],
        "操纵性": ["maneuvering","maneuver","course keeping","turning circle","zigzag"],
    },
    "船舶结构力学与安全": {
        "船体强度": ["hull strength","hull girder","ship strength","ultimate strength"],
        "疲劳分析": ["fatigue life","fatigue assessment","fatigue crack","S-N curve"],
        "碰撞与搁浅": ["ship collision","ship grounding","crashworthiness","impact"],
        "振动分析": ["ship vibration","hull vibration","vibration control","modal analysis"],
        "结构优化": ["structural optimization","weight optimization","topology optimization"],
        "损伤检测": ["damage detection","crack detection","SHM","structural health"],
    },
    "船舶推进与节能": {
        "节能装置": ["energy saving","energy-saving","fuel saving","EEDI"],
        "替代燃料": ["alternative fuel","LNG","hydrogen","ammonia","methanol"],
        "排放控制": ["emission control","carbon emission","SOx","NOx","decarboni"],
        "混合动力": ["hybrid propulsion","hybrid power","battery","electric propulsion"],
        "余热回收": ["waste heat","heat recovery","exhaust gas"],
    },
    "海洋工程结构物": {
        "平台设计": ["platform design","FPSO","semi-submersible","spar","TLP"],
        "立管与锚泊": ["riser","mooring","anchor","tendon","catenary"],
        "海底管道": ["subsea pipeline","pipeline","flowline","riser"],
        "深水技术": ["deepwater","deep water","ultra-deep","deep sea structure"],
        "基础与地基": ["foundation","pile","jacket","gravity base","suction caisson"],
    },
    "自主船舶与智能航行": {
        "路径规划": ["path planning","route planning","trajectory planning"],
        "避碰": ["collision avoidance","COLREG","obstacle avoidance"],
        "自主决策": ["autonomous decision","situation awareness","decision support"],
        "智能感知": ["object detection","perception","sensor fusion","target detection"],
        "运动控制": ["motion control","tracking control","guidance","autopilot"],
    },
    "水下航行器与海洋机器人": {
        "路径规划": ["path planning","AUV path","mission planning"],
        "导航定位": ["navigation","localization","SLAM","positioning","INS","DVL"],
        "水下抓取": ["underwater manipulation","grasping","intervention","dexterous"],
        "目标识别": ["underwater detection","object recognition","target identification","sonar image"],
        "编队控制": ["formation","cooperative","multi-AUV","swarm"],
        "能量管理": ["energy management","battery","wireless charging","energy harves"],
    },
    "船舶与海洋工程数值方法": {
        "CFD方法": ["RANS","DES","LES","DNS","CFD method"],
        "有限元": ["FEM","finite element","finite element analysis"],
        "SPH": ["SPH","smoothed particle","meshless","particle method"],
        "势流方法": ["potential flow","panel method","boundary element"],
        "流固耦合": ["FSI","fluid structure","fluid-structure","coupled analysis"],
    },
}


def classify_sub(title, abstract, topic):
    """返回论文在指定方向下匹配的细粒度关键词"""
    text = (title + " " + abstract).lower()
    sub_kws = SUB_KEYWORDS.get(topic, {})
    matched = []
    for sw_name, kws in sub_kws.items():
        if any(kw.lower() in text for kw in kws):
            matched.append(sw_name)
    return matched


def classify(title, abstract):
    text = (title + " " + abstract).lower()
    domain_q = ["ship","marine","vessel","ocean","maritime","naval","sea","hull",
                "offshore","underwater","aquatic","seaworth","ferry","submarine",
                "port","harbor","船舶","海洋","水动力","watercraft"]
    domain_score = sum(1 for d in domain_q if d in text)
    scores = {}
    for t, kws in TOPICS.items():
        matches = sum(1 for kw in kws if kw.lower() in text)
        if matches >= 2:
            scores[t] = matches * 2 + domain_score
        elif matches == 1 and domain_score >= 2:
            scores[t] = matches + domain_score
        elif matches == 1 and any(kw.lower() in text for kw in kws):
            # Single keyword match, but only count if domain-specific enough
            kw_matched = [kw for kw in kws if kw.lower() in text][0]
            if len(kw_matched) > 6 or any(d in text for d in domain_q[:5]):
                scores[t] = 1 + (domain_score // 2)
    if not scores:
        # Fallback: check if any paper at all relates to domain
        for t, kws in TOPICS.items():
            m = sum(1 for kw in kws if kw.lower() in text)
            if m >= 1:
                scores[t] = m
    best = max(scores, key=scores.get) if scores else None
    sub_kws = classify_sub(title, abstract, best) if best != "其他" else []
    return (best, scores[best], sub_kws) if best else ("其他", 0, [])

def get_journal_rank(journal, config):
    if not journal: return ("", "")
    j = journal.lower().strip().rstrip(".")
    ranks = config.get("journal_rankings", {})
    for tier, names in ranks.items():
        for n in names:
            if n.lower() in j:
                return (tier, n)
    return ("核心期刊", journal[:30])

def extract_doi(title, abstract, arxiv_id=""):
    full = title + " " + abstract
    m = re.search(r'10\.\d{4,}/[\w\.\-/]+', full)
    if m: return m.group(0).rstrip('.')
    if arxiv_id: return f"10.48550/arXiv.{arxiv_id}"
    return ""

# ─── 工具 ───────────────────────────────────────────────
def load_config():
    with open(CONFIG_PATH) as f: return json.load(f)
def save_json(d, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)
def load_existing(p):
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f: return json.load(f)
    return {"papers":[], "updated":None, "history":[]}

# ═══════════════════════════════════════════════════════════
#  arXiv
# ═══════════════════════════════════════════════════════════
ARXIV_API = "http://export.arxiv.org/api/query"

def fetch_arxiv(config):
    cfg = config["sources"]["arxiv"]
    if not cfg.get("enabled"): return []
    queries = config["search_queries"]
    cats = cfg.get("categories",[])
    max_r = cfg.get("max_results",60)
    all_p = {}
    # arXiv API 不适合复杂查询，改用分类独立搜 + 关键词精简
    arxiv_keywords = [
        "ship hydrodynamics", "propeller cavitation", "hull form",
        "offshore platform", "marine renewable energy", "autonomous ship",
        "underwater vehicle", "ship CFD", "ship structural",
        "ship propulsion", "wave energy", "ship maneuvering"
    ]
    for sort_by in ["relevance","submittedDate"]:
        for kw in arxiv_keywords:
            cat_s = " OR ".join(f"cat:{c}" for c in cats)
            query = f"(ti:{kw} OR abs:{kw}) AND ({cat_s})"
            url = ARXIV_API+"?search_query="+quote(query[:2000])+f"&start=0&max_results={max_r//len(arxiv_keywords)}&sortBy={sort_by}&sortOrder=descending"
            try:
                root = ElementTree.fromstring(urlopen(Request(url,headers={"User-Agent":"ShipMonitor/2.0"}),timeout=30).read())
                ns = {"atom":"http://www.w3.org/2005/Atom","arxiv":"http://arxiv.org/schemas/atom"}
                for e in root.findall("atom:entry",ns):
                    pid = e.find("atom:id",ns).text.strip()
                    if pid in all_p: continue
                    ttl = e.find("atom:title",ns).text.strip().replace("\n"," ")
                    abs_ = e.find("atom:summary",ns).text.strip().replace("\n"," ")
                    pub = e.find("atom:published",ns).text[:10]
                    au = [a.find("atom:name",ns).text for a in e.findall("atom:author",ns) if a.find("atom:name",ns) is not None]
                    aid = extract_arxiv_id(pid)
                    tp,ts,sk = classify(ttl, abs_)
                    all_p[pid] = dict(id=aid or pid, title=ttl, abstract=abs_[:500], authors=au[:5],
                        published=pub, year=pub[:4], source="arXiv", url=pid, pdf_url="",
                        doi=extract_doi(ttl,abs_,aid), topic=tp, topic_score=ts, sub_kws=sk,
                        journal="arXiv Preprint", journal_rank="预印本", cited_by=0,
                        institutions=[], concepts=[], fetched=datetime.now().strftime("%Y-%m-%d %H:%M"))
                time.sleep(2)
            except Exception as ex: print(f"  [WARN] arXiv {kw}: {ex}")
    return list(all_p.values())

def extract_arxiv_id(url):
    m = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url)
    return m.group(1) if m else None

# ═══════════════════════════════════════════════════════════
#  OpenAlex（覆盖期刊论文、会议论文、图书章节等）
# ═══════════════════════════════════════════════════════════
OA_API = "https://api.openalex.org/works"
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"

def fetch_openalex(config):
    """OpenAlex API fetcher with polite pool + retry logic"""
    cfg = config["sources"].get("openalex",{})
    if not cfg.get("enabled"): return []
    queries = config["search_queries"][:5]
    max_r = min(cfg.get("max_results",120), 200)
    per_q = max(20, max_r // len(queries))
    all_p = {}; dois_seen = set()
    polite = "mailto=jison@users.noreply.github.com"
    ua = "ShipMonitor/2.0 (mailto:jison@users.noreply.github.com)"

    for q in queries:
        for attempt in range(3):
            try:
                params = dict(search=q, per_page=per_q, sort="cited_by_count:desc",
                    filter="from_publication_date:2021-01-01",
                    select="id,doi,title,abstract_inverted_index,authorships,primary_location,cited_by_count,publication_date,type")
                url = OA_API + "?" + "&".join(f"{k}={quote(str(v))}" for k,v in params.items()) + "&" + polite
                data = json.load(urlopen(Request(url, headers={"User-Agent": ua}), timeout=20))
                for w in data.get("results",[]):
                    wid = w.get("id","")
                    doi = (w.get("doi") or "").replace("https://doi.org/","")
                    if doi in dois_seen or wid in all_p: continue
                    dois_seen.add(doi); dois_seen.add(wid)
                    ttl = w.get("title","")
                    if not ttl or len(ttl)<5: continue
                    pub = (w.get("publication_date") or "2023")[:10]
                    year = pub[:4]; cited = w.get("cited_by_count",0)
                    loc = w.get("primary_location") or {}
                    src = loc.get("source") or {}
                    jour = src.get("display_name","") or ""
                    ws_type = w.get("type","") or ""
                    ranks = config.get("journal_rankings",{})
                    jrank = "一区/顶刊" if any(n in jour.lower() for n in ranks.get("一区/顶刊",[])) else \
                            "二区/重要" if any(n in jour.lower() for n in ranks.get("二区/重要",[])) else \
                            "核心期刊" if jour else ("其他" if ws_type in ("article","review") else "预印本")
                    au_info = []; insts_set = set()
                    for a in w.get("authorships",[]):
                        name = (a.get("author") or {}).get("display_name","")
                        insts = [i.get("display_name","") for i in (a.get("institutions") or [])]
                        for i_ in insts[:2]:
                            if i_: insts_set.add(i_)
                        au_info.append({"name":name, "institutions":insts[:2]})
                    # Reconstruct abstract from inverted index
                    inv_idx = w.get("abstract_inverted_index") or {}
                    if inv_idx:
                        word_positions = []
                        for word, positions in inv_idx.items():
                            for pos in positions:
                                word_positions.append((pos, word))
                        word_positions.sort(key=lambda x: x[0])
                        abstract_text = " ".join(w for _, w in word_positions)[:800]
                    else:
                        abstract_text = ""
                    tp, ts, sk = classify(ttl, abstract_text)
                    all_p[wid] = dict(id=wid, title=ttl, abstract=abstract_text,
                        authors=[a["name"] for a in au_info[:5]],
                        published=pub, year=year, source="OpenAlex",
                        url=f"https://doi.org/{doi}" if doi else wid, pdf_url="",
                        doi=doi, topic=tp, topic_score=ts, sub_kws=sk,
                        journal=jour[:40] if jour else ws_type, journal_rank=jrank,
                        cited_by=cited, institutions=list(insts_set)[:3],
                        concepts=[], fetched=datetime.now().strftime("%Y-%m-%d %H:%M"))
                time.sleep(3.5)
                break
            except Exception as ex:
                if "429" in str(ex):
                    wait = 8 * (attempt + 1)
                    print(f"  [WARN] 429, retry in {wait}s ({attempt+1}/3)")
                    time.sleep(wait)
                    continue
                print(f"  [WARN] OpenAlex '{q[:20]}': {ex}")
                break
    return list(all_p.values())
def fetch_semantic(config):
    cfg = config["sources"]["semantic_scholar"]
    if not cfg.get("enabled"): return []
    queries = config["search_queries"][:3]
    limit = min(cfg.get("limit",20), 50)
    fields = "title,authors,year,url,externalIds,abstract,venue,citationCount,publicationDate,journal"
    all_p = []; seen = set()
    for q in queries:
        url = S2_API+f"?query={quote(q)}&limit={limit//len(queries)+1}&fields={fields}&year=2021-"
        try:
            data = json.load(urlopen(Request(url,headers={"User-Agent":"ShipMonitor/2.0"}),timeout=15))
            for w in data.get("data",[]):
                pid = w.get("paperId","")
                if pid in seen: continue
                seen.add(pid)
                ttl = w.get("title","")
                if not ttl or len(ttl)<5: continue
                abs_ = w.get("abstract","")
                if not abs_: continue
                year = w.get("year",""); pub = w.get("publicationDate","") or str(year)
                jour = ((w.get("journal") or {}).get("name","") or w.get("venue","") or "")
                cited = w.get("citationCount",0)
                ext = w.get("externalIds",{})
                doi = ext.get("DOI","")
                arx = ext.get("ArXiv","")
                au = [a.get("name","") for a in (w.get("authors") or [])[:5]]
                tp,ts,sk = classify(ttl, abs_)
                ranks = config.get("journal_rankings",{})
                jrank = "一区/顶刊" if any(n in jour.lower() for n in ranks.get("一区/顶刊",[])) else \
                        "二区/重要" if any(n in jour.lower() for n in ranks.get("二区/重要",[])) else "核心期刊"
                all_p.append(dict(id=pid, title=ttl, abstract=abs_[:500], authors=au,
                    published=pub[:10], year=str(year), source="Semantic Scholar",
                    url=w.get("url",f"https://www.semanticscholar.org/paper/{pid}"), pdf_url="",
                    doi=doi or extract_doi(ttl,abs_,arx), topic=tp, topic_score=ts, sub_kws=sk,
                    journal=jour[:40] if jour else "", journal_rank=jrank,
                    cited_by=cited, institutions=[], concepts=[],
                    fetched=datetime.now().strftime("%Y-%m-%d %H:%M")))
            time.sleep(3)
        except: pass
    return all_p

# ═══════════════════════════════════════════════════════════
#  合并与统计
# ═══════════════════════════════════════════════════════════
def merge_papers(new_p, existing):
    old = existing.get("papers",[]); hist = existing.get("history",[])
    exist_ids = set()
    for p in old:
        exist_ids.add(p["id"])
        if p.get("doi"): exist_ids.add(p["doi"])
    dedup = [p for p in new_p if p["id"] not in exist_ids and p.get("doi","") not in exist_ids]
    merged = dedup + old
    today = datetime.now().strftime("%Y-%m-%d")
    if dedup:
        hist.append({"date":today, "new":len(dedup), "total":len(merged)})
        hist = hist[-90:]
    return {"papers":merged, "updated":datetime.now().strftime("%Y-%m-%d %H:%M"),
            "today_new":len(dedup), "total":len(merged), "history":hist}


def classify_country(inst_name):
    """判断机构属于国内还是国外"""
    if not inst_name: return "未知"
    # 包含中文 → 国内
    for ch in inst_name:
        if ord(ch) > 0x4E00:
            return "🇨🇳 国内"
    # 中文相关关键词
    cn_kw = ["China","Chinese","Beijing","Shanghai","Tianjin","Nanjing","Wuhan",
             "Harbin","Dalian","Guangzhou","Hong Kong","Taiwan","Macau",
             "Ocean University","Maritime University","科技大学",
             "Huangpu","Jiangnan","COSCO","CSSC","中国"]
    for kw in cn_kw:
        if kw.lower() in inst_name.lower():
            return "🇨🇳 国内"
    # 常见国际机构
    intl_kw = ["University of","Institute of","Centre for","Center for",
               "Laboratory","College","School of","Department of",
               "University of"]
    for kw in intl_kw:
        if kw.lower() in inst_name.lower():
            return "🌍 国外"
    return "🌍 国外"

def compute_stats(papers):
    tc = Counter(); yc = Counter(); sc = Counter(); jc = Counter()
    tp = defaultdict(list)
    author_counter = Counter()
    inst_counter = Counter()
    topic_authors = defaultdict(Counter)
    topic_insts = defaultdict(Counter)
    country_counter = {}
    kw_counter = Counter()
    kw_year_counter = defaultdict(lambda: Counter())
    
    for p in papers:
        t = p.get("topic","其他"); tc[t] += 1; tp[t].append(p)
        y = p.get("year",""); yc[int(y)] += 1 if y.isdigit() else 0
        sc[p.get("source","")] += 1
        j = p.get("journal_rank",""); jc[j] += 1 if j else 0
        
        # 作者统计
        for au in p.get("authors",[]):
            au_name = au.strip()
            if au_name and len(au_name) > 1:
                author_counter[au_name] += 1
                topic_authors[t][au_name] += 1
        
        # 机构统计
        for inst in p.get("institutions",[]):
            inst_name = inst.strip()
            if inst_name and len(inst_name) > 3:
                short = inst_name.split(",")[0].split(";")[0].strip()[:60]
                inst_counter[short] += 1
                topic_insts[t][short] += 1
                # 地域统计
                country = classify_country(short)
                if country not in country_counter:
                    country_counter[country] = {"papers":0, "institutions":set()}
                country_counter[country]["papers"] += 1
                country_counter[country]["institutions"].add(short)
        for skw in p.get("sub_kws",[]):
            kw_counter[skw] += 1
            y = p.get("year","")
            if y.isdigit():
                kw_year_counter[skw][y] += 1
    
    years = sorted(yc); yr = f"{min(years)}-{max(years)}" if years else "—"
    
    # 每个方向的细粒度关键词统计
    keyword_topic = {}
    for t, ps in tp.items():
        kw_t = Counter()
        for p in ps:
            for sk in p.get("sub_kws",[]):
                kw_t[sk] += 1
        keyword_topic[t] = [{"name":k,"count":v} for k,v in kw_t.most_common(15)]
    
    # 每个方向论文的平均引用
    topic_impact = {}
    for t, ps in tp.items():
        c = [p.get("cited_by",0) for p in ps]
        topic_impact[t] = {"count":len(ps), "avg_cited":round(sum(c)/len(c),1) if c else 0,
                           "max_cited":max(c) if c else 0}
    
    # 热点论文（含领域相关性加权）
    now = datetime.now()
    # 船舶领域关健词白名单
    domain_boost_kws = ["ship","marine","vessel","ocean","offshore","underwater","submarine",
        "seakeeping","hydrodynam","propeller","cavitation","hull","CFD","platform",
        "mooring","riser","autonomous","AUV","ROV","wave energy","offshore wind",
        "shipbuilding","propulsion","maneuvering","naval","maritime","harbor",
        "shipyard","浮式","船舶","航运","port","ferry","breakwater","coastal"]
    def hot_score(p):
        cited = p.get("cited_by",0)
        try: d = (now - datetime.strptime(p["published"][:10],"%Y-%m-%d")).days
        except: d = 365
        base = cited * 0.6 + max(0, 365 - d) * 0.4
        # 领域相关性加权
        ttl_abs = (p.get("title","") + " " + p.get("abstract","")).lower()
        domain_matches = sum(1 for kw in domain_boost_kws if kw in ttl_abs)
        if domain_matches >= 3: factor = 1.5
        elif domain_matches >= 1: factor = 1.2
        else: factor = 0.3  # 非领域论文大幅降权
        return base * factor
    hot = sorted(papers, key=lambda p: hot_score(p), reverse=True)[:20]
    
    # 作者/机构整理
    def top_n(counter, n=10):
        return [{"name":k, "count":v} for k,v in counter.most_common(n)]
    
    return dict(
        topic_counts=dict(tc.most_common()),
        year_counts={str(k):yc[k] for k in years},
        source_counts=dict(sc.most_common()),
        journal_rank_counts=dict(jc.most_common()),
        topic_impact=topic_impact, topic_papers={t:tp[t] for t in tp},
        total_topics=len(tc), year_range=yr,
        hot_papers=hot,
        topic_year={t: Counter(p.get("year","") for p in ps) for t,ps in tp.items()},
        keyword_trends={kw: dict(sorted(yrs.items())) for kw, yrs in kw_year_counter.items()} if kw_year_counter else {},
        keyword_hot=[{"name":k,"count":v} for k,v in kw_counter.most_common(30)],
        keyword_topic=keyword_topic,
        # 新增：作者与机构
        top_authors=top_n(author_counter, 15),
        top_institutions=top_n(inst_counter, 20),
        topic_top_authors={t: top_n(ca, 5) for t,ca in topic_authors.items()},
        topic_top_institutions={t: top_n(ci, 8) for t,ci in topic_insts.items()},
        total_authors=len(author_counter),
        total_institutions=len(inst_counter),
        country_stats={k:{"papers":v["papers"],"institutions":len(v["institutions"])} for k,v in country_counter.items()},
        country_ratio={k: round(v["papers"]/max(v["papers"] for v in country_counter.values())*100,1) for k,v in country_counter.items()} if country_counter else {},
    )

# ═══════════════════════════════════════════════════════════
#  HTML生成
# ═══════════════════════════════════════════════════════════
CHART_CDN = "chart.min.js"  # 本地加载，无需外网CDN

COLORS = ["#5B8FA8","#7BA9A0","#B5A88D","#C98B7A","#A88BAB",
          "#8FAB8F","#C9A88D","#7FA8C9","#B58F8F","#8FA8A8"]
RANK_COLORS = {"一区/顶刊":"#C0392B","二区/重要":"#E67E22","核心期刊":"#2980B9","预印本":"#7F8C8D","其他":"#95A5A6"}


# ─── BibTeX 生成 ──────────────────────────────────────────
def bibtex_entry(p, key_prefix="ship"):
    """为单篇论文生成 BibTeX"""
    au = p.get("authors",[])
    authors = " and ".join(au[:6])
    if len(au) > 6: authors += " and others"
    title = p.get("title","").strip().rstrip(".")
    journal = p.get("journal","") or "unknown"
    year = p.get("year","") or "2024"
    doi = p.get("doi","")
    url = p.get("url","")
    
    # 生成唯一key
    first_au = au[0].split(",")[0].split()[-1] if au else "Unknown"
    first_au = first_au.replace(" ","").replace(".","")
    key = f"{key_prefix}_{first_au}{year}"
    
    b = f"@article{{{key},\n"
    b += f"  author = {{{authors}}},\n"
    b += f"  title = {{{title}}},\n"
    b += f"  journal = {{{journal}}},\n"
    b += f"  year = {{{year}}},\n"
    if doi: b += f"  doi = {{{doi}}},\n"
    if url: b += f"  url = {{{url}}},\n"
    b += "}"
    return b, key


def generate_weekly_report(data, config):
    """生成周报摘要页面"""
    papers = data.get("papers",[])
    history = data.get("history",[])
    
    # 按中国周（周一开始）聚合
    from datetime import date, timedelta
    today = date.today()
    # 本周一
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    two_mondays = this_monday - timedelta(days=14)
    
    # 按周分组统计
    def week_group(week_start):
        ws = week_start.strftime("%Y-%m-%d")
        we = (week_start + timedelta(days=6)).strftime("%Y-%m-%d")
        weekly_papers = [p for p in papers if ws <= p.get("published","")[:10] <= we]
        return ws, we, weekly_papers
    
    this_ws, this_we, this_week = week_group(this_monday)
    last_ws, last_we, last_week = week_group(last_monday)
    
    # 本周统计
    topics_this = Counter(p.get("topic","其他") for p in this_week)
    hot_this = sorted(this_week, key=lambda p: p.get("cited_by",0), reverse=True)[:5]
    
    # 比上周变化
    topics_last = Counter(p.get("topic","其他") for p in last_week)
    changes = {}
    for t in set(list(topics_this.keys()) + list(topics_last.keys())):
        c = topics_this.get(t,0) - topics_last.get(t,0)
        if c != 0: changes[t] = c
    
    # 本周机构/作者
    insts = Counter()
    for p in this_week:
        for i in p.get("institutions",[]):
            if i: insts[i.split(",")[0].strip()[:50]] += 1
    
    # 中文周数
    week_num = today.isocalendar()[1]
    year = today.year
    
    return dict(
        week_num=week_num, year=year,
        date_range=f"{this_ws} ~ {this_we}",
        total_this=len(this_week),
        total_last=len(last_week),
        topics_this=dict(topics_this.most_common()),
        changes=changes,
        hot_papers=hot_this,
        new_institutions=insts.most_common(10),
    )


def gen_html(data, config):
    papers = data.get("papers",[])
    stats = compute_stats(papers)
    updated = data.get("updated","")
    total = data.get("total",0)

    tl = list(stats["topic_counts"].keys())
    tcols = {t:COLORS[i%len(COLORS)] for i,t in enumerate(tl)}
    
    jrc = stats["journal_rank_counts"]
    top_j = sum(v for k,v in jrc.items() if k in ("一区/顶刊","二区/重要"))
    
    topic_impact = stats["topic_impact"]
    hot_papers = stats["hot_papers"]
    

    # ── 热度关键词 ──
    hot_kws = stats.get("keyword_hot",[])[:20]
    kw_trends = stats.get("keyword_trends",{})
    kw_html = ""
    for kw in hot_kws:
        n = kw["name"]
        trend = kw_trends.get(n, {})
        # Show yearly counts as a simple bar
        years_sorted = sorted(trend.keys())
        counts = [trend[y] for y in years_sorted]
        max_c = max(counts) if counts else 1
        bars = ""
        for i, y in enumerate(years_sorted):
            pct = int(counts[i] / max_c * 100)
            bars += '<div class="kw-bar"><span class="kw-y">' + y + '</span><div class="kw-fill-w"><div class="kw-fill" style="width:' + str(pct) + '%"></div></div><span class="kw-c">' + str(counts[i]) + '</span></div>'
        kw_html += '<div class="kw-item"><div class="kw-name">' + n + '</div><div class="kw-count">' + str(kw["count"]) + '</div><div class="kw-trend">' + bars + '</div></div>'
        # ── 地域分析 ──
    cn_count = stats.get("country_stats",{}).get("🇨🇳 国内",{}).get("papers",0)
    intl_count = stats.get("country_stats",{}).get("🌍 国外",{}).get("papers",0)
    cn_ratio = stats.get("country_ratio",{}).get("🇨🇳 国内",50)
    intl_ratio = stats.get("country_ratio",{}).get("🌍 国外",50)
    cn_insts = stats.get("country_stats",{}).get("🇨🇳 国内",{}).get("institutions",0)
    intl_insts = stats.get("country_stats",{}).get("🌍 国外",{}).get("institutions",0)
    
    # 按论文-机构出现次数排名
    cn_order = cn_count >= intl_count
    bar_top = '<div class="cbar cn" style="width:' + str(cn_ratio) + '%"></div>'
    bar_bot = '<div class="cbar intl" style="width:' + str(intl_ratio) + '%"></div>'
    if not cn_order:
        bar_top, bar_bot = bar_bot, bar_top
        
    country_html = (
        '<div class="country-grid">'
        '<div class="cg-item ' + ('cn' if cn_order else 'intl') + '">'
        '<span class="cg-flag">' + ('🇨🇳' if cn_order else '🌍') + '</span>'
        '<span class="cg-name">' + ('国内' if cn_order else '国外') + '</span>'
        '<span class="cg-count">' + str(cn_count if cn_order else intl_count) + '篇</span>'
        '<span class="cg-insts">' + str(cn_insts if cn_order else intl_insts) + '个机构</span>'
        '</div>'
        '<div class="country-bar-inner">' + bar_top + bar_bot + '</div>'
        '<div class="cg-item ' + ('intl' if cn_order else 'cn') + '">'
        '<span class="cg-flag">' + ('🌍' if cn_order else '🇨🇳') + '</span>'
        '<span class="cg-name">' + ('国外' if cn_order else '国内') + '</span>'
        '<span class="cg-count">' + str(intl_count if cn_order else cn_count) + '篇</span>'
        '<span class="cg-insts">' + str(intl_insts if cn_order else cn_insts) + '个机构</span>'
        '</div>'
        '</div>'
    )

    # ── 机构列表 ──
    inst_html = ""
    for inst in stats["top_institutions"][:15]:
        n = inst["name"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        inst_html += '<div class="ai-item"><span class="ai-name">' + n + '</span><span class="ai-count">' + str(inst["count"]) + '</span></div>\n'
    
    auth_html = ""
    for au in stats["top_authors"][:12]:
        n = au["name"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        auth_html += '<div class="ai-item"><span class="ai-name">' + n + '</span><span class="ai-count">' + str(au["count"]) + '</span></div>\n'
    
    cards = ('<div class="stats-row">'
        '<div class="sc"><span class="n">' + str(total) + '</span><span class="l">论文总数</span></div>'
        '<div class="sc"><span class="n">' + str(stats["total_topics"]) + '</span><span class="l">研究方向</span></div>'
        '<div class="sc"><span class="n">' + str(stats["total_authors"]) + '</span><span class="l">作者</span></div>'
        '<div class="sc"><span class="n">' + str(stats["total_institutions"]) + '</span><span class="l">机构</span></div>'
        '<div class="sc"><span class="n">' + str(top_j) + '</span><span class="l">顶刊/重要</span></div>'
        '<div class="sc"><span class="n">' + str(len(stats["source_counts"])) + '</span><span class="l">数据源</span></div>'
        '</div>')
    
    # ── Chart.js 数据 ──
    # Force years 2021-2026 for consistent axis
    yl = [str(y) for y in range(2021, 2027)]
    yd = [stats["year_counts"].get(y, 0) for y in yl]
    cum = []
    running = 0
    for v in yd:
        running += v
        cum.append(running)
    
    tl_j = json.dumps(tl, ensure_ascii=False)
    td_j = json.dumps([stats["topic_counts"][t] for t in tl], ensure_ascii=False)
    tc_j = json.dumps([tcols[t] for t in tl], ensure_ascii=False)
    yl_j = json.dumps(yl); yd_j = json.dumps(yd); cum_j = json.dumps(cum)
    jrc_k = json.dumps(list(stats["journal_rank_counts"].keys()), ensure_ascii=False)
    jrc_v = json.dumps(list(stats["journal_rank_counts"].values()), ensure_ascii=False)
    
    # ── 热点论文 ──
    hot_items = ""
    for i,p in enumerate(hot_papers[:10]):
        c = p.get("cited_by",0)
        jrnk = p.get("journal_rank","")
        doi = p.get("doi","")
        pid = p.get("url","#")
        doi_h = '<a href="https://doi.org/' + doi + '" class="doi" target="_blank">' + doi[:35] + '</a>' if doi else ""
        jrnk_h = '<span class="rk">' + jrnk + '</span>' if jrnk else ""
        hot_items += ('<div class="hp" data-pid="' + pid + '">'
            '<span class="hp-n">' + str(i+1) + '</span>'
            '<button class="bm-btn" onclick="toggleBm(this)" title="收藏">☆</button>'
            '<div class="hp-b">'
            '<div class="hp-t"><a href="' + pid + '" target="_blank">' + p["title"][:90] + '</a></div>'
            '<div class="hp-m"><span>' + p.get("published","")[:10] + '</span><span class="ci">📊' + str(c) + '</span>' + jrnk_h + doi_h + '</div>'
            '</div></div>')
    
    # ── 各方向 ──
    topics = ""
    for i,t in enumerate(tl):
        t_kws = stats.get("keyword_topic",{}).get(t,[])[:4]
        ps = sorted(stats["topic_papers"].get(t,[]), key=lambda x: x.get("cited_by",0), reverse=True)
        imp = topic_impact[t]; col = tcols[t]
        items = ""
        for p in ps:  # Show all papers
            ci = p.get("cited_by",0); doi = p.get("doi","")
            au = ", ".join(p.get("authors",[])[:2])
            pid = p.get("url","#")
            yr = p.get("year","") or p.get("published","")[:4]
            jr = p.get("journal_rank","")
            doi_h = '<a href="https://doi.org/' + doi + '" class="doi">📎' + doi[:25] + '</a>' if doi else ""
            insts = p.get("institutions",[])
            inst_h = '<span class="inst">🏛️ ' + insts[0][:35] + '</span>' if insts else ""
            ci_h = '<span class="ci">📊'+str(ci)+'</span>' if ci else ""
            au_h = '<span>'+au[:40]+'</span>' if au else ""
            sk_pi = p.get("sub_kws",[])
            sk_h = '<span class="sk">#' + '#'.join(sk_pi[:3]) + '</span>' if sk_pi else ""
            items += ('<div class="pi" data-pid="' + pid + '" data-year="' + yr + '" data-jrank="' + jr + '">'
                '<div class="pi-t">'
                '<button class="bm-btn" onclick="toggleBm(this)" title="收藏">☆</button> '
                '<a href="' + pid + '" target="_blank">' + p["title"][:80] + '</a></div>'
                '<div class="pi-m"><span>' + p.get("published","")[:10] + '</span>' + au_h + sk_h + ci_h + inst_h + doi_h + '</div></div>')
        more_h = ""
        topics += ('<div class="ts">'
            '<div class="th" onclick="tt(this)">'
            '<span class="dot" style="background:' + col + '"></span><span class="tn">' + t + '</span>'
            '<span class="tc">' + str(stats["topic_counts"][t]) + '篇</span>'
            '<span class="ti">📊均引' + str(imp["avg_cited"]) + '</span>'
            '<span class="tic">▸</span>'
            '</div><div class="tb" style="display:none">' + items + more_h + '</div></div>')
    
    html = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
    html += '<title>船舶研究动态 · 统计看板</title>\n<link rel="stylesheet" href="style.css">\n'
    html += '<script src="' + CHART_CDN + '"></script>\n</head>\n<body>\n'
    html += '<header>\n<h1>🚢 船舶与海洋工程研究动态监测</h1>\n'
    html += '<p class="sub">多源数据分析 · 每3天自动更新 · 2021-2026</p>\n'
    html += '<p class="meta">🕐 ' + updated + ' | arXiv + OpenAlex + Semantic Scholar</p>\n<p style="text-align:center;font-size:.78rem;margin-top:6px"><a href="weekly.html">📋 \u67e5\u770b\u5b8c\u6574\u5468\u62a5 \u2192</a></p>\n</header>\n<main>\n'
    html += cards + '\n'
    html += '<div class="charts-row">\n'
    html += '<div class="cc"><h2>📊 研究方向分布</h2><div class="cw"><canvas id="c1"></canvas></div></div>\n'
    html += '<div class="cc"><h2>📈 发文趋势</h2><div class="cw"><canvas id="c2"></canvas></div></div>\n'
    html += '<div class="cc"><h2>🏆 期刊等级</h2><div class="cw"><canvas id="c3"></canvas></div></div>\n</div>\n'
    html += '<section class="hot"><h2>🔥 热点论文 · 综合排名</h2><p class="hint">引用+时效加权</p>' + hot_items + '</section>\n'
    html += '<section class="kw-section"><h2>🔍 研究热度关键词 Top 20</h2><div class="kw-grid">' + kw_html + '</div></section>\n'
    hl = ""
    if hot_papers:
        tp = hot_papers[0]
        doi = tp.get("doi","")
        dh = '<a href="https://doi.org/'+doi+'">'+doi[:30]+'</a>' if doi else ""
        au = ", ".join(tp.get("authors",[])[:2])
        jour = tp.get("journal","")[:20]
        top = tp.get("topic","")
        url = tp.get("url","#")
        hl = '<div class="hl"><span class="hl-badge">🔥 本期亮点</span><span class="hl-txt"><b><a href="' + url + '" target="_blank">' + tp["title"][:80] + '</a></b> 由 ' + au + ' 等人完成，发表在 <b>' + jour + '</b>，属于<b>' + top + '</b>方向。已被引用 ' + str(tp.get("cited_by",0)) + ' 次。' + dh + '</span></div>'
    html += hl + '\n'
    html += '<section class="country-s"><h2>🌏 地域分布 · 国内 vs 国外</h2>' + country_html + '</section>\n'
    html += '<section class="ai-s"><h2>🏫 高产机构 Top 15</h2><div class="ai-l">' + inst_html + '</div></section>\n'
    html += '<section class="ai-s"><h2>👨‍🔬 活跃作者 Top 12</h2><div class="ai-l">' + auth_html + '</div></section>\n'
    html += '<section class="detail"><h2>📋 研究方向详情</h2>\n'
    # Direction filter tabs
    filter_tabs = '<div class="df">'
    filter_tabs += '<button class="df-btn active" data-dir="all" onclick="filterDir(\'all\')">📌 全部</button>'
    filter_tabs += '<button class="df-btn" data-dir="⭐bookmark" onclick="filterDir(\'⭐bookmark\')">⭐ 收藏</button>'
    for t in tl:
        col = tcols[t]
        esc_t = t.replace("&","&amp;").replace("'","")
        filter_tabs += '<button class="df-btn" data-dir="' + esc_t + '" onclick="filterDir(this.getAttribute(\'data-dir\'))" style="border-left:3px solid ' + col + '">' + esc_t + '</button>'
    filter_tabs += '</div>'
    html += filter_tabs + '\n'
    # ── 搜索与筛选栏 ──
    html += '<div class="search-bar">\n'
    html += '<input type="text" id="ps" class="ps-input" placeholder="🔍 搜论文标题/作者..." oninput="uf()">\n'
    html += '<select id="yrf" class="sf" onchange="uf()"><option value="all">📅 全部年份</option><option value="2026">2026</option><option value="2025">2025</option><option value="2024">2024</option><option value="2023">2023</option><option value="2022">2022</option><option value="2021">2021</option></select>\n'
    html += '<select id="jrf" class="sf" onchange="uf()"><option value="all">🏆 全部期刊</option><option value="一区/顶刊">一区/顶刊</option><option value="二区/重要">二区/重要</option><option value="核心期刊">核心期刊</option><option value="预印本">预印本</option><option value="其他">其他</option></select>\n'
    html += '<span class="result-count" id="rc"></span>\n'
    html += '</div>\n'
    html += '<div class="tf"><input type="text" id="ts" placeholder="🔍 搜研究方向..." oninput="ft()"></div>\n'
    html += topics + '</section>\n</main>\n'
    html += '<footer><p>每3天08:00自动更新 · <a href="https://github.com/Jison-hue/ship-research-monitor">GitHub</a></p></footer>\n'
    html += '<script>\n'
    html += 'new Chart(c1,{type:"bar",data:{labels:' + tl_j + ',datasets:[{label:"论文数",data:' + td_j + ',backgroundColor:' + tc_j + ',borderRadius:3}]},options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{color:"rgba(0,0,0,0.04)"}},y:{grid:{display:false}}}}});\n'
    html += 'new Chart(c2,{type:"bar",data:{labels:' + yl_j + ',datasets:[{label:"新增",data:' + yd_j + ',backgroundColor:"rgba(91,143,168,0.6)",order:2},{label:"累计",data:' + cum_j + ',type:"line",borderColor:"#C98B7A",fill:true,tension:0.3,pointRadius:3,order:1}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"top",labels:{font:{size:12}}}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:"rgba(0,0,0,0.04)"}}}}});\n'
    html += 'new Chart(c3,{type:"doughnut",data:{labels:' + jrc_k + ',datasets:[{data:' + jrc_v + ',backgroundColor:["#C0392B","#E67E22","#2980B9","#7F8C8D","#95A5A6"]}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{font:{size:11}}}}}});\n'
    html += 'function tt(el){var b=el.nextElementSibling,i=el.querySelector(".tic");b.style.display=b.style.display=="block"?"none":"block";i.textContent=b.style.display=="block"?"▾":"▸";}\n'
    html += 'function ft(){var q=document.getElementById("ts").value.toLowerCase();document.querySelectorAll(".ts").forEach(function(s){s.style.display=s.querySelector(".tn").textContent.toLowerCase().includes(q)?"":"none";});}\n'
    html += '/* ─── 搜索筛选函数 ─── */\n'
    html += 'function uf(){var yr=document.getElementById("yrf").value;var jr=document.getElementById("jrf").value;var q=document.getElementById("ps").value.toLowerCase().trim();document.querySelectorAll(".pi").forEach(function(pi){var py=pi.getAttribute("data-year")||"";var pj=pi.getAttribute("data-jrank")||"";var t=(pi.querySelector(".pi-t a")||{}).textContent||"";t=t.toLowerCase();var m=(pi.querySelector(".pi-m")||{}).textContent||"";m=m.toLowerCase();var y_ok=yr==="all"||py===yr;var j_ok=jr==="all"||pj===jr;var s_ok=!q||t.includes(q)||m.includes(q);pi.style.display=(y_ok&&j_ok&&s_ok)?"":"none"});var v=document.querySelectorAll(".pi:not([style*=none])").length;document.getElementById("rc").textContent=v>0?"找到 "+v+" 篇":""}\n'
    html += 'function af(){uf()}\n'
    html += 'function ps(){uf()}\n'
    html += '/* ─── 文献收藏 ─── */\n'
    html += 'function getBm(){try{return JSON.parse(localStorage.getItem(\'ship_bm\')||\'[]\')}catch(e){return []}}\n'
    html += 'function saveBm(bm){localStorage.setItem(\'ship_bm\',JSON.stringify(bm))}\n'
    html += 'function toggleBm(btn){var pid=btn.closest(\'[data-pid]\').getAttribute(\'data-pid\');var bm=getBm();var idx=bm.indexOf(pid);if(idx>-1){bm.splice(idx,1);btn.textContent=\'☆\';btn.classList.remove(\'bm-on\')}else{bm.push(pid);btn.textContent=\'★\';btn.classList.add(\'bm-on\')}saveBm(bm)}\n'
    html += 'function filterDir(dir){document.querySelectorAll(\'.df-btn\').forEach(function(b){b.classList.remove(\'active\')});document.querySelectorAll(\'.ts\').forEach(function(s){s.style.display=\'none\'});if(dir===\'all\'){document.querySelectorAll(\'.ts\').forEach(function(s){s.style.display=\'\'})}else if(dir===\'⭐bookmark\'){var bm=getBm();document.querySelectorAll(\'.ts\').forEach(function(s){var show=false;s.querySelectorAll(\'[data-pid]\').forEach(function(p){p.style.display=bm.indexOf(p.getAttribute(\'data-pid\'))>-1?\'\':\'none\';if(p.style.display!=\'none\')show=true});s.style.display=show?\'\':\'none\';var tic=s.querySelector(\'.tic\');var tb=s.querySelector(\'.tb\');if(show&&tic&&tb){tic.textContent=\'▾\';tb.style.display=\'block\'}})}else{document.querySelectorAll(\'.ts\').forEach(function(s){var t=s.querySelector(\'.tn\');if(t&&t.textContent.trim()===dir){s.style.display=\'\'}})};document.querySelectorAll(\'.df-btn\').forEach(function(b){if(b.getAttribute(\'data-dir\')===dir)b.classList.add(\'active\')})}\n'
    html += 'function syncBm(){var bm=getBm();document.querySelectorAll(\'[data-pid]\').forEach(function(el){var pid=el.getAttribute(\'data-pid\');var btn=el.querySelector(\'.bm-btn\');if(btn){if(bm.indexOf(pid)>-1){btn.textContent=\'★\';btn.classList.add(\'bm-on\')}else{btn.textContent=\'☆\';btn.classList.remove(\'bm-on\')}}})}\n'
    html += 'document.addEventListener(\'DOMContentLoaded\',syncBm);\n'
    html += '</script>\n</body>\n</html>\n'
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    print("="*50); print(f"🚢 船舶研究动态监测 v2"); print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"); print("="*50)
    config = load_config(); existing = load_existing(DATA_PATH); all_new = []
    print("\n📄 arXiv..."); 
    try: p=fetch_arxiv(config); print(f"   ✅ {len(p)}"); all_new.extend(p)
    except Exception as e: print(f"   ❌ {e}")
    print("📘 Semantic Scholar...")
    try: p=fetch_semantic(config); print(f"   ✅ {len(p)}"); all_new.extend(p)
    except Exception as e: print(f"   ❌ {e}")
    print("🌐 OpenAlex...")
    try: p=fetch_openalex(config); print(f"   ✅ {len(p)}"); all_new.extend(p)
    except Exception as e: print(f"   ❌ {e}")
    print(f"\n🔄 合并..."); merged = merge_papers(all_new, existing)
    print(f"   总: {merged['total']} | 新增: {merged['today_new']}")
    save_json(merged, DATA_PATH); gen_html(merged, config)
    s = compute_stats(merged["papers"])
    print(f"\n📊 研究方向: {s['total_topics']}个")
    for t,c in list(s["topic_counts"].items())[:5]: print(f"   {t}: {c}篇 (均引{s['topic_impact'][t]['avg_cited']})")
    print(f"✅ 完成!")
    print(f"   页面: {OUTPUT_HTML} ({os.path.getsize(OUTPUT_HTML)//1024} KB)")

if __name__=="__main__": main()
