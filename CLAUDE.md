# ComicHub - 漫画阅读站

## 项目概述
本地漫画阅读站，爬取 mangacopy.com 等中文漫画源的漫画，解密后本地存储，通过 nginx 提供服务，前端提供阅读器 UI。

## 架构
```
mangacopy.com → Playwright+Stealth (获取加密 key)
                    ↓
              Python AES-128-CBC (解密 → 图片 URL)
                    ↓
              requests (下载图片到磁盘)
                    ↓
              nginx (serve /data/ 目录 + 反向代理 MangaDex API)
                    ↓
              静态 HTML 前端 (书架 + 章节列表 + 翻页阅读器)
```

## 项目布局
```
~/sites/comic-hub/
  crawler/crawler.py     ← 主爬虫脚本
  data/{slug}/           ← 下载的漫画 (自动创建)
    {NNN}_{chapter}/     ← 每章一个目录
      001.webp           ← 编号页面
      meta.json          ← {pages, downloaded}
  www/
    index.html           ← MangaDex 搜索 + "本地书架"按钮
    local.html           ← 本地书架 + 阅读器
  nginx.conf             ← nginx 配置 (含 /data/ mount)
```

## 技术栈
- 前端: 纯 HTML/CSS/JS (无框架，无构建步骤)
- 后端: nginx 静态服务 + 反向代理
- 爬虫: Python 3 + Playwright + playwright-stealth + pycryptodome
- 存储: 本地文件系统，nginx autoindex 提供目录浏览
- 部署: Docker nginx，通过 Cloudflare Tunnel 暴露

## 数据目录结构
```
data/{slug}/
  {NNN}_{chapter_title}/
    001.webp
    002.webp
    ...
    meta.json  → {"pages": N, "downloaded": M}
```

## nginx 关键配置
- /data/ → alias /data/manga/ (autoindex on)
- /api/ → proxy MangaDex API
- /covers/ → proxy MangaDex covers
- / → 静态文件

## 已知问题（已修复）
1. 阅读器只有"显示/隐藏"翻页，体验差
2. 书架没有封面图
3. 爬虫没有元数据 (作者、简介、封面)
4. 没有阅读进度记录
5. UI 设计简陋
6. 不支持移动端手势
7. 没有搜索本地漫画功能
8. 爬虫只支持 mangacopy 单一源
9. 没有 Docker Compose 一键部署
