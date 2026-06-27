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
    "船舶水动力学":   ["hydrodynamic","resistance","propeller","cavitation","hull form","seakeeping","maneuvering","cfd","computational fluid","propulsion","drag reduction","ship wave","wake","boundary layer","fluid structure","水动力","阻力","螺旋桨","兴波"],
    "自主航行与避碰": ["autonomous navigation","collision avoidance","path planning","unmanned surface","usv","mass","maritime autonomous","COLREG","motion planning","trajectory prediction","situation awareness","autonomous vessel","自主航行","避碰","无人船"],
    "水下机器人":     ["auv","rov","underwater vehicle","underwater robot","submarine","deep sea","underwater manipulation","underwater exploration","glider","水下机器人"],
    "船舶结构安全":   ["structural health","fatigue","crack detection","corrosion","hull strength","structural analysis","finite element","ship structure","fracture","damage detection","结构健康","疲劳","裂纹"],
    "海洋可再生能源": ["offshore wind","wave energy","tidal energy","renewable energy","floating wind","marine energy","wind turbine","wave power","海洋能","海上风电","波浪能"],
    "船舶能效与减排": ["energy efficiency","emission","fuel consumption","green shipping","decarboni","alternative fuel","lng","hydrogen","carbon emission","clean energy","环保","减排","能效"],
    "港口与物流":     ["port automation","terminal","logistics","container","berth","supply chain","harbor","港口","码头","集装箱"],
    "机器学习与AI":   ["deep learning","machine learning","neural network","reinforcement learning","cnn","lstm","transformer","gan","artificial intelligence","computer vision","object detection","semantic segmentation","机器学习","深度学习","神经网络"],
    "水下通信与感知": ["underwater communication","acoustic","sonar","lidar","radar","sensor fusion","underwater detection","underwater imaging","maritime surveillance","水下通信","声纳","水声"],
    "船舶设计与建造": ["ship design","naval architecture","shipbuilding","parametric design","optimization","multi-objective","船舶设计","造船","优化设计"],
}

def classify(title, abstract):
    text = (title + " " + abstract).lower()
    scores = {t: sum(1 for kw in kws if kw.lower() in text) for t, kws in TOPICS.items()}
    best = max(scores, key=scores.get)
    return (best, scores[best]) if scores[best] > 0 else ("其他", 0)

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
    max_r = cfg.get("max_results",50)
    all_p = {}
    for sort_by in ["relevance","submittedDate"]:
        terms = " OR ".join("(" + " AND ".join("ti:" + w for w in q.split()) + ")" for q in queries)
        cat_s = " OR ".join(f"cat:{c}" for c in cats)
        query = f"({terms}) AND ({cat_s})"
        url = ARXIV_API+"?search_query="+quote(query[:2000])+f"&start=0&max_results={max_r//2}&sortBy={sort_by}&sortOrder=descending"
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
                tp,ts = classify(ttl, abs_)
                all_p[pid] = dict(id=aid or pid, title=ttl, abstract=abs_[:500], authors=au[:5],
                    published=pub, year=pub[:4], source="arXiv", url=pid, pdf_url="",
                    doi=extract_doi(ttl,abs_,aid), topic=tp, topic_score=ts,
                    journal="arXiv Preprint", journal_rank="预印本", cited_by=0,
                    institutions=[], concepts=[], fetched=datetime.now().strftime("%Y-%m-%d %H:%M"))
            time.sleep(3)
        except Exception as ex: print(f"  [WARN] arXiv {sort_by}: {ex}")
    return list(all_p.values())

def extract_arxiv_id(url):
    m = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url)
    return m.group(1) if m else None

# ═══════════════════════════════════════════════════════════
#  OpenAlex（覆盖期刊论文、会议论文、图书章节等）
# ═══════════════════════════════════════════════════════════
OA_API = "https://api.openalex.org/works"

def fetch_openalex(config):
    cfg = config["sources"].get("openalex",{})
    if not cfg.get("enabled"): return []
    queries = config["search_queries"][:8]
    max_r = min(cfg.get("max_results",100), 200)
    per_q = max(20, max_r // len(queries))
    all_p = {}
    dois_seen = set()

    for q in queries:
        params = dict(
            search=q, per_page=per_q,
            sort="cited_by_count:desc",
            filter="from_publication_date:2023-01-01",
            select="id,doi,title,abstract_inverted_index,authorships,primary_location,cited_by_count,publication_date,concepts,type,keywords"
        )
        url = OA_API + "?" + "&".join(f"{k}={quote(str(v))}" for k,v in params.items())
        try:
            data = json.load(urlopen(Request(url,headers={"User-Agent":"ShipMonitor/2.0"}),timeout=20))
            for w in data.get("results",[]):
                wid = w.get("id","")
                doi = (w.get("doi") or "").replace("https://doi.org/","")
                if doi in dois_seen or wid in all_p: continue
                dois_seen.add(doi); dois_seen.add(wid)
                ttl = w.get("title","")
                if not ttl or len(ttl)<5: continue
                pub = (w.get("publication_date") or "2023")[:10]
                year = pub[:4]
                cited = w.get("cited_by_count",0)
                loc = w.get("primary_location") or {}
                src = loc.get("source") or {}
                jour = src.get("display_name","") or ""
                ws_type = w.get("type","") or ""
                ranks = config.get("journal_rankings",{})
                jrank = "一区/顶刊" if any(n in jour.lower() for n in ranks.get("一区/顶刊",[])) else \
                        "二区/重要" if any(n in jour.lower() for n in ranks.get("二区/重要",[])) else \
                        "核心期刊" if jour else ("其他" if ws_type in ("article","review") else "预印本")
                au_info = []
                insts_set = set()
                for a in w.get("authorships",[]):
                    name = (a.get("author") or {}).get("display_name","")
                    insts = [i.get("display_name","") for i in (a.get("institutions") or [])]
                    for i_ in insts[:2]:
                        if i_: insts_set.add(i_)
                    au_info.append({"name":name, "institutions":insts[:2]})
                concepts = [c.get("display_name","") for c in (w.get("concepts") or [])[:5]]
                abstract = ""
                tp,ts = classify(ttl, abstract)
                all_p[wid] = dict(id=wid, title=ttl, abstract=abstract, authors=[a["name"] for a in au_info[:5]],
                    published=pub, year=year, source="OpenAlex", url=f"https://doi.org/{doi}" if doi else wid,
                    pdf_url="", doi=doi, topic=tp, topic_score=ts, journal=jour[:40] if jour else ws_type,
                    journal_rank=jrank, cited_by=cited,
                    institutions=list(insts_set)[:3], concepts=concepts,
                    fetched=datetime.now().strftime("%Y-%m-%d %H:%M"))
            time.sleep(2)
        except Exception as ex: print(f"  [WARN] OpenAlex '{q[:20]}': {ex}")
    return list(all_p.values())

# ═══════════════════════════════════════════════════════════
#  Semantic Scholar
# ═══════════════════════════════════════════════════════════
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"

def fetch_semantic(config):
    cfg = config["sources"]["semantic_scholar"]
    if not cfg.get("enabled"): return []
    queries = config["search_queries"][:3]
    limit = min(cfg.get("limit",20), 50)
    fields = "title,authors,year,url,externalIds,abstract,venue,citationCount,publicationDate,journal"
    all_p = []; seen = set()
    for q in queries:
        url = S2_API+f"?query={quote(q)}&limit={limit//len(queries)+1}&fields={fields}&year=2023-"
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
                tp,ts = classify(ttl, abs_)
                ranks = config.get("journal_rankings",{})
                jrank = "一区/顶刊" if any(n in jour.lower() for n in ranks.get("一区/顶刊",[])) else \
                        "二区/重要" if any(n in jour.lower() for n in ranks.get("二区/重要",[])) else "核心期刊"
                all_p.append(dict(id=pid, title=ttl, abstract=abs_[:500], authors=au,
                    published=pub[:10], year=str(year), source="Semantic Scholar",
                    url=w.get("url",f"https://www.semanticscholar.org/paper/{pid}"), pdf_url="",
                    doi=doi or extract_doi(ttl,abs_,arx), topic=tp, topic_score=ts,
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

def compute_stats(papers):
    tc = Counter(); yc = Counter(); sc = Counter(); jc = Counter()
    tp = defaultdict(list)
    for p in papers:
        t = p.get("topic","其他"); tc[t] += 1; tp[t].append(p)
        y = p.get("year",""); yc[int(y)] += 1 if y.isdigit() else 0
        sc[p.get("source","")] += 1
        j = p.get("journal_rank",""); jc[j] += 1 if j else 0
    years = sorted(yc); yr = f"{min(years)}-{max(years)}" if years else "—"
    # 关键词热度: 统计每个方向论文的平均引用
    topic_impact = {}
    for t, ps in tp.items():
        c = [p.get("cited_by",0) for p in ps]
        topic_impact[t] = {"count":len(ps), "avg_cited":round(sum(c)/len(c),1) if c else 0,
                           "max_cited":max(c) if c else 0}
    # 热点论文: top 20 按引用+时效加权排序
    now = datetime.now()
    def hot_score(p):
        cited = p.get("cited_by",0)
        try: d = (now - datetime.strptime(p["published"][:10],"%Y-%m-%d")).days
        except: d = 365
        return cited * 0.6 + max(0, 365 - d) * 0.4
    hot = sorted(papers, key=lambda p: hot_score(p), reverse=True)[:20]
    return dict(topic_counts=dict(tc.most_common()),
                year_counts={str(k):yc[k] for k in years},
                source_counts=dict(sc.most_common()),
                journal_rank_counts=dict(jc.most_common()),
                topic_impact=topic_impact, topic_papers={t:tp[t] for t in tp},
                total_topics=len(tc), year_range=yr,
                hot_papers=hot,
                topic_year={t: Counter(p.get("year","") for p in ps) for t,ps in tp.items()})

# ═══════════════════════════════════════════════════════════
#  HTML生成
# ═══════════════════════════════════════════════════════════
CHART_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"

COLORS = ["#5B8FA8","#7BA9A0","#B5A88D","#C98B7A","#A88BAB",
          "#8FAB8F","#C9A88D","#7FA8C9","#B58F8F","#8FA8A8"]
RANK_COLORS = {"一区/顶刊":"#C0392B","二区/重要":"#E67E22","核心期刊":"#2980B9","预印本":"#7F8C8D","其他":"#95A5A6"}

def gen_html(data, config):
    papers = data.get("papers",[])
    stats = compute_stats(papers)
    updated = data.get("updated","")
    total = data.get("total",0)

    tl = list(stats["topic_counts"].keys())
    tcols = {t:COLORS[i%len(COLORS)] for i,t in enumerate(tl)}

    # ── 统计卡片 ──
    jrc = stats["journal_rank_counts"]
    top_j = sum(v for k,v in jrc.items() if k in ("一区/顶刊","二区/重要"))
    cards = f"""
    <div class="stats-row">
        <div class="sc"><span class="n">{total}</span><span class="l">论文总数</span></div>
        <div class="sc"><span class="n">{stats['total_topics']}</span><span class="l">研究方向</span></div>
        <div class="sc"><span class="n">{stats['year_range']}</span><span class="l">覆盖年份</span></div>
        <div class="sc"><span class="n">{top_j}</span><span class="l">顶刊/重要期刊</span></div>
        <div class="sc"><span class="n">{len(stats['source_counts'])}</span><span class="l">数据源</span></div>
    </div>"""

    # ── 数据（给Chart.js）──
    topic_impact = stats["topic_impact"]
    impact_data = {t: topic_impact[t] for t in tl}
    hot_papers = stats["hot_papers"]
    topic_labels_j = json.dumps(tl, ensure_ascii=False)
    topic_data_j = json.dumps([stats["topic_counts"][t] for t in tl], ensure_ascii=False)
    topic_avg_j = json.dumps([topic_impact[t]["avg_cited"] for t in tl], ensure_ascii=False)
    topic_colors_j = json.dumps([tcols[t] for t in tl], ensure_ascii=False)
    year_labels = sorted(stats["year_counts"])
    year_data = [stats["year_counts"][y] for y in year_labels]
    cum = [sum(year_data[:i+1]) for i in range(len(year_data))]
    yl_j = json.dumps(year_labels)
    yd_j = json.dumps(year_data)
    cum_j = json.dumps(cum)

    # ── 热点论文 ──
    hot_html = ""
    for i,p in enumerate(hot_papers[:10]):
        c = p.get("cited_by",0)
        jrnk = p.get("journal_rank","")
        rcol = RANK_COLORS.get(jrnk,"#95A5A6")
        doi = p.get("doi","")
        doi_h = f'<a href="https://doi.org/{doi}" class="doi" target="_blank">{doi[:40]}</a>' if doi else ""
        hot_html += f"""
        <div class="hp">
            <span class="hp-num">{i+1}</span>
            <div class="hp-body">
                <div class="hp-title"><a href="{p.get("url","#")}" target="_blank">{p["title"][:90]}</a></div>
                <div class="hp-meta">
                    <span>{p.get("published","")[:10]}</span>
                    <span class="cite">📊 {c} 引用</span>
                    {f'<span class="rank" style="color:{rcol}">{jrnk}</span>' if jrnk else ''}
                    {doi_h}
                </div>
            </div>
        </div>"""

    # ── 各方向 ──
    topics_html = ""
    for i,t in enumerate(tl):
        ps = sorted(stats["topic_papers"].get(t,[]), key=lambda x: x.get("cited_by",0), reverse=True)
        c = stats["topic_counts"][t]
        imp = topic_impact[t]
        col = tcols[t]
        items = ""
        for p in ps[:8]:
            ci = p.get("cited_by",0)
            jour = p.get("journal","")
            jrnk = p.get("journal_rank","")
            doi = p.get("doi","")
            au = ", ".join(p.get("authors",[])[:2])
            doi_h = f'<a href="https://doi.org/{doi}" class="doi">📎 {doi[:30]}</a>' if doi else ""
            items += f"""
            <div class="pi">
                <div class="pi-title"><a href="{p.get("url","#")}" target="_blank">{p["title"][:90]}</a></div>
                <div class="pi-meta">
                    <span>{p.get("published","")[:10]}</span>
                    {f'<span class="au">{au[:50]}…</span>' if au else ''}
                    {f'<span class="ci">📊 {ci}</span>' if ci else ''}
                    {doi_h}
                </div>
            </div>"""
        more = c - 8
        topics_html += f"""
        <div class="ts">
            <div class="th" onclick="tt(this)">
                <span class="dot" style="background:{col}"></span>
                <span class="tn">{t}</span>
                <span class="tc">{c}篇</span>
                <span class="ti">📊 均引{imp["avg_cited"]} 最高{imp["max_cited"]}</span>
                <span class="tic">▸</span>
            </div>
            <div class="tb" style="display:none">
                {items}
                {f'<p class="m">…还有{more}篇</p>' if more>0 else ''}
            </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>船舶研究动态 · 统计看板</title>
<link rel="stylesheet" href="style.css">
<script src="{CHART_CDN}"></script>
</head>
<body>
<header>
    <h1>🚢 船舶研究动态监测</h1>
    <p class="sub">Ship & Maritime Research · 多源数据分析 · 每3天自动更新</p>
    <p class="meta">🕐 {updated} | 数据来源: arXiv + OpenAlex + Semantic Scholar</p>
</header>
<main>
    {cards}

    <div class="charts-row">
        <div class="cc">
            <h2>📊 研究方向分布</h2>
            <div class="cw"><canvas id="c1"></canvas></div>
        </div>
        <div class="cc">
            <h2>📈 发文趋势</h2>
            <div class="cw"><canvas id="c2"></canvas></div>
        </div>
        <div class="cc">
            <h2>🏆 期刊等级分布</h2>
            <div class="cw"><canvas id="c3"></canvas></div>
        </div>
    </div>

    <section class="hot">
        <h2>🔥 热点论文 · 综合加权排名</h2>
        <p class="hint">引用数 + 时效性加权排序</p>
        {hot_html}
    </section>

    <section class="detail">
        <h2>📋 研究方向详情</h2>
        <div class="tf"><input type="text" id="ts" placeholder="🔍 搜研究方向..." oninput="ft()"></div>
        {topics_html}
    </section>
</main>
<footer>
    <p>采集: arXiv API + OpenAlex API + Semantic Scholar API | 每3天 08:00 自动更新</p>
    <p><a href="https://github.com/Jison-hue/ship-research-monitor" target="_blank">GitHub</a></p>
</footer>
<script>
const tx = {topic_labels_j}, td = {topic_data_j}, ta = {topic_avg_j}, tc = {topic_colors_j};
new Chart(document.getElementById('c1'), {{
    type:'bar', data:{{labels:tx, datasets:[{{label:'论文数',data:td,backgroundColor:tc,borderRadius:3}}]}},
    options:{{indexAxis:'y', responsive:true, maintainAspectRatio:false,
        plugins:{{legend:{{display:false}}}},
        scales:{{x:{{beginAtZero:true,grid:{{color:'rgba(0,0,0,0.04)'}}}},y:{{grid:{{display:false}}}}}} }}
}});
new Chart(document.getElementById('c2'), {{
    type:'bar', data:{{
        labels:{yl_j}, datasets:[
            {{label:'新增',data:{yd_j},backgroundColor:'rgba(91,143,168,0.6)',order:2}},
            {{label:'累计',data:{cum_j},type:'line',borderColor:'#C98B7A',fill:true,tension:0.3,pointRadius:3,order:1}}
        ]
    }},
    options:{{responsive:true, maintainAspectRatio:false, plugins:{{legend:{{position:'top',labels:{{font:{{size:12}}}}}}}},
        scales:{{x:{{grid:{{display:false}}}},y:{{beginAtZero:true,grid:{{color:'rgba(0,0,0,0.04)'}}}}}} }}
}});
new Chart(document.getElementById('c3'), {{
    type:'doughnut', data:{{
        labels:{json.dumps(list(stats['journal_rank_counts'].keys()), ensure_ascii=False)},
        datasets:[{{data:{json.dumps(list(stats['journal_rank_counts'].values()), ensure_ascii=False)},
            backgroundColor:['#C0392B','#E67E22','#2980B9','#7F8C8D','#95A5A6']}}]
    }},
    options:{{responsive:true, maintainAspectRatio:false, plugins:{{legend:{{position:'bottom',labels:{{font:{{size:11}}}}}}}} }}
}});
function tt(el){{var b=el.nextElementSibling,i=el.querySelector('.tic');var o=b.style.display=='block';b.style.display=o?'none':'block';i.textContent=o?'▸':'▾';}}
function ft(){{var q=document.getElementById('ts').value.toLowerCase();document.querySelectorAll('.ts').forEach(function(s){{s.style.display=s.querySelector('.tn').textContent.toLowerCase().includes(q)?'':'none';}});}}
</script>
</body>
</html>"""
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f: f.write(html)

# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════
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
