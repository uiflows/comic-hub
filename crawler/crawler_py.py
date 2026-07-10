#!/usr/bin/env python3
"""
漫画爬虫 v2: 纯 Python 解密 contentKey → 提取图片 URL → 下载
无需 Playwright，直接 HTTP + AES 解密
"""

import os, sys, json, re, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.mangacopy.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
})
session.proxies = {
    'http': 'http://127.0.0.1:7897',
    'https': 'http://127.0.0.1:7897',
}

BASE_URL = "https://www.mangacopy.com"
IMAGE_CDN = "https://sd.mangafunb.fun"
DATA_DIR = Path(os.path.expanduser("~/sites/comic-hub/data"))

def decrypt_content_key(content_key: str, cct: str) -> list:
    """
    解密 contentKey → 图片 URL 列表
    
    content_key: 加密的 hex 字符串
    cct: 密钥字符串 (从页面 var cct = '...' 提取)
    
    返回: [{"url": "https://...", ...}, ...]
    """
    # IV = 前16个字符(UTF-8)
    iv = content_key[:16].encode('utf-8')
    # 密文 = 第17个字符开始，hex decode
    ciphertext_hex = content_key[16:]
    ciphertext = bytes.fromhex(ciphertext_hex)
    # Key = cct (UTF-8)
    key = cct.encode('utf-8')
    # AES-128-CBC, PKCS7 padding
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
    # UTF-8 decode → JSON
    data = json.loads(plaintext.decode('utf-8'))
    return data

def fetch_page(url: str) -> str:
    """获取页面 HTML"""
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text

def extract_vars(html: str) -> dict:
    """从 HTML 提取 cct 和 contentKey"""
    result = {}
    
    # var cct = 'op0zzpvv.nmn.00p';
    m = re.search(r"var cct\s*=\s*'([^']+)'", html)
    if m:
        result['cct'] = m.group(1)
    
    # var contentKey = '...';
    m = re.search(r"var contentKey\s*=\s*'([^']+)'", html)
    if m:
        result['contentKey'] = m.group(1)
    
    # 漫画标题
    m = re.search(r'<title>([^<]+)</title>', html)
    if m:
        result['title'] = m.group(1).strip()
    
    return result

def get_chapter_list(slug: str) -> list:
    """从漫画详情页获取所有章节"""
    url = f"{BASE_URL}/comic/{slug}"
    html = fetch_page(url)
    
    chapters = []
    for m in re.finditer(r'<a\s+href="(/comic/[^/]+/chapter/[^"]+)"[^>]*>(.*?)</a>', html):
        href = m.group(1)
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        chapters.append({
            'title': text,
            'url': urljoin(BASE_URL, href),
            'id': href.split('/chapter/')[-1]
        })
    
    return chapters

def download_image(url: str, save_path: Path) -> bool:
    """下载单张图片"""
    if save_path.exists():
        return True
    
    try:
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    ❌ 下载失败: {e}")
        return False

def crawl_chapter(chapter_url: str, ch_dir: Path) -> int:
    """爬取单个章节，返回下载图片数"""
    print(f"  加载章节页...")
    html = fetch_page(chapter_url)
    vars_ = extract_vars(html)
    
    if not vars_.get('contentKey'):
        print(f"  ⚠️ 未找到 contentKey，跳过")
        return 0
    
    print(f"  cct={vars_['cct']}, key length={len(vars_['contentKey'])}")
    
    # 解密
    try:
        pages = decrypt_content_key(vars_['contentKey'], vars_['cct'])
    except Exception as e:
        print(f"  ❌ 解密失败: {e}")
        return 0
    
    print(f"  解密成功: {len(pages)} 页")
    
    # 下载
    downloaded = 0
    for i, page in enumerate(pages):
        img_url = page.get('url', '')
        if not img_url:
            continue
        
        ext = Path(urlparse(img_url).path).suffix or '.jpg'
        save_path = ch_dir / f"{i+1:03d}{ext}"
        
        print(f"  [{i+1}/{len(pages)}] {img_url[:80]}...", end=' ')
        if download_image(img_url, save_path):
            size = save_path.stat().st_size
            print(f"✅ {size//1024}KB")
            downloaded += 1
        else:
            print("❌")
    
    # 保存元数据
    ch_dir.joinpath('meta.json').write_text(
        json.dumps({'pages': len(pages), 'downloaded': downloaded, 'url': chapter_url},
                   ensure_ascii=False, indent=2)
    )
    
    return downloaded

def crawl_manga(slug: str, start: int = 0, limit: int = 0):
    """爬取整部漫画"""
    print(f"\n{'='*60}")
    print(f"📚 开始爬取: {slug}")
    print(f"{'='*60}")
    
    chapters = get_chapter_list(slug)
    if not chapters:
        print("❌ 未找到章节")
        return
    
    print(f"找到 {len(chapters)} 个章节")
    
    if limit > 0:
        chapters = chapters[start:start + limit]
    elif start > 0:
        chapters = chapters[start:]
    
    manga_dir = DATA_DIR / slug
    total = 0
    
    for i, ch in enumerate(chapters):
        print(f"\n📖 [{i+1}/{len(chapters)}] {ch['title']}")
        
        safe_title = re.sub(r'[^\w\s-]', '', ch['title']).strip()[:40]
        ch_dir = manga_dir / f"{i+1:03d}_{safe_title}"
        ch_dir.mkdir(parents=True, exist_ok=True)
        
        n = crawl_chapter(ch['url'], ch_dir)
        total += n
    
    print(f"\n{'='*60}")
    print(f"✅ 完成！共下载 {total} 张图片 → {manga_dir}")
    print(f"{'='*60}")

def test_decrypt(chapter_url: str):
    """测试解密功能"""
    print(f"测试解密: {chapter_url}")
    html = fetch_page(chapter_url)
    vars_ = extract_vars(html)
    print(f"cct = {vars_.get('cct')}")
    print(f"contentKey length = {len(vars_.get('contentKey', ''))}")
    
    pages = decrypt_content_key(vars_['contentKey'], vars_['cct'])
    print(f"\n解密结果: {len(pages)} 页")
    for i, p in enumerate(pages[:5]):
        print(f"  [{i}] url: {p.get('url', '')[:100]}")
        for k, v in p.items():
            if k != 'url':
                print(f"      {k}: {v}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 crawler_py.py test <章节URL>     # 测试解密")
        print("  python3 crawler_py.py crawl <slug> [start] [limit]  # 爬漫画")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'test':
        test_decrypt(sys.argv[2])
    elif cmd == 'crawl':
        slug = sys.argv[2]
        start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        crawl_manga(slug, start, limit)
