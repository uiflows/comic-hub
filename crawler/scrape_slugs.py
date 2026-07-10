#!/Volumes/SSD/Hermes/Hermes总工作台/项目/comic-crawler/venv/bin/python3
"""Fast batch slug scraper for mangacopy category pages."""
import asyncio, json, sys, os
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/.local/bin"))
from pw_tool import StealthBrowser

BASE = "https://www.mangacopy.com"
DATA_DIR = Path(os.path.expanduser("~/sites/comic-hub/data"))
existing = set(os.listdir(DATA_DIR)) if DATA_DIR.exists() else set()

CATEGORIES = [
    "aiqing", "huanlexiang", "maoxian", "qihuan", "baihe",
    "xiaoyuan", "kehuan", "dongfang", "danmei", "shenghuo",
    "gedou", "qingxiaoshuo", "qita", "xuanyi", "TL",
    "mengxi", "shengui", "zhichang", "zhiyu", "jiecao",
    "sige", "changtiao", "jianniang", "gaoxiao", "jingji",
    "weiniang", "mohuan", "rexie", "xingzhuanhuan", "meishi",
    "lizhi", "caise", "hougong", "zhentan", "jingsong",
    "yinyuewudao", "yishijie", "zhanzheng", "lishi", "jizhan",
    "dushi", "chuanyue", "chongsheng", "kongbu", "shengcun",
    "wuxia", "zhaixi", "zhuansheng",
]

async def scrape_category(category: str, pages: int = 10):
    """Scrape slugs from a category, across multiple pages."""
    all_slugs = set()
    try:
        async with StealthBrowser(
            cookie_file=Path(os.path.expanduser("~/sites/comic-hub/crawler/.cookies/mangacopy.json"))
        ) as sb:
            for page in range(1, pages + 1):
                url = f"{BASE}/comics?theme={category}&page={page}"
                try:
                    html = await sb.fetch(url)
                    # Extract /comic/{slug} patterns
                    import re
                    slugs = re.findall(r'/comic/([a-zA-Z0-9_-]+)', html)
                    new_count = 0
                    for s in slugs:
                        if s not in existing and s not in all_slugs:
                            all_slugs.add(s)
                            new_count += 1
                    if new_count == 0 and page > 1:
                        break  # no new slugs, stop paginating this category
                except Exception as e:
                    print(f"  Page {page} error: {e}", file=sys.stderr)
                    break
    except Exception as e:
        print(f"Category {category} failed: {e}", file=sys.stderr)
    
    return all_slugs

async def main():
    all_new = set()
    for cat in CATEGORIES:
        slugs = await scrape_category(cat, pages=5)
        new = slugs - existing
        all_new |= new
        print(f"{cat}: {len(new)} new (total collected: {len(all_new)})", flush=True)
        if len(all_new) >= 500:
            break
    
    print(json.dumps(sorted(all_new), ensure_ascii=False))

asyncio.run(main())
