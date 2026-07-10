#!/usr/bin/env python3
"""探路 v4: 研究翻页机制，尝试触发加载所有页面"""

import os, json, time
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/Volumes/SSD/playwright/browsers'
from playwright.sync_api import sync_playwright

URL = "https://www.mangacopy.com/comic/diyuanzuigao/chapter/4fc803ae-0abd-11ef-8563-3f487b7d9a9a"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy={'server': 'http://127.0.0.1:7897'})
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        
        # Intercept ALL requests to find the API that fetches individual page images
        api_urls = []
        def log_req(request):
            if any(x in request.url for x in ['mangafunb', '/api/', 'chapter', 'comicdetail']):
                api_urls.append(request.url[:150])
        page.on('request', log_req)
        
        page.goto(URL, timeout=30000, wait_until='domcontentloaded')
        page.wait_for_timeout(5000)
        
        # Check page counter after load
        idx = page.evaluate("document.querySelector('.comicIndex')?.textContent")
        count = page.evaluate("document.querySelector('.comicCount')?.textContent")
        print(f"页面计数: {idx} / {count}")
        
        # Strategy 1: Scroll to bottom very gradually
        print("\n策略1: 逐像素滚动到底部...")
        height = page.evaluate("document.body.scrollHeight")
        print(f"  页面总高度: {height}px")
        
        # Scroll in steps
        for step in range(15):
            scroll_to = min((step + 1) * height // 10, height)
            page.evaluate(f"window.scrollTo(0, {scroll_to})")
            page.wait_for_timeout(1500)
            img_count = page.evaluate("document.querySelectorAll('.comicContent-list img').length")
            idx2 = page.evaluate("document.querySelector('.comicIndex')?.textContent")
            count2 = page.evaluate("document.querySelector('.comicCount')?.textContent")
            print(f"  步骤{step+1}: scrollTo({scroll_to}), imgs={img_count}, page={idx2}/{count2}")
        
        # Strategy 2: Click on page to advance (some readers advance on click)
        print("\n策略2: 点击页面中间...")
        page.click('.comicContent', timeout=3000)
        page.wait_for_timeout(2000)
        img_count = page.evaluate("document.querySelectorAll('.comicContent-list img').length")
        print(f"  图片数: {img_count}")
        
        # Strategy 3: Press right arrow / PageDown
        print("\n策略3: 按键盘 PageDown/ArrowDown...")
        for key in ['PageDown', 'ArrowDown', 'ArrowRight', 'Space']:
            page.keyboard.press(key)
            page.wait_for_timeout(1000)
            img_count = page.evaluate("document.querySelectorAll('.comicContent-list img').length")
            idx3 = page.evaluate("document.querySelector('.comicIndex')?.textContent")
            print(f"  {key}: imgs={img_count}, page={idx3}")
        
        # Strategy 4: Directly call page loading function if exposed
        print("\n策略4: 查找 JS 翻页函数...")
        js_result = page.evaluate("""
            () => {
                const r = {};
                // Look for any global functions related to page navigation
                for (let key of Object.keys(window)) {
                    if (typeof window[key] === 'function') {
                        const fnStr = window[key].toString();
                        if (fnStr.includes('comicIndex') || fnStr.includes('comicCount') || 
                            fnStr.includes('loadPage') || fnStr.includes('nextPage') ||
                            fnStr.includes('pageChange')) {
                            r[key] = fnStr.substring(0, 200);
                        }
                    }
                }
                return JSON.stringify(r);
            }
        """)
        print(f"  {js_result}")
        
        # Strategy 5: Use mouse wheel
        print("\n策略5: 鼠标滚轮...")
        for _ in range(20):
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(500)
        img_count = page.evaluate("document.querySelectorAll('.comicContent-list img').length")
        print(f"  滚轮后: {img_count}")
        
        # Strategy 6: Look at network requests for page loading
        print(f"\n策略6: 网络请求分析 (共 {len(api_urls)} 个):")
        for u in api_urls:
            print(f"  {u}")
        
        # Final state
        page.wait_for_timeout(2000)
        imgs = page.evaluate("""
            Array.from(document.querySelectorAll('.comicContent-list img')).map(i => i.src?.substring(0, 150))
        """)
        print(f"\n最终: {len(imgs)} 张图片")
        for i in imgs:
            print(f"  {i}")
        
        browser.close()

if __name__ == '__main__':
    main()
