# 📚 ComicHub — 漫画阅读站

自托管的中文漫画阅读站：爬取 → 本地存储 → Docker nginx 部署 → Cloudflare Tunnel 公网访问。纯静态前端 + 零构建，支持 MangaDex 在线搜索与本地书架无缝切换。

## ✨ 功能

| 模块 | 功能 |
|------|------|
| 🕷 **爬虫** | 从 mangacopy.com 自动爬取漫画，AES-128-CBC 解密，断点续传，多线程下载 |
| 📖 **阅读器** | 卷轴模式 / 翻页模式，键盘快捷键，移动端手势，双指缩放 |
| 📚 **书架** | 网格/列表双视图，搜索过滤，阅读进度自动保存 |
| 🌐 **双源** | 本地书架 + MangaDex API 在线搜索，无缝切换 |
| 🎨 **主题** | 暗色/亮色自动跟随系统，手动切换 |
| 🚀 **部署** | Docker Compose 一键启动，nginx 高性能静态服务 |
| 🔒 **暴露** | Cloudflare Tunnel 安全穿透，无需公网 IP |

## 🚀 快速启动

```bash
# 1. 克隆
git clone https://github.com/uiflows/comic-hub.git
cd comic-hub

# 2. 准备漫画数据（可选 — 没有数据也能启动，书架为空）
mkdir -p data

# 3. 启动
docker compose up -d --build

# 4. 访问
open http://localhost:8080
```

**自定义端口：**
```bash
COMICHUB_PORT=9000 docker compose up -d --build
```

**健康检查：**
```bash
curl http://localhost:8080/health
# → {"status":"ok"}
```

## 📥 爬取漫画

```bash
cd crawler
pip install -r requirements.txt          # 需 pw_tool.StealthBrowser 在 PYTHONPATH
playwright install chromium              # 首次需要安装浏览器

# 下载全部章节
python3 crawler.py <slug>

# 下载指定范围（第 0 章起，共 5 章）
python3 crawler.py <slug> 0 5

# 5 线程并发下载
python3 crawler.py <slug> --workers 5
```

爬虫自动完成：
- 📸 下载封面 → `data/{slug}/cover.jpg`
- 📝 写入元数据 → `data/{slug}/manga.json`（标题/作者/简介/标签/章节顺序）
- ⏭️ 断点续传 — 跳过已完整下载的章节
- 📊 `tqdm` 进度条 + 并发图片下载

## 🗂 项目结构

```
comic-hub/
├── Dockerfile                  # nginx:1.27-alpine 镜像
├── docker-compose.yml          # 一键部署（端口/卷挂载/健康检查）
├── nginx.conf                  # nginx 配置（静态文件 + MangaDex 反代 + autoindex）
├── .dockerignore               # 构建排除
├── .gitignore                  # 版本控制排除（credentials/cookies/数据）
│
├── crawler/                    # 🕷 漫画爬虫
│   ├── crawler.py              # 主爬虫：BaseCrawler 抽象 + MangaCopyCrawler 实现
│   ├── crawler_py.py           # 备用爬虫实现
│   ├── crawler_v6_backup.py    # v6 旧版备份
│   ├── explore_mangacopy.py    # 站点探索/逆向工具
│   ├── explore_chapter.py      # 章节结构分析
│   ├── explore_v3/v4/v5.py     # 历史探索脚本
│   ├── scrape_slugs.py         # 批量采集漫画 slug
│   ├── test_stealth.py         # 反检测测试
│   └── requirements.txt        # Python 依赖
│
├── www/                        # 🎨 前端（纯 HTML/CSS/JS，零构建）
│   ├── index.html              # 书架页：网格/列表 + 搜索 + 继续阅读
│   ├── local.html              # 阅读器：卷轴/翻页 + 缩略图导航 + 手势
│   ├── lib.js                  # 共享逻辑：数据访问 / 进度管理 / 主题切换
│   └── style.css               # CSS 变量主题 + 通用组件样式
│
├── import_to_mccms.py          # 🔄 导入漫城CMS（MC CMS / 苹果CMS漫画版）
├── import_to_mccms.sh          # Shell 版导入脚本（旧版兼容）
├── webp2jpg.py                 # 🖼 WebP → JPEG 批量转换工具
│
├── data/                       # 📦 漫画数据（gitignore，不提交）
│   └── {slug}/
│       ├── cover.jpg           # 封面图
│       ├── manga.json          # 元数据（标题/作者/简介/标签/章节）
│       └── {NNN}_{章节名}/
│           ├── 001.webp
│           ├── 002.webp
│           └── ...
│
├── .cloudflare-tunnel/         # 🔒 Cloudflare Tunnel 配置（不提交）
├── README.md                   # 本文件
└── 日志.md                     # 项目操作日志
```

## 🏗 架构

```
┌─────────────────┐
│  浏览器访问      │
│ comic.aweb3.cc  │
└────────┬────────┘
         │ HTTPS
    ┌────▼─────┐
    │Cloudflare│  ← CDN + Tunnel
    └────┬─────┘
         │ cloudflared
    ┌────▼─────┐
    │  nginx   │  ← Docker 容器，端口 127.0.0.1:8080
    │ (Alpine) │
    └────┬─────┘
         │
    ┌────┴────────────────────┐
    │         │        │       │
    ▼         ▼        ▼       ▼
  静态     /data/    /api/   /covers/
  前端    漫画数据  MangaDex  MangaDex
  (html)  (文件)    (反代)    (封面CDN)
```

## 📖 阅读器快捷键

| 按键 | 功能 |
|------|------|
| `← →` `↑ ↓` | 翻页 |
| `Space` | 下一章 |
| `Esc` | 返回目录 |
| `M` | 切换卷轴/翻页模式 |
| 点击左侧/右侧 | 上页/下页 |
| 移动端左右滑 | 上页/下页 |
| 双指缩放 | 翻页模式下放大/缩小 |

## 🔧 辅助工具

### 导入漫城CMS

将本地漫画批量导入漫城CMS（苹果CMS漫画版）：

```bash
# Python 版（推荐 — 支持完整元数据映射）
python3 import_to_mccms.py

# Shell 版（旧版兼容）
./import_to_mccms.sh
```

详细 API 文档见 [comic-cms-integration 技能](https://github.com/nousresearch/hermes-agent)。

### WebP 转 JPEG

```bash
python3 webp2jpg.py <输入目录> <输出目录>
```

## 🛠 技术栈

| 层 | 技术 |
|----|------|
| **前端** | 纯 HTML/CSS/JS（零框架，零构建） |
| **Web 服务器** | nginx 1.27 (Alpine) |
| **爬虫** | Python 3 + Playwright + playwright-stealth + pycryptodome |
| **反爬对抗** | 随机 UA + stealth 补丁 + 请求延迟 |
| **图片格式** | WebP（存储）/ 自动转换（CMS 导入时） |
| **容器化** | Docker + Docker Compose |
| **公网暴露** | Cloudflare Tunnel |
| **元数据** | manga.json（自定义格式，含中英文标签） |

## ⚙️ 设计理念

- **元数据优先，autoindex 回退** — 前端优先读 `manga.json`（正确章节顺序+封面）；旧数据无此文件时自动回退 nginx autoindex
- **零依赖前端** — 无 npm、无打包、无框架，打开即用
- **多源爬虫框架** — `BaseCrawler` 抽象，新增漫画源只需实现 `fetch_meta` / `fetch_chapters` / `fetch_pages`
- **热更新开发** — `www/`、`nginx.conf`、`data/` 以只读卷挂载，改代码即时生效，无需重建镜像

## 📄 许可

MIT
