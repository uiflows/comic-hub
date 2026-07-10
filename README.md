# 📚 ComicHub — 本地漫画阅读站

现代化的本地漫画阅读站：爬取中文漫画源、本地存储、沉浸式阅读器。纯静态前端 + nginx，零构建步骤。

## 🚀 一键启动

```bash
docker compose up -d --build
# 打开 http://localhost:8080
```

自定义端口：`COMICHUB_PORT=9000 docker compose up -d`
健康检查：`curl localhost:8080/health` → `{"status":"ok"}`

## 📥 下载漫画

```bash
cd crawler
pip install -r requirements.txt          # 需 pw_tool.StealthBrowser 在 PYTHONPATH
python3 crawler.py <slug>                 # 下载全部章节
python3 crawler.py <slug> 0 5             # 从第 0 章起下载 5 章
python3 crawler.py <slug> --workers 5     # 5 线程并发下载
```

爬虫会自动：
- 下载封面 → `data/{slug}/cover.jpg`
- 写入元数据 → `data/{slug}/manga.json`（标题/作者/简介/标签/章节顺序）
- 断点续传（跳过已完整下载的章节）
- 并发下载图片 + tqdm 进度条

## 🗂 目录结构

```
comic-hub/
├── crawler/crawler.py        # BaseCrawler 抽象 + MangaCopyCrawler
├── www/
│   ├── index.html            # 书架 (网格/列表 + 继续阅读 + MangaDex 搜索)
│   ├── local.html            # 阅读器 (卷轴/翻页 + 缩略图 + 手势)
│   ├── lib.js                # 共享：数据访问 / 进度 / 主题
│   └── style.css             # 主题变量 + 通用组件
├── data/{slug}/              # 下载的漫画
│   ├── cover.jpg
│   ├── manga.json
│   └── {NNN}_{章节}/001.webp ...
├── Dockerfile · docker-compose.yml · nginx.conf
```

## 📖 阅读器功能

| 功能 | 操作 |
|------|------|
| 卷轴模式（默认）/ 翻页模式 | 顶栏 📜/📄 按钮 或 `M` 键 |
| 翻页 | `← →` `↑ ↓` / 点击左右区域 / 移动端左右滑动 |
| 下一章 | `Space` |
| 返回目录 | `Esc` |
| 缩略图导航 | 顶栏 🖼 按钮，点击跳转 |
| 双指缩放 / 双击放大 | 翻页模式移动端 |
| 主题切换 | 🌓 按钮（默认跟随系统）|
| 阅读进度 | 自动保存到 localStorage，下次自动恢复 |

## 🔧 设计说明

- **元数据优先、autoindex 回退**：前端优先读 `manga.json`（含正确章节顺序与封面）；
  旧数据无此文件时自动回退解析 nginx autoindex，保证向后兼容。
- **零依赖**：纯 HTML/CSS/JS，无框架无构建。
- **多源框架**：`BaseCrawler` 抽象，新增漫画源只需实现
  `fetch_meta` / `fetch_chapters` / `fetch_pages`。
- 开发时 `www/`、`nginx.conf`、`data/` 以只读卷挂载，改动即时生效，无需重建镜像。
