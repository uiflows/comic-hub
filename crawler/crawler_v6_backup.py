#!/usr/bin/env python3
"""
ComicHub 漫画爬虫 v6
====================
- 抽象 BaseCrawler，方便接入多源
- 自动下载封面 cover.jpg + 元数据 manga.json (标题/作者/简介/标签/章节)
- 断点续传 (跳过已下载章节/页面)
- 多线程并发下载图片
- tqdm 进度条

用法:
    python3 crawler.py <slug> [start] [limit]
    python3 crawler.py <slug> --workers 5

环境:
    需要 pw_tool.StealthBrowser (Playwright + stealth) 在 PYTHONPATH 中。
"""

import sys
import re
import json
import asyncio
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

try:
    from tqdm import tqdm
except ImportError:  # tqdm 可选，缺失时退化为简单计数
    def tqdm(iterable=None, total=None, desc="", **kw):
        return iterable if iterable is not None else _NullBar(total, desc)

    class _NullBar:
        def __init__(self, total, desc):
            self.total, self.n, self.desc = total or 0, 0, desc
        def update(self, n=1):
            self.n += n
            print(f"  {self.desc}: {self.n}/{self.total}", end="\r")
        def __enter__(self): return self
        def __exit__(self, *a): print()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ─────────────────────────── 工具 ───────────────────────────

def safe_name(text: str, maxlen: int = 40) -> str:
    """清洗成安全的目录名"""
    cleaned = re.sub(r'[^\w\s一-鿿-]', '', text).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned[:maxlen] or "untitled"


# ─────────────────────────── 抽象基类 ───────────────────────────

class BaseCrawler:
    """所有漫画源的基类。子类需实现 fetch_meta / fetch_chapters / fetch_pages。"""

    name = "base"
    base_url = ""

    def __init__(self, workers: int = 4, proxy: str | None = "http://127.0.0.1:7897"):
        self.workers = workers
        self.http = requests.Session()
        self.http.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Referer": self.base_url or "https://www.google.com",
        })
        if proxy:
            self.http.proxies = {"http": proxy, "https": proxy}

    # ── 子类实现 ──
    async def fetch_meta(self, sb, slug: str) -> dict:
        """返回 {title, author, description, tags, cover_url}"""
        raise NotImplementedError

    async def fetch_chapters(self, sb, slug: str) -> list:
        """返回 [{title, url, uid}, ...] (按阅读顺序)"""
        raise NotImplementedError

    async def fetch_pages(self, sb, chapter: dict) -> list:
        """返回 [img_url, ...]"""
        raise NotImplementedError

    # ── 通用下载逻辑 ──
    def _download_one(self, img_url: str, dest: Path) -> bool:
        if dest.exists() and dest.stat().st_size > 0:
            return True
        try:
            r = self.http.get(img_url, timeout=60)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return True
        except Exception as e:
            print(f"    ❌ {dest.name}: {e}")
            return False

    def download_pages(self, page_urls: list, ch_dir: Path) -> int:
        """并发下载一章的所有页面，返回成功数。断点续传。"""
        ch_dir.mkdir(parents=True, exist_ok=True)
        tasks = []
        for j, url in enumerate(page_urls):
            if not url:
                continue
            ext = Path(urlparse(url).path).suffix or ".jpg"
            tasks.append((url, ch_dir / f"{j + 1:03d}{ext}"))

        ok = 0
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futures = {ex.submit(self._download_one, u, d): d for u, d in tasks}
            with tqdm(total=len(futures), desc="  下载", unit="p", leave=False) as bar:
                for fut in as_completed(futures):
                    if fut.result():
                        ok += 1
                    bar.update(1)
        return ok

    def download_cover(self, cover_url: str, manga_dir: Path) -> str | None:
        if not cover_url:
            return None
        ext = Path(urlparse(cover_url).path).suffix or ".jpg"
        dest = manga_dir / f"cover{ext}"
        if dest.exists() and dest.stat().st_size > 0:
            return dest.name
        manga_dir.mkdir(parents=True, exist_ok=True)
        if self._download_one(cover_url, dest):
            print(f"  🖼  封面 → {dest.name}")
            return dest.name
        return None

    # ── 主流程 ──
    async def run(self, slug: str, start: int = 0, limit: int = 0):
        from pw_tool import StealthBrowser  # 延迟导入，缺失时其它逻辑仍可用

        manga_dir = DATA_DIR / slug
        manga_dir.mkdir(parents=True, exist_ok=True)

        async with StealthBrowser() as sb:
            # 1. 元数据 + 章节
            print(f"📋 [{self.name}] {slug} — 抓取元数据...")
            meta = {}
            try:
                meta = await self.fetch_meta(sb, slug)
            except Exception as e:
                print(f"  ⚠️ 元数据抓取失败: {e}")

            chapters = await self.fetch_chapters(sb, slug)
            print(f"  共 {len(chapters)} 章")

            # 封面
            cover_name = self.download_cover(meta.get("cover_url", ""), manga_dir)

            # 选择要爬取的章节区间，但保留全局 index 用于稳定命名
            indexed = list(enumerate(chapters))  # [(global_idx, ch)]
            if limit > 0:
                indexed = indexed[start:start + limit]
            elif start > 0:
                indexed = indexed[start:]

            # 2. 逐章下载
            ch_records = []
            total = 0
            for gidx, ch in indexed:
                title = ch["title"]
                ch_dir = manga_dir / f"{gidx + 1:03d}_{safe_name(title)}"
                cmeta_path = ch_dir / "meta.json"

                # 断点续传：已完整下载则跳过
                if cmeta_path.exists():
                    try:
                        cm = json.loads(cmeta_path.read_text())
                        if cm.get("downloaded", 0) >= cm.get("pages", 1) > 0:
                            print(f"⏭  [{gidx + 1}] {title} (已完成 {cm['downloaded']}p)")
                            ch_records.append({"dir": ch_dir.name, "title": title,
                                               "index": gidx + 1, "pages": cm["pages"]})
                            total += cm["downloaded"]
                            continue
                    except Exception:
                        pass

                print(f"📖 [{gidx + 1}] {title}")
                try:
                    pages = await self.fetch_pages(sb, ch)
                except Exception as e:
                    print(f"  ❌ 解析失败: {e}")
                    continue

                if not pages:
                    print("  ⚠️ 无页面")
                    continue

                dl = self.download_pages(pages, ch_dir)
                print(f"  ✅ {dl}/{len(pages)} 页")
                cmeta_path.write_text(
                    json.dumps({"pages": len(pages), "downloaded": dl,
                                "title": title, "index": gidx + 1}, ensure_ascii=False)
                )
                ch_records.append({"dir": ch_dir.name, "title": title,
                                   "index": gidx + 1, "pages": len(pages)})
                total += dl

            # 3. 写 manga.json (合并已存在记录，保持全集顺序)
            self._write_manga_meta(manga_dir, slug, meta, cover_name, ch_records)

        print(f"\n{'=' * 60}\n✅ 共 {total} 张 → {manga_dir}")

    def _write_manga_meta(self, manga_dir, slug, meta, cover_name, ch_records):
        path = manga_dir / "manga.json"
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                pass

        # 合并章节：以 index 为键，新记录覆盖旧记录
        ch_map = {c["index"]: c for c in existing.get("chapters", [])}
        for c in ch_records:
            ch_map[c["index"]] = c
        chapters = sorted(ch_map.values(), key=lambda c: c["index"])

        data = {
            "slug": slug,
            "title": meta.get("title") or existing.get("title") or slug,
            "author": meta.get("author") or existing.get("author", ""),
            "description": meta.get("description") or existing.get("description", ""),
            "tags": meta.get("tags") or existing.get("tags", []),
            "cover": cover_name or existing.get("cover"),
            "source": self.name,
            "chapters": chapters,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"  📝 元数据 → manga.json ({len(chapters)} 章)")


# ─────────────────────────── MangaCopy 实现 ───────────────────────────

class MangaCopyCrawler(BaseCrawler):
    name = "mangacopy"
    base_url = "https://www.mangacopy.com"

    @staticmethod
    def _decrypt(cct: str, content_key: str) -> list:
        """AES-128-CBC 解密页面列表"""
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        iv = content_key[:16].encode()
        ct = bytes.fromhex(content_key[16:])
        cipher = AES.new(cct.encode(), AES.MODE_CBC, iv=iv)
        return json.loads(unpad(cipher.decrypt(ct), AES.block_size))

    async def fetch_meta(self, sb, slug: str) -> dict:
        await sb.fetch(f"{self.base_url}/comic/{slug}")
        # 通过页面 JS 读取 meta 标签和 DOM
        cover = await sb.eval(
            "document.querySelector('meta[property=\"og:image\"]')?.content || "
            "document.querySelector('.comicParticulars-left-img img')?.src || ''")
        title = await sb.eval(
            "document.querySelector('h6.comicParticulars-title-right')?.innerText || "
            "document.querySelector('meta[property=\"og:novel:book_name\"]')?.content || "
            "document.querySelector('title')?.innerText || ''")
        author = await sb.eval(
            "Array.from(document.querySelectorAll('.comicParticulars-right-txt a'))"
            ".map(a=>a.innerText).join(', ') || "
            "document.querySelector('meta[property=\"og:novel:author\"]')?.content || ''")
        desc = await sb.eval(
            "document.querySelector('.intro-total')?.innerText || "
            "document.querySelector('meta[name=\"description\"]')?.content || ''")
        tags = await sb.eval(
            "JSON.stringify(Array.from(document.querySelectorAll('.comicParticulars-tag a'))"
            ".map(a=>a.innerText.replace('#','').trim()).filter(Boolean))")
        try:
            tag_list = json.loads(tags) if tags else []
        except Exception:
            tag_list = []
        return {
            "cover_url": urljoin(self.base_url, cover) if cover else "",
            "title": (title or "").strip(),
            "author": (author or "").strip(),
            "description": (desc or "").strip(),
            "tags": tag_list,
        }

    async def fetch_chapters(self, sb, slug: str) -> list:
        # fetch_meta 已经导航到 comic 页；若单独调用则重新导航
        if not await sb.eval("location.href.includes('/comic/')"):
            await sb.fetch(f"{self.base_url}/comic/{slug}")
        links = await sb.extract('a[href*="/chapter/"]', attr="href")
        texts = await sb.extract('a[href*="/chapter/"]', attr="innerText")
        chapters, seen = [], set()
        for href, text in zip(links, texts):
            if not href or not text or "/chapter/" not in href:
                continue
            uid = href.split("/chapter/")[-1]
            if uid in seen or text.strip() in ("開始閱讀", "开始阅读"):
                continue
            seen.add(uid)
            chapters.append({"title": text.strip(), "url": urljoin(self.base_url, href), "uid": uid})
        return chapters

    async def fetch_pages(self, sb, chapter: dict) -> list:
        await sb.fetch(chapter["url"])
        cct = await sb.eval("window.cct || ''")
        ck = await sb.eval("window.contentKey || ''")
        if not ck:
            raise RuntimeError("contentKey 为空")
        pages = self._decrypt(cct, ck)
        return [p.get("url", "") for p in pages]


# ─────────────────────────── 入口 ───────────────────────────

SOURCES = {"mangacopy": MangaCopyCrawler}


def main():
    ap = argparse.ArgumentParser(description="ComicHub 漫画爬虫")
    ap.add_argument("slug", help="漫画 slug")
    ap.add_argument("start", nargs="?", type=int, default=0, help="起始章节索引")
    ap.add_argument("limit", nargs="?", type=int, default=0, help="爬取数量 (0=全部)")
    ap.add_argument("--source", default="mangacopy", choices=list(SOURCES))
    ap.add_argument("--workers", type=int, default=4, help="并发下载线程数")
    ap.add_argument("--no-proxy", action="store_true")
    args = ap.parse_args()

    crawler = SOURCES[args.source](
        workers=args.workers,
        proxy=None if args.no_proxy else "http://127.0.0.1:7897",
    )
    asyncio.run(crawler.run(args.slug, args.start, args.limit))


if __name__ == "__main__":
    main()
