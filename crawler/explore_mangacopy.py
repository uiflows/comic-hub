#!/usr/bin/env python3
"""探路脚本：用 Playwright 打开 mangacopy 漫画页，抓取网络请求"""

import os
import json
import sys

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/Volumes/SSD/playwright/browsers'

from playwright.sync_api import sync_playwright

COMIC_URL = "https://www.mangacopy.com/comic/diyuanzuigao"
# 大陆无障碍地址
# COMIC_URL = "https://www.copy3000.com/comic/diyuanzuigao"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy={'server': 'http://127.0.0.1:7897'},
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1440, 'height': 900},
            locale='zh-CN'
        )
        page = context.new_page()
        
        # Collect XHR/Fetch requests
        api_requests = []
        def log_request(request):
            url = request.url
            if '/api/' in url or 'comicId' in url or 'chapter' in url.lower():
                api_requests.append({
                    'url': url,
                    'method': request.method,
                    'headers': dict(request.headers),
                })
        
        def log_response(response):
            url = response.url
            if '/api/' in url or 'comicId' in url or 'chapter' in url.lower():
                # Find matching request and add status
                for req in api_requests:
                    if req['url'] == url:
                        try:
                            body = response.text()
                            if len(body) < 3000:
                                req['response'] = body[:2000]
                            else:
                                req['response'] = body[:200] + f'... ({len(body)} bytes)'
                        except:
                            req['response'] = f'status={response.status} (binary)'
                        break
        
        page.on('request', log_request)
        page.on('response', log_response)
        
        print(f"[1] Navigating to {COMIC_URL}...")
        try:
            page.goto(COMIC_URL, timeout=30000, wait_until='networkidle')
        except Exception as e:
            print(f"  Page load issue: {e}")
        
        page.wait_for_timeout(3000)
        
        title = page.title()
        print(f"  Title: {title}")
        
        # Dump all collected API requests
        print(f"\n[2] API requests found: {len(api_requests)}")
        for i, req in enumerate(api_requests):
            print(f"\n  --- Request #{i+1} ---")
            print(f"  {req['method']} {req['url']}")
            if 'response' in req:
                resp = req['response']
                try:
                    data = json.loads(resp)
                    # Pretty print top-level keys
                    if isinstance(data, dict):
                        print(f"  Response keys: {list(data.keys())}")
                        # Show first result
                        if 'results' in data and data['results']:
                            r = data['results']
                            if isinstance(r, dict) and 'list' in r:
                                print(f"  Results: {len(r['list'])} items, total={r.get('total')}")
                            elif isinstance(r, list):
                                print(f"  Results: {len(r)} items")
                        # Show code
                        if 'code' in data:
                            print(f"  code={data['code']}, message={data.get('message','')}")
                except:
                    print(f"  Response: {resp[:300]}")
        
        # Try to find chapter list elements
        print(f"\n[3] Looking for chapter list...")
        chapters = page.query_selector_all('a[href*="chapter"]')
        if not chapters:
            # Try other selectors
            chapters = page.query_selector_all('a')
            print(f"  Total links on page: {len(chapters)}")
            # Print first 20 links
            for i, a in enumerate(chapters[:20]):
                href = a.get_attribute('href') or ''
                text = a.inner_text().strip()[:50] if a.inner_text() else ''
                if text:
                    print(f"  [{i}] {text} → {href}")
        else:
            print(f"  Found {len(chapters)} chapter links")
            for i, ch in enumerate(chapters[:5]):
                print(f"  [{i}] {ch.inner_text().strip()} → {ch.get_attribute('href')}")
        
        browser.close()

if __name__ == '__main__':
    main()
