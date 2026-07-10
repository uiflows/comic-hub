#!/usr/bin/env python3
"""探路 v5: 拦截解码，捕获所有图片 URL。用 networkidle 等 JS 执行完"""

import os, json, re, time
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/Volumes/SSD/playwright/browsers'
from playwright.sync_api import sync_playwright

URL = "https://www.mangacopy.com/comic/diyuanzuigao/chapter/4fc803ae-0abd-11ef-8563-3f487b7d9a9a"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy={'server': 'http://127.0.0.1:7897'})
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        
        # Intercept all image requests
        img_urls = []
        def log_img(response):
            if response.ok and 'image' in response.headers.get('content-type', ''):
                url = response.url
                if 'mangafunb' in url and 'loading' not in url and 'ads' not in url and 'icon' not in url:
                    img_urls.append(url)
        page.on('response', log_img)
        
        print("加载页面 (networkidle)...")
        page.goto(URL, timeout=60000, wait_until='networkidle')
        page.wait_for_timeout(5000)
        
        # Check page state
        idx = page.evaluate("document.querySelector('.comicIndex')?.textContent")
        total = page.evaluate("document.querySelector('.comicCount')?.textContent")
        print(f"页面: {idx}/{total}")
        
        # Try to force load all pages by continuously scrolling and waiting
        print("\n持续滚动加载...")
        prev_count = 0
        stalled = 0
        
        while stalled < 5:
            # Scroll down
            page.evaluate('window.scrollTo(0, document.body.scrollHeight + 2000)')
            time.sleep(2)
            
            current_count = len(img_urls)
            new_idx = page.evaluate("document.querySelector('.comicIndex')?.textContent")
            new_total = page.evaluate("document.querySelector('.comicCount')?.textContent")
            
            print(f"  图片: {current_count}, 页码: {new_idx}/{new_total}")
            
            if current_count == prev_count:
                stalled += 1
            else:
                stalled = 0
                prev_count = current_count
        
        print(f"\n结果: 共捕获 {len(img_urls)} 张图片 URL")
        for i, u in enumerate(img_urls):
            print(f"  [{i+1}] {u[:120]}")
        
        browser.close()

if __name__ == '__main__':
    main()
