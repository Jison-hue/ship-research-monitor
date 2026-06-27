# 🚢 船舶研究动态监测

> 每日自动采集船舶/海洋工程领域最新研究论文，零成本，设置一次就不用管。

## 功能

- 📄 **arXiv** — 从相关分类（机器人、系统工程、流体力学等）抓取最新预印本
- 📘 **Semantic Scholar** — 补充检索相关学术论文
- 🔍 **智能排序** — 按关键词匹配度 + 时效性打分，相关论文排前面
- 📊 **统计面板** — 总数、今日新增、近7天趋势一目了然
- 🔎 **在线搜索** — 支持按关键词和来源筛选
- 📱 **移动适配** — 手机电脑都能看

## 快速上手

### 1. 克隆仓库到 GitHub

```bash
# 在 GitHub 上新建一个仓库，比如 ship-research-monitor
# 然后推上去
git init
git add .
git commit -m "init: ship research monitor"
git remote add origin https://github.com/你的用户名/ship-research-monitor.git
git push -u origin main
```

### 2. 开启 GitHub Pages

- 进入仓库 Settings → Pages
- Source 选 **GitHub Actions**

### 3. 等它跑起来

推送后 Actions 会自动触发一次采集。以后每天北京时间 08:00 自动更新。

也可以去 Actions 页面点 **Run workflow** 手动触发。

### 4. 访问

`https://你的用户名.github.io/ship-research-monitor/`

## 配置说明

编辑 `config.json` 即可调整：

| 字段 | 说明 |
|------|------|
| `search_queries` | 搜索关键词列表，越精准越好 |
| `sources.arxiv.categories` | arXiv 分类 |
| `sources.semantic_scholar.limit` | 每次查询上限 |
| `project.update_time` | 页面显示的更新时间 |

## 本地测试

```bash
python3 scripts/fetch_papers.py
```

首次运行会创建 `data/papers.json` 和 `docs/index.html`，用浏览器打开 `docs/index.html` 即可预览。

## 技术栈

- Python 3 (标准库 + requests)
- GitHub Actions (定时任务)
- GitHub Pages (静态托管)
- arXiv API + Semantic Scholar API (数据源)

## 许可

MIT
