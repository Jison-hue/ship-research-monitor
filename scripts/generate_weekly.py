#!/usr/bin/env python3
"""
船舶研究周报生成器
读取 papers.json，生成 weekly.html
"""
import json, os
from datetime import datetime, timedelta
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "papers.json")
OUTPUT = os.path.join(BASE, "docs", "weekly.html")

def generate():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    papers = data.get("papers", [])
    
    today = datetime.now().date()
    mon = today - timedelta(days=today.weekday())
    sun = mon + timedelta(days=6)
    last_mon = mon - timedelta(days=7)
    last_sun = mon - timedelta(days=1)
    
    ws = mon.strftime("%Y-%m-%d")
    we = sun.strftime("%Y-%m-%d")
    lws = last_mon.strftime("%Y-%m-%d")
    lwe = last_sun.strftime("%Y-%m-%d")
    
    week_papers = [p for p in papers if ws <= p.get("published", "")[:10] <= we]
    last_week = [p for p in papers if lws <= p.get("published", "")[:10] <= lwe]
    
    topics = Counter(p.get("topic","其他") for p in week_papers)
    last_topics = Counter(p.get("topic","其他") for p in last_week)
    
    changes = {}
    for t in set(list(topics.keys()) + list(last_topics.keys())):
        c = topics.get(t,0) - last_topics.get(t,0)
        if c != 0: changes[t] = c
    
    hot = sorted(week_papers, key=lambda p: p.get("cited_by",0), reverse=True)[:5]
    # ── 本周亮点 ──
    highlight = None
    highlight_score = 0
    for p in week_papers:
        jrk = p.get("journal_rank","")
        rank_bonus = {"一区/顶刊": 3, "二区/重要": 2, "核心期刊": 1}.get(jrk, 0)
        score = p.get("cited_by", 0) * 0.3 + rank_bonus * 20
        if score > highlight_score:
            highlight_score = score
            highlight = p
    
    hl_html = ""
    if highlight:
        doi = highlight.get("doi","")
        dh = '<a href="https://doi.org/'+doi+'" class="doi">'+doi[:30]+'</a>' if doi else ""
        au = ", ".join(highlight.get("authors",[])[:2])
        jour = highlight.get("journal","")
        tp = highlight.get("topic","")
        rk = highlight.get("journal_rank","")
        hl_html = '''<div class="hl">
            <div class="hl-badge">🔥 本周亮点</div>
            <div class="hl-title">''' + esc(highlight["title"][:100]) + '''</div>
            <div class="hl-meta">''' + au + ''' | ''' + jour[:30] + ''' | ''' + rk + ''' | 已被引用''' + str(highlight.get("cited_by",0)) + '''次</div>
            <div class="hl-desc">💡 建议关注：本周''' + tp + '''方向的重点文献，发表在''' + esc(jour[:20]) + '''，由''' + au + '''等人完成，是该方向值得关注的新进展。</div>
            <div class="hl-doi">''' + dh + '''</div>
        </div>'''
    
    insts = Counter()
    for p in week_papers:
        for i in p.get("institutions",[]):
            if i: insts[i.split(",")[0].strip()[:45]] += 1
    
    wn = today.isocalendar()[1]
    
    def esc(s):
        return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    
    def t(s):  # topic items
        r = ""
        for name, cnt in sorted(s.items(), key=lambda x: -x[1])[:8]:
            c = changes.get(name, 0)
            ch = ""
            if c > 0: ch = '<span class="ch-up">\u25b2'+str(c)+'</span>'
            elif c < 0: ch = '<span class="ch-down">\u25bc'+str(abs(c))+'</span>'
            r += '<div class="wl"><span>'+esc(name)+'</span><span class="wc">'+str(cnt)+'\u7bc7</span>'+ch+'</div>'
        return r
    
    def h():  # hot papers
        r = ""
        for i,p in enumerate(hot):
            doi = p.get("doi","")
            dh = '<a href="https://doi.org/'+doi+'" class="doi">'+doi[:30]+'</a>' if doi else ""
            au = ", ".join(p.get("authors",[])[:2])
            r += '<div class="pr"><span class="pn">'+str(i+1)+'</span><div class="pb"><div class="pt"><a href="'+esc(p.get("url","#"))+'" target="_blank">'+esc(p["title"][:90])+'</a></div><div class="pm">'+p.get("published","")[:10]+' | '+esc(au[:40])+' | \u3010'+str(p.get("cited_by",0))+'\u5f15\u7528\u3011'+dh+'</div></div></div>'
        return r
    
    def i():  # institutions
        r = ""
        for name, cnt in insts.most_common(8):
            r += '<div class="wl"><span>'+esc(name)+'</span><span class="wc">'+str(cnt)+'</span></div>'
        return r or '<p style="color:#888;font-size:.8rem">\u6682\u65e0\u6570\u636e</p>'
    
    html = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
    html += '<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
    html += '<title>\u8239\u8236\u4e0e\u6d77\u6d0b\u5de5\u7a0b\u7814\u7a76\u5468\u62a5 &middot; \u7b2c'+str(wn)+'\u5468</title>\n'
    html += '<link rel="stylesheet" href="style.css">\n'
    html += '<style>body{background:#f0f2f5}.wp{max-width:680px;margin:0 auto;padding:24px 16px}.wh{text-align:center;margin-bottom:24px}.wh h1{font-size:1.35rem;font-weight:700}.wh .s{color:#636e72;font-size:.82rem;margin-top:4px}.ws{background:#fff;border-radius:10px;padding:16px 18px;border:1px solid #e9ecef;margin-bottom:14px}.ws h2{font-size:.9rem;font-weight:600;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #5B8FA8}.wss{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}.wsc{text-align:center;padding:14px 8px;background:#fff;border-radius:10px;border:1px solid #e9ecef}.wsc .n{display:block;font-size:1.25rem;font-weight:700;color:#5B8FA8}.wsc .l{font-size:.72rem;color:#636e72;margin-top:2px}.wl{display:flex;justify-content:space-between;padding:5px 0;font-size:.8rem;border-bottom:1px solid #f0f0f0}.wl:last-child{border:none}.wc{font-weight:600;color:#5B8FA8}.ch-up{color:#27ae60;font-size:.72rem;margin-left:6px}.ch-down{color:#e74c3c;font-size:.72rem;margin-left:6px}.pr{display:flex;gap:8px;padding:6px 0;border-bottom:1px solid #f0f0f0}.pr:last-child{border:none}.pn{font-weight:700;color:#5B8FA8;min-width:20px}.pb{flex:1;min-width:0}.pt{font-size:.8rem;font-weight:500}.pt a{color:#2d3436}.pt a:hover{color:#5B8FA8}.pm{font-size:.7rem;color:#636e72;margin-top:1px}.doi{font-family:monospace;font-size:.65rem;color:#5B8FA8!important;word-break:break-all}.bk{display:inline-block;margin-top:10px;font-size:.76rem;color:#5B8FA8}footer{text-align:center;padding:20px;color:#636e72;font-size:.7rem;max-width:680px;margin:0 auto}</style>\n</head>\n<body>\n'
    html += '<div class="wp">\n'
    html += '<div class="wh"><h1>\U0001f6a2 \u8239\u8236\u4e0e\u6d77\u6d0b\u5de5\u7a0b\u7814\u7a76\u5468\u62a5</h1><p class="s">\u7b2c'+str(wn)+'\u5468 &middot; '+ws+' ~ '+we+'</p></div>\n'
    html += '<div class="wss"><div class="wsc"><span class="n">'+str(len(week_papers))+'</span><span class="l">\u672c\u5468\u8bba\u6587</span></div><div class="wsc"><span class="n">'+str(len(last_week))+'</span><span class="l">\u4e0a\u5468\u8bba\u6587</span></div><div class="wsc"><span class="n">'+str(len(topics))+'</span><span class="l">\u7814\u7a76\u65b9\u5411</span></div></div>\n'
    html += '<div class="ws"><h2>\U0001f4ca \u672c\u5468\u7814\u7a76\u65b9\u5411</h2>'+t(dict(topics.most_common()))+'</div>\n'
    html += '<div class="ws"><h2>\U0001f525 \u70ed\u70b9\u8bba\u6587</h2>'+h()+'</div>\n'
    html += '<div class="ws"><h2>\U0001f3db\ufe0f \u6d3b\u8dc3\u673a\u6784</h2>'+i()+'</div>\n'
    html += '<a href="index.html" class="bk">\u2190 \u8fd4\u56de\u4e3b\u770b\u677f</a>\n</div>\n'
    html += '<footer>\u6bcf3\u5929\u81ea\u52a8\u91c7\u96c6 &middot; \u6bcf\u5468\u81ea\u52a8\u6c47\u603b</footer>\n</body>\n</html>'
    
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\u2705 \u5468\u62a5\u5df2\u751f\u6210: {OUTPUT} ({os.path.getsize(OUTPUT)//1024}KB)")

if __name__ == "__main__":
    generate()
