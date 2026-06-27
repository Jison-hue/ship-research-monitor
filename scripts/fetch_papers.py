#!/usr/bin/env python3
"""
Ship Research Daily Monitor - 船舶研究动态每日采集
自动从 arXiv 和 Semantic Scholar 抓取船舶/海洋工程最新论文
"""

import json
import time
import os
import re
import sys
from datetime import datetime, timedelta
from xml.etree import ElementTree
from urllib.request import urlopen, Request
from urllib.parse import quote

# ─── 路径 ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
OUTPUT_JSON = os.path.join(DATA_DIR, "papers.json")
OUTPUT_HTML = os.path.join(DOCS_DIR, "index.html")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_existing(path):
    """加载已有的历史数据，保持去重"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"papers": [], "updated": None, "history": []}


def extract_arxiv_id(url):
    """从arXiv URL提取论文ID"""
    match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url)
    return match.group(1) if match else None


# ═══════════════════════════════════════════════════════════
#  arXiv API
# ═══════════════════════════════════════════════════════════

ARXIV_API = "http://export.arxiv.org/api/query"


def build_arxiv_query(queries, categories, max_results=50):
    """构建arXiv查询字符串"""
    terms = []
    for q in queries:
        # 拆分成短语和单词
        words = q.strip().split()
        term = ' AND '.join(
            [f'ti:"{w}"' if len(w) > 2 else f'ti:{w}' for w in words]
        )
        terms.append(f'({term})')
    
    cat_filter = ' OR '.join([f'cat:{c}' for c in categories])
    query_parts = ' OR '.join(terms)
    
    # arXiv查询限制：先按相关度排序，取最新的一批
    return f'{query_parts} AND ({cat_filter})'


def fetch_arxiv(config):
    """从arXiv获取论文"""
    cfg = config["sources"]["arxiv"]
    if not cfg.get("enabled"):
        return []
    
    max_results = cfg.get("max_results", 50)
    queries = config["search_queries"]
    categories = cfg.get("categories", [])
    
    # 分两批取：相关度排序 + 最新排序
    all_papers = {}
    
    for sort_by in ["relevance", "submittedDate"]:
        query = build_arxiv_query(queries, categories, max_results)
        params = {
            "search_query": query[:2000],  # arXiv URL长度限制
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
            xml_data = resp.read().decode("utf-8")
            
            root = ElementTree.fromstring(xml_data)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }
            
            for entry in root.findall("atom:entry", ns):
                paper_id = entry.find("atom:id", ns).text.strip()
                if paper_id in all_papers:
                    continue
                
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
                published = entry.find("atom:published", ns).text[:10]
                updated = entry.find("atom:updated", ns).text[:10]
                
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
                
                categories_list = []
                for cat in entry.findall("atom:category", ns):
                    categories_list.append(cat.attrib.get("term", ""))
                
                all_papers[paper_id] = {
                    "id": extract_arxiv_id(paper_id) or paper_id,
                    "title": title,
                    "abstract": summary[:500],
                    "authors": authors[:5],
                    "published": published,
                    "source": "arXiv",
                    "url": abs_url,
                    "pdf_url": pdf_url,
                    "categories": categories_list[:5],
                    "fetched": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            
            time.sleep(3)  # arXiv API限流
            
        except Exception as e:
            print(f"  [WARN] arXiv {sort_by} 查询失败: {e}")
            continue
    
    return list(all_papers.values())


# ═══════════════════════════════════════════════════════════
#  Semantic Scholar API
# ═══════════════════════════════════════════════════════════

S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"


def fetch_semantic_scholar(config):
    """从Semantic Scholar获取论文"""
    cfg = config["sources"]["semantic_scholar"]
    if not cfg.get("enabled"):
        return []
    
    queries = config["search_queries"]
    limit = min(cfg.get("limit", 30), 100)
    fields = "title,authors,year,url,externalIds,abstract,venue,publicationDate"
    fields_of_study = cfg.get("fields_of_study", [])
    
    all_papers = []
    seen_ids = set()
    
    # 只取前3个查询，避免超API限额
    for query in queries[:3]:
        params = {
            "query": query,
            "limit": limit // len(queries[:5]) + 1,
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
                
                ext_ids = paper.get("externalIds", {})
                arxiv_id = ext_ids.get("ArXiv", "")
                
                title = paper.get("title", "")
                if not title or len(title) < 5:
                    continue
                
                abstract = paper.get("abstract", "")
                if not abstract:
                    continue
                
                authors = []
                for a in paper.get("authors", [])[:5]:
                    authors.append(a.get("name", ""))
                
                year = paper.get("year", "")
                pub_date = paper.get("publicationDate", "")
                venue = paper.get("venue", "")
                
                all_papers.append({
                    "id": pid,
                    "title": title,
                    "abstract": abstract[:500],
                    "authors": authors,
                    "published": pub_date[:10] if pub_date else str(year),
                    "source": "Semantic Scholar",
                    "url": paper.get("url", f"https://www.semanticscholar.org/paper/{pid}"),
                    "pdf_url": "",
                    "categories": [venue] if venue else [],
                    "arxiv_id": arxiv_id,
                    "fetched": datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
            
            time.sleep(3)  # 限流
            
        except Exception as e:
            print(f"  [WARN] Semantic Scholar '{query[:30]}' 查询失败: {e}")
            continue
    
    return all_papers


# ═══════════════════════════════════════════════════════════
#  数据合并与去重
# ═══════════════════════════════════════════════════════════

def merge_papers(new_papers, existing_data):
    """合并新旧数据，去重"""
    existing = existing_data.get("papers", [])
    history = existing_data.get("history", [])
    last_updated = existing_data.get("updated")
    
    # 已有论文的ID集合
    existing_ids = set()
    existing_arxiv = set()
    for p in existing:
        existing_ids.add(p["id"])
        if p["source"] == "arXiv":
            existing_arxiv.add(p["id"])
        if p.get("arxiv_id"):
            existing_arxiv.add(p["arxiv_id"])
    
    # 去重
    deduped = []
    for p in new_papers:
        pid = p["id"]
        aid = p.get("arxiv_id", "")
        if pid in existing_ids or aid in existing_arxiv:
            continue
        if pid in [x["id"] for x in deduped]:
            continue
        deduped.append(p)
    
    # 合并：新论文在前
    merged = deduped + existing
    
    # 当日新增计入历史（简化：只记数量）
    today = datetime.now().strftime("%Y-%m-%d")
    if deduped:
        history.append({
            "date": today,
            "new_count": len(deduped),
            "total": len(merged),
        })
        history = history[-90:]  # 保留90天
    
    return {
        "papers": merged,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_updated": last_updated,
        "today_new": len(deduped),
        "total": len(merged),
        "history": history,
    }


# ═══════════════════════════════════════════════════════════
#  关键词打分（提升相关性排序）
# ═══════════════════════════════════════════════════════════

# 船海核心关键词 - 命中越多越靠前
CORE_KW = [
    "ship", "vessel", "maritime", "marine", "ocean", "offshore", "underwater",
    "submarine", "naval", "seaworth", "seakeeping", "maneuvering",
    "propeller", "cavitation", "hydrodynamic", "resistance", "hull",
    "autonomous surface", "unmanned surface", "ROV", "AUV", "USV", "ASV",
    "collision avoidance", "path planning", "trajectory prediction",
    "船舶", "海洋工程", "水动力", "螺旋桨", "自主航行"
]


def score_paper(paper):
    """给论文打分，越高越相关"""
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()
    text = title + " " + abstract
    
    score = 0
    for kw in CORE_KW:
        if kw.lower() in text:
            score += 1
    
    # 标题命中权重更高
    for kw in CORE_KW:
        if kw.lower() in title:
            score += 2
    
    # 时效加分（越新越好）
    pub = paper.get("published", "")
    if pub:
        try:
            dt = datetime.strptime(pub[:10], "%Y-%m-%d") if "-" in pub else None
            if dt:
                days_ago = (datetime.now() - dt).days
                if days_ago <= 7:
                    score += 3
                elif days_ago <= 30:
                    score += 2
                elif days_ago <= 90:
                    score += 1
        except:
            pass
    
    # 优先arXiv（预印本更新更快）
    if paper.get("source") == "arXiv":
        score += 1
    
    return score


# ═══════════════════════════════════════════════════════════
#  HTML生成
# ═══════════════════════════════════════════════════════════

def generate_html(data, config):
    """从JSON数据生成静态HTML"""
    papers = data.get("papers", [])
    today_new = data.get("today_new", 0)
    total = data.get("total", 0)
    updated = data.get("updated", "")
    history = data.get("history", [])
    
    # 排序：分数降序
    scored = [(score_paper(p), p) for p in papers]
    scored.sort(key=lambda x: -x[0])
    papers = [p for _, p in scored]
    
    # 按时间分组
    today = datetime.now().strftime("%Y-%m-%d")
    this_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    today_papers = []
    week_papers = []
    older_papers = []
    
    for p in papers:
        pub = p.get("published", "")[:10]
        if pub == today:
            today_papers.append(p)
        elif pub >= this_week:
            week_papers.append(p)
        else:
            older_papers.append(p)
    
    # 统计
    stats_html = f"""
    <div class="stats">
        <div class="stat-card">
            <span class="stat-num">{total}</span>
            <span class="stat-label">论文总数</span>
        </div>
        <div class="stat-card">
            <span class="stat-num">{today_new}</span>
            <span class="stat-label">今日新增</span>
        </div>
        <div class="stat-card">
            <span class="stat-num">{len(today_papers)}</span>
            <span class="stat-label">今日发表</span>
        </div>
        <div class="stat-card">
            <span class="stat-num">{len(week_papers)}</span>
            <span class="stat-label">近7天</span>
        </div>
    </div>
    """
    
    # 历史趋势（简化）
    history_html = ""
    if history:
        bars = ""
        max_count = max(h["new_count"] for h in history[-30:]) or 1
        for h in history[-30:]:
            pct = int(h["new_count"] / max_count * 100)
            bars += f'<div class="hist-bar" title="{h["date"]}: {h["new_count"]}篇">' \
                    f'<div class="hist-fill" style="height:{pct}%"></div></div>'
        history_html = f"""
        <div class="history-section">
            <h3>📊 采集趋势（近30天）</h3>
            <div class="hist-chart">{bars}</div>
        </div>
        """
    
    def paper_card(p):
        authors = ", ".join(p.get("authors", []))
        abstract = p.get("abstract", "")[:300]
        if len(p.get("abstract", "")) > 300:
            abstract += "..."
        
        cats = " · ".join(p.get("categories", []))
        source_badge = "📄 arXiv" if p.get("source") == "arXiv" else "📘 Semantic Scholar"
        
        return f"""
        <div class="paper-card">
            <div class="paper-header">
                <a href="{p.get("url", "#")}" target="_blank" class="paper-title">{p.get("title", "")}</a>
                <span class="paper-source" data-source="{p.get("source", "")}">{source_badge}</span>
            </div>
            <div class="paper-meta">
                <span class="paper-date">📅 {p.get("published", "未知")}</span>
                <span class="paper-authors">👤 {authors}</span>
            </div>
            <div class="paper-abstract">{abstract}</div>
            {f'<div class="paper-cats">🏷️ {cats}</div>' if cats else ''}
            {f'<a href="{p.get("pdf_url", "")}" target="_blank" class="paper-pdf">📥 PDF</a>' if p.get("pdf_url") else ''}
        </div>
        """
    
    today_html = "\n".join(paper_card(p) for p in today_papers) or '<p class="empty">暂无今日发表的论文</p>'
    week_html = "\n".join(paper_card(p) for p in week_papers[:20]) or ""
    older_html = "\n".join(paper_card(p) for p in older_papers[:30]) or ""
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>船舶研究动态 | Ship Research Monitor</title>
    <link rel="stylesheet" href="style.css">
    <meta name="description" content="每日自动采集船舶/海洋工程领域最新研究论文">
    <meta property="og:title" content="船舶研究动态">
    <meta property="og:description" content="每日自动采集船舶/海洋工程领域最新研究论文">
</head>
<body>
    <header>
        <div class="header-content">
            <h1>🚢 船舶研究动态</h1>
            <p class="subtitle">Ship & Maritime Research Monitor · 每日自动更新</p>
            <p class="update-info">🕐 最后更新: {updated} · 数据来源: arXiv + Semantic Scholar</p>
        </div>
    </header>
    
    <main>
        {stats_html}
        {history_html}
        
        <section id="today">
            <h2>📌 今日发表</h2>
            {today_html}
        </section>
        
        <section id="week">
            <h2>📅 近7天</h2>
            {week_html}
        </section>
        
        <section id="all">
            <h2>📚 全部论文 ({len(papers)}篇)</h2>
            <div class="filter-bar">
                <input type="text" id="search-input" placeholder="🔍 搜索标题/摘要..." oninput="filterPapers()">
                <select id="source-filter" onchange="filterPapers()">
                    <option value="all">全部来源</option>
                    <option value="arXiv">📄 arXiv</option>
                    <option value="Semantic Scholar">📘 Semantic Scholar</option>
                </select>
            </div>
            <div id="papers-list">
                {older_html}
            </div>
        </section>
    </main>
    
    <footer>
        <p>⚡ 每日 {config.get("project", {}).get("update_time", "08:00")} 自动更新 · 基于 GitHub Actions</p>
        <p>数据来源: arXiv API · Semantic Scholar API</p>
    </footer>
    
    <script>
    function filterPapers() {{
        const query = document.getElementById('search-input').value.toLowerCase();
        const source = document.getElementById('source-filter').value;
        const cards = document.querySelectorAll('#papers-list .paper-card');
        
        cards.forEach(card => {{
            const title = card.querySelector('.paper-title').textContent.toLowerCase();
            const abs = card.querySelector('.paper-abstract')?.textContent.toLowerCase() || '';
            const cardSource = card.querySelector('.paper-source')?.getAttribute('data-source') || '';
            
            const matchText = title.includes(query) || abs.includes(query);
            const matchSource = source === 'all' || cardSource === source;
            
            card.style.display = (matchText && matchSource) ? 'block' : 'none';
        }});
    }}
    </script>
</body>
</html>"""
    
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    
    return html


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 50)
    print(f"🚢 船舶研究动态采集器")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    config = load_config()
    existing = load_existing(OUTPUT_JSON)
    
    all_new = []
    
    # 1. arXiv
    print("\n📄 正在从arXiv获取论文...")
    try:
        arxiv_papers = fetch_arxiv(config)
        print(f"   ✅ 获取到 {len(arxiv_papers)} 篇")
        all_new.extend(arxiv_papers)
    except Exception as e:
        print(f"   ❌ arXiv 采集失败: {e}")
    
    # 2. Semantic Scholar
    print("\n📘 正在从Semantic Scholar获取论文...")
    try:
        s2_papers = fetch_semantic_scholar(config)
        print(f"   ✅ 获取到 {len(s2_papers)} 篇")
        all_new.extend(s2_papers)
    except Exception as e:
        print(f"   ❌ Semantic Scholar 采集失败: {e}")
    
    # 3. 合并去重
    print(f"\n🔄 合并去重...")
    merged = merge_papers(all_new, existing)
    print(f"   📊 总论文数: {merged['total']}")
    print(f"   🆕 今日新增: {merged['today_new']}")
    
    # 4. 保存JSON
    save_json(merged, OUTPUT_JSON)
    print(f"   ✅ 数据已保存: {OUTPUT_JSON}")
    
    # 5. 生成HTML
    print(f"\n📝 生成静态页面...")
    generate_html(merged, config)
    print(f"   ✅ 页面已生成: {OUTPUT_HTML}")
    
    # 6. 摘要输出
    print("\n" + "=" * 50)
    print(f"✅ 采集完成!")
    print(f"   总论文: {merged['total']}")
    print(f"   今日新增: {merged['today_new']}")
    print(f"   页面大小: {os.path.getsize(OUTPUT_HTML) // 1024} KB")
    print("=" * 50)


if __name__ == "__main__":
    main()
