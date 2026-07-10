#!/usr/bin/env python3
"""第二步：打开章节页面，抓取图片加载网络请求"""

import os, json
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/Volumes/SSD/playwright/browsers'
from playwright.sync_api import sync_playwright

CHAPTER_URL = "https://www.mangacopy.com/comic/diyuanzuigao/chapter/4fc803ae-0abd-11ef-8563-3f487b7d9a9a"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy={'server': 'http://127.0.0.1:7897'},
            args=['--no-sandbox']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            viewport={'width': 1440, 'height': 900}
        )
        page = context.new_page()
        
        api_calls = []
        img_urls = []
        
        def log_request(request):
            url = request.url
            if '/api/' in url or 'chapter' in url.lower():
                api_calls.append({'url': url, 'method': request.method})
            # Track image requests
            if any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.avif']):
                img_urls.append(url)
        
        def log_response(response):
            url = response.url
            for req in api_calls:
                if req['url'] == url:
                    try:
                        body = response.text()
                        req['status'] = response.status
                        req['body'] = body[:500]
                    except:
                        req['status'] = response.status
        
        page.on('request', log_request)
        page.on('response', log_response)
        
        print(f"Opening chapter: {CHAPTER_URL}")
        try:
            page.goto(CHAPTER_URL, timeout=30000, wait_until='networkidle')
        except Exception as e:
            print(f"  Load issue: {e}")
        
        page.wait_for_timeout(3000)
        
        print(f"Title: {page.title()}")
        
        # Check for images on page
        imgs = page.query_selector_all('img')
        print(f"\nIMG tags on page: {len(imgs)}")
        for i, img in enumerate(imgs[:5]):
            src = img.get_attribute('src') or img.get_attribute('data-src') or ''
            print(f"  [{i}] {src[:120]}")
        
        print(f"\nAPI calls:")
        for req in api_calls:
            print(f"  {req['method']} {req['url']}")
            if 'body' in req:
                print(f"    body preview: {req['body'][:200]}")
        
        print(f"\nImage URLs from network ({len(img_urls)}):")
        for u in img_urls[:10]:
            print(f"  {u[:150]}")
        
        browser.close()

if __name__ == '__main__':
    main()
