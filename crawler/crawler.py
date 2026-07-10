#!/Volumes/SSD/Hermes/Hermes总工作台/项目/comic-crawler/venv/bin/python3
"""
ComicHub 漫画爬虫 v7 — Claude Code 优化版
===========================================
反反爬策略优化 (v6 → v7):

1. Cookie 持久化 — 保存/恢复 Cloudflare clearance cookies
2. 标签页并行 — asyncio.Semaphore 控制并发章节加载
3. 双策略 — AES 解密 + intercept 图片捕获，互为 fallback
4. 请求节奏 — jitter 延迟 / 导航 cooldown / 限速
5. Headless 降级 — contentKey 连续为空 → 有头模式重试
6. aiohttp 异步下载 — 替代 requests+ThreadPoolExecutor
7. 章节级并行 — asyncio.gather + Semaphore 并发处理章节
8. 重试机制 — 指数退避 + 原子写入

用法:
    python3 crawler.py <slug> [start] [limit]
    python3 crawler.py <slug> --workers 8 --tabs 3
    python3 crawler.py <slug> --strategy intercept
    python3 crawler.py <slug> --cookie-file .cookies/manga.json
"""

from __future__ import annotations

import sys
import re
import json
import asyncio
import logging
import random
import argparse
from pathlib import Path
from typing import Optional, Callable, TypeVar, Awaitable
from urllib.parse import urljoin, urlparse

import aiohttp

try:
    from tqdm import tqdm as _tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# ─────────────────────────── 配置 ───────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COOKIE_DIR = Path(__file__).resolve().parent / ".cookies"
DEFAULT_COOKIE_FILE = COOKIE_DIR / "mangacopy.json"

BASE_URL = "https://www.mangacopy.com"
IMAGE_CDN = "https://sd.mangafunb.fun"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

BLOCK_THRESHOLD = 3  # contentKey 连续为空的阈值，触发 headless 降级
DEFAULT_RETRIES = 3
DEFAULT_CONCURRENCY = 3
DEFAULT_WORKERS = 4
DEFAULT_TABS = 1  # 默认串行，保证零回归

T = TypeVar("T")

# ─────────────────────────── 日志 ───────────────────────────

class _TqdmLogHandler(logging.Handler):
    """经 tqdm.write 输出日志，不打断进度条"""
    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        if TQDM_AVAILABLE:
            _tqdm.write(msg)
        else:
            print(msg)

log = logging.getLogger("comic-hub")


def setup_logging(verbose: bool = False):
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    # 清除默认 NullHandler，换上真 handler
    log.handlers.clear()
    h = _TqdmLogHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    log.addHandler(h)


# ─────────────────────────── 工具 ───────────────────────────

def safe_name(text: str, maxlen: int = 40) -> str:
    cleaned = re.sub(r'[^\w\s一-鿿-]', '', text).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned[:maxlen] or "untitled"


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    retries: int = DEFAULT_RETRIES,
    base_delay: float = 2.0,
) -> T:
    last_err = None
    for attempt in range(retries):
        try:
            return await fn()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
                log.warning(f"重试 {attempt + 1}/{retries}，等待 {wait:.1f}s: {e}")
                await asyncio.sleep(wait)
    raise last_err


def tqdm(iterable=None, total=None, desc="", **kw):
    if TQDM_AVAILABLE:
        return _tqdm(iterable, total=total, desc=desc, **kw)
    else:
        return _NullBar(iterable, total, desc)


class _NullBar:
    def __init__(self, it=None, total=0, desc=""):
        self._it = it
        self.total = total or 0
        self.n, self.desc = 0, desc
    def __iter__(self):
        for item in self._it or []:
            yield item
    def update(self, n=1):
        self.n += n
        if self.total:
            print(f"  {self.desc}: {self.n}/{self.total}", end="\r")
    def __enter__(self): return self
    def __exit__(self, *a): print()
    def close(self): pass
    def refresh(self): pass


# ─────────────────────────── StealthPagePool ───────────────────────────

class StealthPagePool:
    """标签页池：复用 StealthBrowser context，并行加载章节页面"""

    def __init__(self, sb, pool_size: int):
        self.sb = sb
        self.pool_size = pool_size
        self._sem = asyncio.Semaphore(pool_size)
        self._available: asyncio.Queue = asyncio.Queue()
        self._pages: list = []
        self._has_new_page: Optional[bool] = None

    async def start(self):
        if not hasattr(self.sb, 'new_page') or not callable(self.sb.new_page):
            self._has_new_page = False
            log.warning("StealthBrowser 不支持 new_page()，回退串行模式")
            return

        self._has_new_page = True
        for i in range(self.pool_size):
            try:
                page = await self.sb.new_page()
                self._pages.append(page)
                await self._available.put(page)
            except Exception as e:
                log.error(f"创建标签页 {i + 1} 失败: {e}")
                break

    async def acquire(self):
        """获取一个可用标签页"""
        await self._sem.acquire()
        return await self._available.get()

    async def release(self, page):
        """归还标签页"""
        await self._available.put(page)
        self._sem.release()

    async def stop(self):
        for page in self._pages:
            try:
                await page.close()
            except Exception:
                pass
        self._pages.clear()


# ─────────────────────────── BaseCrawler ───────────────────────────

class _StealthBlocked(Exception):
    """Stealth 被拦截，需要降级"""


class BaseCrawler:
    name = "base"
    base_url = ""

    def __init__(
        self,
        workers: int = DEFAULT_WORKERS,
        proxy: str | None = "http://127.0.0.1:7897",
        retries: int = DEFAULT_RETRIES,
        strategy: str = "aes",
        cookie_file: str | None = None,
        no_pace: bool = False,
        no_download: bool = False,
    ):
        self.workers = workers
        self.proxy = proxy
        self.retries = retries
        self.strategy = strategy
        self.cookie_file = cookie_file
        self.no_pace = no_pace
        self.no_download = no_download
        self._session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("Session not started — call start_session() first")
        return self._session

    async def start_session(self):
        connector = aiohttp.TCPConnector(limit=self.workers * 2, limit_per_host=self.workers)
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": random.choice(USER_AGENTS)},
            connector=connector,
        )

    async def close_session(self):
        if self._session:
            await self._session.close()
            self._session = None

    # ── 子类实现 ──
    async def fetch_meta(self, page, slug: str) -> dict:
        raise NotImplementedError

    async def fetch_chapters(self, page, slug: str) -> list:
        raise NotImplementedError

    async def fetch_pages(self, page, chapter: dict, strategy: str = "aes") -> list:
        raise NotImplementedError

    # ── 图片下载 (aiohttp 异步) ──
    async def _download_one(self, img_url: str, dest: Path) -> bool:
        if dest.exists() and dest.stat().st_size > 0:
            return True

        if not self.no_pace:
            await asyncio.sleep(random.uniform(0.3, 1.5))

        part = dest.with_suffix(dest.suffix + ".part")
        for attempt in range(self.retries):
            try:
                async with self.session.get(img_url, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    r.raise_for_status()
                    part.write_bytes(await r.read())
                part.replace(dest)
                return True
            except Exception as e:
                if attempt < self.retries - 1:
                    wait = 2 ** attempt + random.uniform(0, 1)
                    log.debug(f"  下载重试 {attempt + 1}/{self.retries}: {dest.name} ({wait:.1f}s)")
                    await asyncio.sleep(wait)
                else:
                    log.warning(f"  ❌ {dest.name}: {e}")
                    if part.exists():
                        part.unlink(missing_ok=True)
                    return False
        return False

    async def download_pages(self, page_urls: list, ch_dir: Path, show_bar: bool = True) -> int:
        ch_dir.mkdir(parents=True, exist_ok=True)
        if self.no_download:
            return len([u for u in page_urls if u])
        tasks = []
        for j, url in enumerate(page_urls):
            if not url:
                continue
            ext = Path(urlparse(url).path).suffix or ".jpg"
            tasks.append((url, ch_dir / f"{j + 1:03d}{ext}"))

        sem = asyncio.Semaphore(self.workers)
        async def _bounded(url, dest):
            async with sem:
                return await self._download_one(url, dest)

        coros = [_bounded(u, d) for u, d in tasks]
        ok = 0
        if show_bar and TQDM_AVAILABLE:
            with tqdm(total=len(coros), desc="  下载", unit="p", leave=False) as bar:
                for coro in asyncio.as_completed(coros):
                    if await coro:
                        ok += 1
                    bar.update(1)
        else:
            results = await asyncio.gather(*coros)
            ok = sum(1 for r in results if r)
        return ok

    async def download_cover(self, cover_url: str, manga_dir: Path) -> str | None:
        if self.no_download or not cover_url:
            return None
        ext = Path(urlparse(cover_url).path).suffix or ".jpg"
        dest = manga_dir / f"cover{ext}"
        if dest.exists() and dest.stat().st_size > 0:
            return dest.name
        manga_dir.mkdir(parents=True, exist_ok=True)
        if await self._download_one(cover_url, dest):
            log.info(f"  🖼  封面 → {dest.name}")
            return dest.name
        return None

    # ── 双策略页面获取 ──
    async def _fetch_pages_with_fallback(self, page, chapter: dict) -> list:
        primary = self.strategy
        fallback = "intercept" if primary == "aes" else "aes"

        for strat in (primary, fallback):
            try:
                pages = await self.fetch_pages(page, chapter, strategy=strat)
                if pages:
                    log.debug(f"  策略 {strat}: 获取 {len(pages)} 页")
                    return pages
            except Exception as e:
                log.debug(f"  策略 {strat} 失败: {e}")
                continue
        return []

    # ── 主流程 ──
    async def run(
        self,
        slug: str,
        start: int = 0,
        limit: int = 0,
        tabs: int = DEFAULT_TABS,
        pool: StealthPagePool | None = None,
    ):
        from pw_tool import StealthBrowser

        manga_dir = DATA_DIR / slug
        manga_dir.mkdir(parents=True, exist_ok=True)

        # Cookie 文件
        cookie_file = self.cookie_file or str(DEFAULT_COOKIE_FILE)
        Path(cookie_file).parent.mkdir(parents=True, exist_ok=True)

        await self.start_session()

        chapters, meta = await self._load_meta_with_retry(slug, cookie_file)

        if not chapters:
            log.error("无章节可爬")
            await self.close_session()
            return

        # 选择爬取范围
        indexed = list(enumerate(chapters))
        if limit > 0:
            indexed = indexed[start:start + limit]
        elif start > 0:
            indexed = indexed[start:]

        own_pool = pool is None
        if own_pool:
            pool = StealthPagePool(None, 0)  # placeholder, 下面重新创建
            if tabs > 1:
                pool = StealthPagePool(None, tabs)

        # 封面
        if own_pool:
            async with StealthBrowser(cookie_file=cookie_file) as sb:
                cover_name = await self.download_cover(meta.get("cover_url", ""), manga_dir)
        else:
            cover_name = await self.download_cover(meta.get("cover_url", ""), manga_dir)

        # 下载章节 (支持 headless 降级)
        remaining = indexed
        ch_records = []
        total = 0
        headless = True

        while remaining:
            try:
                if own_pool:
                    async with StealthBrowser(
                        cookie_file=cookie_file,
                        headless=headless,
                    ) as sb:
                        if tabs > 1:
                            pool = StealthPagePool(sb, tabs)
                            await pool.start()
                            tup = await self._run_parallel(
                                pool, remaining, manga_dir, ch_records
                            )
                        else:
                            tup = await self._run_serial(
                                sb, remaining, manga_dir, ch_records
                            )
                        new_records, new_total = tup
                else:
                    if tabs > 1:
                        tup = await self._run_parallel(
                            pool, remaining, manga_dir, ch_records
                        )
                    else:
                        # 用外部 pool 的第一个 page
                        page = await pool.acquire()
                        try:
                            tup = await self._run_serial_on_page(
                                page, remaining, manga_dir, ch_records
                            )
                        finally:
                            await pool.release(page)
                    new_records, new_total = tup

                ch_records = new_records
                total += new_total
                break  # 成功

            except _StealthBlocked:
                if headless:
                    log.warning(
                        f"⚠️  Stealth 被拦截 (连续 {BLOCK_THRESHOLD} 次 contentKey 为空)，"
                        "降级到有头模式重试…"
                    )
                    headless = False
                    continue
                else:
                    log.error("❌ 有头模式仍被拦截，放弃")
                    break

        # 写 manga.json
        self._write_manga_meta(manga_dir, slug, meta, cover_name, ch_records)

        if own_pool:
            try:
                await pool.stop()
            except Exception:
                pass

        await self.close_session()
        log.info(f"\n{'=' * 60}\n✅ 共 {total} 张 → {manga_dir}")

    async def _load_meta_with_retry(self, slug: str, cookie_file: str):
        """加载元数据和章节列表（带重试）"""
        from pw_tool import StealthBrowser

        async with StealthBrowser(cookie_file=cookie_file) as sb:
            log.info(f"📋 [{self.name}] {slug} — 抓取元数据...")
            meta = {}
            try:
                meta = await retry_async(lambda: self.fetch_meta(sb, slug))
            except Exception as e:
                log.warning(f"  ⚠️ 元数据抓取失败: {e}")

            chapters = await retry_async(lambda: self.fetch_chapters(sb, slug))
            log.info(f"  共 {len(chapters)} 章")
            return chapters, meta

    async def _run_serial(self, sb, indexed, manga_dir, ch_records):
        return await self._run_serial_on_page(sb, indexed, manga_dir, ch_records)

    async def _run_serial_on_page(self, page, indexed, manga_dir, ch_records):
        new_total = 0
        empty_count = 0
        for gidx, ch in indexed:
            try:
                result = await self._process_chapter(page, ch, gidx, manga_dir, show_bar=True)
                if result is None:
                    empty_count += 1
                    if empty_count >= BLOCK_THRESHOLD:
                        raise _StealthBlocked(empty_count)
                elif result:
                    dl, rec = result
                    ch_records.append(rec)
                    new_total += dl
                    empty_count = 0
            except _StealthBlocked:
                raise
            except Exception:
                pass
        return ch_records, new_total

    async def _run_parallel(self, pool: StealthPagePool, indexed, manga_dir, ch_records):
        sem = asyncio.Semaphore(pool.pool_size)
        empty_count = [0]  # mutable int
        lock = asyncio.Lock()
        new_total = 0

        async def _worker(gidx, ch):
            nonlocal new_total
            async with sem:
                page = await pool.acquire()
                try:
                    result = await self._process_chapter(page, ch, gidx, manga_dir, show_bar=False)
                    if result is None:
                        async with lock:
                            empty_count[0] += 1
                            if empty_count[0] >= BLOCK_THRESHOLD:
                                raise _StealthBlocked(empty_count[0])
                    elif result:
                        dl, rec = result
                        async with lock:
                            ch_records.append(rec)
                            nonlocal new_total
                            new_total += dl
                            empty_count[0] = 0
                finally:
                    await pool.release(page)

        coros = [_worker(gidx, ch) for gidx, ch in indexed]
        try:
            await asyncio.gather(*coros)
        except _StealthBlocked:
            raise

        return ch_records, new_total

    async def _process_chapter(self, page, ch, gidx, manga_dir, show_bar=True):
        title = ch["title"]
        ch_dir = manga_dir / f"{gidx + 1:03d}_{safe_name(title)}"
        cmeta_path = ch_dir / "meta.json"

        # 断点续传
        if cmeta_path.exists():
            try:
                cm = json.loads(cmeta_path.read_text())
                if cm.get("downloaded", 0) >= cm.get("pages", 1) > 0:
                    log.info(f"⏭  [{gidx + 1}] {title} (已完成 {cm['downloaded']}p)")
                    return cm["downloaded"], {
                        "dir": ch_dir.name, "title": title,
                        "index": gidx + 1, "pages": cm["pages"],
                    }
            except Exception:
                pass

        # 导航冷却
        if not self.no_pace:
            await asyncio.sleep(random.uniform(1.0, 3.0))

        log.info(f"📖 [{gidx + 1}] {title}")

        # 获取页面 URL 列表
        try:
            pages = await retry_async(
                lambda: self._fetch_pages_with_fallback(page, ch)
            )
        except Exception as e:
            log.error(f"  ❌ 解析失败: {e}")
            return None

        if not pages:
            log.warning(f"  ⚠️ 无页面 (可能被反爬)")
            return None

        dl = await self.download_pages(pages, ch_dir, show_bar=show_bar)
        log.info(f"  ✅ {dl}/{len(pages)} 页")
        cmeta_path.write_text(
            json.dumps({
                "pages": len(pages), "downloaded": dl,
                "title": title, "index": gidx + 1,
            }, ensure_ascii=False)
        )
        return dl, {
            "dir": ch_dir.name, "title": title,
            "index": gidx + 1, "pages": len(pages),
        }

    def _write_manga_meta(self, manga_dir, slug, meta, cover_name, ch_records):
        path = manga_dir / "manga.json"
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                pass

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
        log.info(f"  📝 元数据 → manga.json ({len(chapters)} 章)")


# ─────────────────────────── MangaCopyCrawler ───────────────────────────

class MangaCopyCrawler(BaseCrawler):
    name = "mangacopy"
    base_url = BASE_URL

    @staticmethod
    def _decrypt(cct: str, content_key: str) -> list:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        iv = content_key[:16].encode()
        ct = bytes.fromhex(content_key[16:])
        cipher = AES.new(cct.encode(), AES.MODE_CBC, iv=iv)
        return json.loads(unpad(cipher.decrypt(ct), AES.block_size))

    # ── fetch_meta / fetch_chapters (同 v6，支持 page 参数) ──
    async def fetch_meta(self, page, slug: str) -> dict:
        await self._goto(page, f"{self.base_url}/comic/{slug}")
        cover = await self._eval(page,
            "document.querySelector('meta[property=\"og:image\"]')?.content || "
            "document.querySelector('.comicParticulars-left-img img')?.src || ''")
        title = await self._eval(page,
            "document.querySelector('h6.comicParticulars-title-right')?.innerText || "
            "document.querySelector('meta[property=\"og:novel:book_name\"]')?.content || "
            "document.querySelector('title')?.innerText || ''")
        author = await self._eval(page,
            "Array.from(document.querySelectorAll('.comicParticulars-right-txt a'))"
            ".map(a=>a.innerText).join(', ') || "
            "document.querySelector('meta[property=\"og:novel:author\"]')?.content || ''")
        desc = await self._eval(page,
            "document.querySelector('.intro-total')?.innerText || "
            "document.querySelector('meta[name=\"description\"]')?.content || ''")
        tags = await self._eval(page,
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

    async def fetch_chapters(self, page, slug: str) -> list:
        if not await self._eval(page, "location.href.includes('/comic/')"):
            await self._goto(page, f"{self.base_url}/comic/{slug}")
        links = await self._extract(page, 'a[href*="/chapter/"]', attr="href")
        texts = await self._extract(page, 'a[href*="/chapter/"]')
        chapters, seen = [], set()
        for href, text in zip(links, texts):
            if not href or not text or "/chapter/" not in href:
                continue
            uid = href.split("/chapter/")[-1]
            if uid in seen or text.strip() in ("開始閱讀", "开始阅读"):
                continue
            seen.add(uid)
            chapters.append({
                "title": text.strip(),
                "url": urljoin(self.base_url, href),
                "uid": uid,
            })
        return chapters

    async def fetch_pages(self, page, chapter: dict, strategy: str = "aes") -> list:
        if strategy == "intercept":
            return await self._fetch_pages_intercept(page, chapter)
        else:
            return await self._fetch_pages_aes(page, chapter)

    async def _fetch_pages_aes(self, page, chapter: dict) -> list:
        await self._goto(page, chapter["url"])
        cct = await self._eval(page, "window.cct || ''")
        ck = await self._eval(page, "window.contentKey || ''")
        if not ck:
            raise RuntimeError("contentKey 为空")
        pages = self._decrypt(cct, ck)
        return [p.get("url", "") for p in pages]

    async def _fetch_pages_intercept(self, page, chapter: dict) -> list:
        """intercept 策略：拦截网络请求捕获图片 URL，滚动触发懒加载"""
        img_urls: list[str] = []

        async def _on_response(response):
            if not response.ok:
                return
            ct = response.headers.get("content-type", "")
            if "image" not in ct:
                return
            url = response.url
            if "mangafunb" not in url:
                return
            if any(x in url.lower() for x in ("loading", "ads", "icon", "logo", "favicon")):
                return
            if url not in img_urls:
                img_urls.append(url)

        page.on("response", _on_response)
        await self._goto(page, chapter["url"])

        # 获取期望页数
        try:
            expected = int(await self._eval(page,
                "document.querySelector('.comicCount')?.textContent || '0'"))
        except (ValueError, TypeError):
            expected = 0

        # 滚动加载
        stalled = 0
        prev = 0
        while stalled < 5 and len(img_urls) < 500:
            await self._eval(page, "window.scrollTo(0, document.body.scrollHeight + 2000)")
            await asyncio.sleep(2)
            if expected > 0 and len(img_urls) >= expected:
                break
            if len(img_urls) == prev:
                stalled += 1
            else:
                stalled = 0
            prev = len(img_urls)

        if expected > 0 and len(img_urls) < expected:
            log.warning(f"  ⚠️  intercept 只捕获 {len(img_urls)}/{expected} 页")
        return img_urls

    # ── 页面操作适配层 (兼容 StealthBrowser 和原生 Playwright Page) ──
    @staticmethod
    async def _goto(page, url: str):
        if hasattr(page, 'fetch'):
            await page.fetch(url)
        elif hasattr(page, 'goto'):
            await page.goto(url, wait_until="networkidle", timeout=30000)
        else:
            raise RuntimeError("Unknown page type")

    @staticmethod
    async def _eval(page, js: str):
        if hasattr(page, 'eval'):
            return await page.eval(js)
        elif hasattr(page, 'evaluate'):
            return await page.evaluate(js)
        else:
            raise RuntimeError("Unknown page type")

    @staticmethod
    async def _extract(page, selector: str, attr: str = "innerText"):
        if hasattr(page, 'extract'):
            return await page.extract(selector, attr=attr)
        elif hasattr(page, 'query_selector_all'):
            els = await page.query_selector_all(selector)
            results = []
            for el in els:
                if attr == "innerText":
                    results.append((await el.inner_text()).strip())
                else:
                    results.append(await el.get_attribute(attr))
            return results
        else:
            raise RuntimeError("Unknown page type")


# ─────────────────────────── CLI ───────────────────────────

SOURCES = {"mangacopy": MangaCopyCrawler}


def main():
    ap = argparse.ArgumentParser(description="ComicHub 漫画爬虫 v7")
    ap.add_argument("slug", help="漫画 slug")
    ap.add_argument("start", nargs="?", type=int, default=0, help="起始章节索引")
    ap.add_argument("limit", nargs="?", type=int, default=0, help="爬取数量 (0=全部)")
    ap.add_argument("--source", default="mangacopy", choices=list(SOURCES))
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发下载线程数")
    ap.add_argument("--tabs", type=int, default=DEFAULT_TABS, help="并行标签页数 (1=串行)")
    ap.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="重试次数")
    ap.add_argument("--strategy", default="aes", choices=["aes", "intercept"],
                    help="页面获取策略 (aes=解密, intercept=拦截)")
    ap.add_argument("--cookie-file", default=None, help="Cookie 文件路径")
    ap.add_argument("--no-proxy", action="store_true")
    ap.add_argument("--no-pace", action="store_true", help="关闭请求节奏控制")
    ap.add_argument("--no-download", action="store_true", help="不下载图片到本地")
    ap.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    args = ap.parse_args()

    setup_logging(args.verbose)

    crawler = SOURCES[args.source](
        workers=args.workers,
        proxy=None if args.no_proxy else "http://127.0.0.1:7897",
        retries=args.retries,
        strategy=args.strategy,
        cookie_file=args.cookie_file,
        no_pace=args.no_pace,
        no_download=args.no_download,
    )
    asyncio.run(crawler.run(args.slug, args.start, args.limit, tabs=args.tabs))


if __name__ == "__main__":
    main()
