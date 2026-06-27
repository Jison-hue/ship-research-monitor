#!/usr/bin/env python3
"""
Ship Research Monitor - 船舶研究动态监测
数据采集 + 统计分析 + 趋势可视化
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from xml.etree import ElementTree
from urllib.request import urlopen, Request
from urllib.parse import quote
from collections import defaultdict, Counter

# ─── 路径 ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
OUTPUT_JSON = os.path.join(DATA_DIR, "papers.json")
OUTPUT_HTML = os.path.join(DOCS_DIR, "index.html")

# ─── 研究方向分类 ──────────────────────────────────────
TOPICS = {
    "船舶水动力学": [
        "hydrodynamic", "resistance", "propeller", "cavitation", "hull form",
        "seakeeping", "maneuvering", "cfd", "computational fluid", "propulsion",
        "drag reduction", "ship wave", "wake", "boundary layer", "fluid structure",
        "水动力", "阻力", "螺旋桨", "兴波"
    ],
    "自主航行与避碰": [
        "autonomous navigation", "collision avoidance", "path planning",
        "unmanned surface", "usv", "mass", "maritime autonomous",
        "COLREG", "motion planning", "trajectory prediction",
        "situation awareness", "autonomous vessel",
        "自主航行", "避碰", "无人船"
    ],
    "水下机器人": [
        "auv", "rov", "underwater vehicle", "underwater robot",
        "submarine", "deep sea", "underwater manipulation",
        "underwater exploration", "glider",
        "水下机器人", "AUV", "ROV"
    ],
    "船舶结构安全": [
        "structural health", "fatigue", "crack detection", "corrosion",
        "hull strength", "structural analysis", "finite element",
        "ship structure", "fracture", "damage detection",
        "结构健康", "疲劳", "裂纹"
    ],
    "海洋可再生能源": [
        "offshore wind", "wave energy", "tidal energy", "renewable energy",
        "floating wind", "marine energy", "wind turbine", "wave power",
        "海洋能", "海上风电", "波浪能"
    ],
    "船舶能效与减排": [
        "energy efficiency", "emission", "fuel consumption", "green shipping",
        "decarboni", "alternative fuel", "lng", "hydrogen",
        "carbon emission", "clean energy", "环保", "减排", "能效"
    ],
    "港口与物流": [
        "port automation", "terminal", "logistics", "container",
        "berth", "supply chain", "harbor",
        "港口", "码头", "集装箱"
    ],
    "机器学习与AI": [
        "deep learning", "machine learning", "neural network",
        "reinforcement learning", "cnn", "lstm", "transformer",
        "gan", "artificial intelligence", "computer vision",
        "object detection", "semantic segmentation",
        "机器学习", "深度学习", "神经网络"
    ],
    "水下通信与感知": [
        "underwater communication", "acoustic", "sonar", "lidar",
        "radar", "sensor fusion", "underwater detection",
        "underwater imaging", "maritime surveillance",
        "水下通信", "声纳", "水声"
    ],
    "船舶设计与建造": [
        "ship design", "naval architecture", "shipbuilding",
        "parametric design", "optimization", "multi-objective",
        "船舶设计", "造船", "优化设计"
    ],
}

# ─── 工具函数 ───────────────────────────────────────────
def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_existing(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"papers": [], "updated": None, "history": []}

def extract_arxiv_id(url):
    m = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url)
    return m.group(1) if m else None

def extract_doi(title, abstract, arxiv_id, source_url):
    """提取DOI"""
    full = (title + " " + abstract)
    # 先找显式DOI
    m = re.search(r'10\.\d{4,}/[\w\.\-/]+', full)
    if m:
        return m.group(0).rstrip('.')
    # arXiv paper 默认DOI
    if arxiv_id:
        return f"10.48550/arXiv.{arxiv_id}"
    return ""


def classify_paper(title, abstract):
    """给论文打研究方向标签"""
    text = (title + " " + abstract).lower()
    scores = {}
    for topic, keywords in TOPICS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[topic] = score
    if not scores:
        return "其他", 0
    best = max(scores, key=scores.get)
    return best, scores[best]


# ═══════════════════════════════════════════════════════════
#  arXiv API
# ═══════════════════════════════════════════════════════════

ARXIV_API = "http://export.arxiv.org/api/query"

def build_arxiv_query(queries, categories):
    terms = []
    for q in queries:
        words = q.strip().split()
        term = ' AND '.join(
            [f'ti:"{w}"' if len(w) > 2 else f'ti:{w}' for w in words]
        )
        terms.append(f'({term})')
    cat_filter = ' OR '.join([f'cat:{c}' for c in categories])
    return f'({" OR ".join(terms)}) AND ({cat_filter})'


def fetch_arxiv(config):
    cfg = config["sources"]["arxiv"]
    if not cfg.get("enabled"):
        return []
    
    max_results = cfg.get("max_results", 50)
    queries = config["search_queries"]
    categories = cfg.get("categories", [])
    all_papers = {}
    
    for sort_by in ["relevance", "submittedDate"]:
        query = build_arxiv_query(queries, categories)
        params = {
            "search_query": query[:2000],
            "start": 0,
            "max_results": max_results // 2,
            "sortBy": sort_by,
            "sortOrder": "descending",
        }
        url = ARXIV_API + "?" + "&".join(
            [f"{k}={quote(str(v))}" for k, v in params.items()]
        )
        
        try:
            req = Request(url, headers={"User-Agent": "ShipMonitor/1.0"})
            resp = urlopen(req, timeout=30)
            root = ElementTree.fromstring(resp.read().decode("utf-8"))
            ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
            
            for entry in root.findall("atom:entry", ns):
                paper_id = entry.find("atom:id", ns).text.strip()
                if paper_id in all_papers:
                    continue
                
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
                published = entry.find("atom:published", ns).text[:10]
                
                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.find("atom:name", ns)
                    if name is not None:
                        authors.append(name.text)
                
                links = entry.findall("atom:link", ns)
                pdf_url = ""
                abs_url = paper_id
                for link in links:
                    if link.attrib.get("title") == "pdf":
                        pdf_url = link.attrib["href"]
                    elif link.attrib.get("rel") == "alternate":
                        abs_url = link.attrib["href"]
                
                arxiv_id = extract_arxiv_id(paper_id) or ""
                topic, topic_score = classify_paper(title, summary)
                
                all_papers[paper_id] = {
                    "id": arxiv_id or paper_id,
                    "title": title,
                    "abstract": summary[:500],
                    "authors": authors[:5],
                    "published": published,
                    "year": published[:4],
                    "source": "arXiv",
                    "url": abs_url,
                    "pdf_url": pdf_url,
                    "doi": extract_doi(title, summary, arxiv_id, abs_url),
                    "topic": topic,
                    "topic_score": topic_score,
                    "fetched": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            
            time.sleep(3)
        except Exception as e:
            print(f"  [WARN] arXiv {sort_by} 失败: {e}")
    
    return list(all_papers.values())


# ═══════════════════════════════════════════════════════════
#  Semantic Scholar API
# ═══════════════════════════════════════════════════════════

S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"

def fetch_semantic_scholar(config):
    cfg = config["sources"]["semantic_scholar"]
    if not cfg.get("enabled"):
        return []
    
    queries = config["search_queries"][:3]
    limit = min(cfg.get("limit", 20), 50)
    fields = "title,authors,year,url,externalIds,abstract,venue,publicationDate"
    
    all_papers = []
    seen_ids = set()
    
    for query in queries:
        params = {
            "query": query,
            "limit": limit // len(queries) + 1,
            "fields": fields,
            "year": f"{datetime.now().year - 2}-",
        }
        url = S2_API + "?" + "&".join(
            [f"{k}={quote(str(v))}" for k, v in params.items()]
        )
        
        try:
            req = Request(url, headers={"User-Agent": "ShipMonitor/1.0"})
            resp = urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            
            for paper in data.get("data", []):
                pid = paper.get("paperId", "")
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                
                title = paper.get("title", "")
                if not title or len(title) < 5:
                    continue
                abstract = paper.get("abstract", "")
                if not abstract:
                    continue
                
                authors = [a.get("name", "") for a in paper.get("authors", [])[:5]]
                year = paper.get("year", "")
                pub_date = paper.get("publicationDate", "")
                venue = paper.get("venue", "")
                ext_ids = paper.get("externalIds", {})
                arxiv_id = ext_ids.get("ArXiv", "")
                doi = ext_ids.get("DOI", "")
                
                topic, topic_score = classify_paper(title, abstract)
                
                all_papers.append({
                    "id": pid,
                    "title": title,
                    "abstract": abstract[:500],
                    "authors": authors,
                    "published": pub_date[:10] if pub_date else str(year),
                    "year": str(year),
                    "source": "Semantic Scholar",
                    "url": paper.get("url", f"https://www.semanticscholar.org/paper/{pid}"),
                    "pdf_url": "",
                    "doi": doi or extract_doi(title, abstract, arxiv_id, ""),
                    "topic": topic,
                    "topic_score": topic_score,
                    "fetched": datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
            
            time.sleep(3)
        except Exception as e:
            print(f"  [WARN] SS '{query[:20]}' 失败: {e}")
    
    return all_papers


# ═══════════════════════════════════════════════════════════
#  数据合并与统计分析
# ═══════════════════════════════════════════════════════════

def merge_papers(new_papers, existing_data):
    existing = existing_data.get("papers", [])
    history = existing_data.get("history", [])
    
    existing_ids = set()
    for p in existing:
        existing_ids.add(p["id"])
        if p.get("doi"):
            existing_ids.add(p["doi"])
    
    deduped = []
    for p in new_papers:
        if p["id"] in existing_ids or p.get("doi", "") in existing_ids:
            continue
        deduped.append(p)
    
    merged = deduped + existing
    
    today = datetime.now().strftime("%Y-%m-%d")
    if deduped:
        history.append({"date": today, "new_count": len(deduped), "total": len(merged)})
        history = history[-90:]
    
    return {
        "papers": merged,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today_new": len(deduped),
        "total": len(merged),
        "history": history,
    }


def compute_statistics(papers):
    """计算统计数据"""
    # 按研究方向统计
    topic_counts = Counter()
    topic_papers = defaultdict(list)
    for p in papers:
        topic = p.get("topic", "其他")
        topic_counts[topic] += 1
        topic_papers[topic].append(p)
    
    # 按年份统计
    year_counts = Counter()
    for p in papers:
        y = p.get("year", "未知")
        if y and y.isdigit():
            year_counts[int(y)] += 1
    
    # 按年份+研究方向统计
    topic_year = defaultdict(lambda: Counter())
    for p in papers:
        t = p.get("topic", "其他")
        y = p.get("year", "未知")
        if y and y.isdigit():
            topic_year[t][int(y)] += 1
    
    # 汇总年份范围
    years = sorted(y for y in year_counts if y != "未知")
    year_range = f"{min(years)}-{max(years)}" if years else "—"
    
    # 按来源统计
    source_counts = Counter(p.get("source", "其他") for p in papers)
    
    return {
        "topic_counts": dict(topic_counts.most_common()),
        "year_counts": {str(k): v for k, v in sorted(year_counts.items())},
        "topic_year": {t: {str(k): v for k, v in sorted(d.items())} for t, d in topic_year.items()},
        "source_counts": dict(source_counts.most_common()),
        "total_topics": len(topic_counts),
        "year_range": year_range,
        "topic_papers": {t: sorted(ps, key=lambda x: x.get("published", ""), reverse=True)[:20]
                         for t, ps in topic_papers.items()},
    }


# ═══════════════════════════════════════════════════════════
#  HTML 生成（简约统计看板）
# ═══════════════════════════════════════════════════════════

CHART_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"

def generate_html(data, config):
    papers = data.get("papers", [])
    stats = compute_statistics(papers)
    updated = data.get("updated", "")
    total = data.get("total", 0)
    
    # ── 颜色方案（莫兰迪色系）──
    colors = [
        "#5B8FA8", "#7BA9A0", "#B5A88D", "#C98B7A", "#A88BAB",
        "#8FAB8F", "#C9A88D", "#7FA8C9", "#B58F8F", "#8FA8A8"
    ]
    topic_list = list(stats["topic_counts"].keys())
    topic_colors = {t: colors[i % len(colors)] for i, t in enumerate(topic_list)}
    
    # ── 统计卡片 ──
    stats_cards = f"""
    <div class="stats-row">
        <div class="stat-card"><span class="num">{total}</span><span class="label">论文总数</span></div>
        <div class="stat-card"><span class="num">{stats['total_topics']}</span><span class="label">研究方向</span></div>
        <div class="stat-card"><span class="num">{stats['year_range']}</span><span class="label">覆盖年份</span></div>
        <div class="stat-card"><span class="num">{len(stats['source_counts'])}</span><span class="label">数据源</span></div>
    </div>
    """
    
    # ── Chart.js 数据 ──
    chart_data = json.dumps({
        "topicLabels": topic_list,
        "topicData": [stats["topic_counts"].get(t, 0) for t in topic_list],
        "topicColors": [topic_colors[t] for t in topic_list],
        "yearLabels": list(stats["year_counts"].keys()),
        "yearData": list(stats["year_counts"].values()),
    }, ensure_ascii=False)
    
    # ── 按年份累加 ──
    year_keys = sorted(stats["year_counts"].keys())
    cumulative = 0
    cum_data_js = []
    for y in year_keys:
        cumulative += stats["year_counts"][y]
        cum_data_js.append(cumulative)
    chart_data_js = json.dumps({
        "yearLabels": year_keys,
        "newData": [stats["year_counts"][y] for y in year_keys],
        "cumData": cum_data_js,
    }, ensure_ascii=False)
    
    # ── 各方向论文详情（带DOI）──
    topics_html = ""
    for i, topic in enumerate(topic_list):
        color = topic_colors[topic]
        count = stats["topic_counts"][topic]
        paper_list = stats["topic_papers"].get(topic, [])[:10]
        
        papers_html = ""
        for p in paper_list:
            doi = p.get("doi", "")
            doi_html = f'<a href="https://doi.org/{doi}" target="_blank" class="doi">{doi[:45]}</a>' if doi else ""
            authors = ", ".join(p.get("authors", [])[:3])
            
            papers_html += f"""
            <div class="paper-item">
                <div class="paper-title">
                    <a href="{p.get("url", "#")}" target="_blank">{p["title"][:100]}</a>
                </div>
                <div class="paper-meta">
                    <span class="year">📅 {p.get("published", "")[:10]}</span>
                    {f'<span class="authors">👤 {authors[:60]}</span>' if authors else ''}
                    {doi_html}
                </div>
            </div>
            """
        
        if not papers_html:
            papers_html = '<p class="empty">暂无论文详情</p>'
        
        more = stats["topic_counts"].get(topic, 0) - len(paper_list)
        more_html = f'<p class="more">…… 还有 {more} 篇</p>' if more > 0 else ""
        
        topics_html += f"""
        <div class="topic-section">
            <div class="topic-header" onclick="toggleTopic(this)">
                <span class="topic-dot" style="background:{color}"></span>
                <span class="topic-name">{topic}</span>
                <span class="topic-count">{count} 篇</span>
                <span class="toggle-icon">▸</span>
            </div>
            <div class="topic-body" id="topic-{i}">
                {papers_html}
                {more_html}
            </div>
        </div>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>船舶研究动态 · 统计看板</title>
    <link rel="stylesheet" href="style.css">
    <script src="{CHART_CDN}"></script>
</head>
<body>
    <header>
        <h1>🚢 船舶研究动态</h1>
        <p class="sub">Ship & Maritime Research · 统计分析</p>
        <p class="meta">🕐 更新于 {updated} | 每3天自动采集</p>
    </header>

    <main>
        {stats_cards}

        <section class="charts-section">
            <div class="chart-container">
                <h2>📊 研究方向分布</h2>
                <div class="chart-wrap"><canvas id="topicChart"></canvas></div>
            </div>
            <div class="chart-container">
                <h2>📈 发文趋势</h2>
                <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
            </div>
        </section>

        <section class="detail-section">
            <h2>📋 研究方向详情</h2>
            <div class="topic-filter">
                <input type="text" id="topicSearch" placeholder="🔍 搜索研究方向..." oninput="filterTopics()">
            </div>
            <div id="topicList">{topics_html}</div>
        </section>
    </main>

    <footer>
        <p>采集来源: arXiv · Semantic Scholar | 每3天 08:00 自动更新</p>
        <p><a href="https://github.com/Jison-hue/ship-research-monitor" target="_blank">GitHub</a></p>
    </footer>

    <script>
    const trendData = {chart_data_js};
    const topicLabels = {json.dumps(topic_list, ensure_ascii=False)};
    const topicData = {json.dumps([stats['topic_counts'].get(t, 0) for t in topic_list], ensure_ascii=False)};
    const topicColors = {json.dumps([topic_colors[t] for t in topic_list], ensure_ascii=False)};

    // 趋势图: 柱状 + 折线
    new Chart(document.getElementById('trendChart'), {{
        type: 'bar',
        data: {{
            labels: trendData.yearLabels,
            datasets: [{{
                label: '新增论文',
                data: trendData.newData,
                backgroundColor: 'rgba(91, 143, 168, 0.6)',
                borderColor: 'rgba(91, 143, 168, 1)',
                borderWidth: 1,
                order: 2
            }}, {{
                label: '累计',
                data: trendData.cumData,
                type: 'line',
                borderColor: '#C98B7A',
                backgroundColor: 'rgba(201, 139, 122, 0.08)',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointBackgroundColor: '#C98B7A',
                order: 1
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top', labels: {{ font: {{ size: 12 }} }} }} }},
            scales: {{
                x: {{ grid: {{ display: false }} }},
                y: {{ beginAtZero: true, grid: {{ color: 'rgba(0,0,0,0.05)' }} }}
            }}
        }}
    }});

    // 研究方向分布: 水平柱状图
    new Chart(document.getElementById('topicChart'), {{
        type: 'bar',
        data: {{
            labels: topicLabels,
            datasets: [{{
                label: '论文数量',
                data: topicData,
                backgroundColor: topicColors,
                borderRadius: 3,
            }}]
        }},
        options: {{
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{
                x: {{ beginAtZero: true, grid: {{ color: 'rgba(0,0,0,0.05)' }} }},
                y: {{ grid: {{ display: false }} }}
            }}
        }}
    }});

    function toggleTopic(el) {{
        const body = el.nextElementSibling;
        const icon = el.querySelector('.toggle-icon');
        const isOpen = body.style.display === 'block';
        body.style.display = isOpen ? 'none' : 'block';
        icon.textContent = isOpen ? '▸' : '▾';
    }}

    function filterTopics() {{
        const q = document.getElementById('topicSearch').value.toLowerCase();
        document.querySelectorAll('.topic-section').forEach(s => {{
            const name = s.querySelector('.topic-name').textContent.toLowerCase();
            s.style.display = name.includes(q) ? '' : 'none';
        }});
    }}
    </script>
</body>
</html>"""
    
    # 修正：删除重复的饼图初始化，只保留正确的 chartData
    html = html.replace(
        f'const chartData = {chart_data_js};',
        f'const chartData = {chart_data_js};'
    )
    
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    
    return html


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 50)
    print(f"🚢 船舶研究动态监测 · 数据采集")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    config = load_config()
    existing = load_existing(OUTPUT_JSON)
    all_new = []
    
    print("\n📄 正在从 arXiv 获取论文...")
    try:
        papers = fetch_arxiv(config)
        print(f"   ✅ {len(papers)} 篇")
        all_new.extend(papers)
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    print("\n📘 正在从 Semantic Scholar 获取论文...")
    try:
        papers = fetch_semantic_scholar(config)
        print(f"   ✅ {len(papers)} 篇")
        all_new.extend(papers)
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    print(f"\n🔄 合并去重...")
    merged = merge_papers(all_new, existing)
    print(f"   📊 总论文: {merged['total']} | 今日新增: {merged['today_new']}")
    
    save_json(merged, OUTPUT_JSON)
    
    print(f"\n📊 计算统计 & 生成看板...")
    generate_html(merged, config)
    
    stats = compute_statistics(merged["papers"])
    print(f"   📈 研究方向: {stats['total_topics']} 个")
    for t, c in list(stats["topic_counts"].items())[:5]:
        print(f"      {t}: {c} 篇")
    
    print(f"\n✅ 完成! 页面: docs/index.html")
    print("=" * 50)


if __name__ == "__main__":
    main()
