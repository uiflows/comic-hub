#!/usr/bin/env python3
"""探路 v3: 在浏览器中执行 JS，提取解密后的章节数据"""

import os, json
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/Volumes/SSD/playwright/browsers'
from playwright.sync_api import sync_playwright

URL = "https://www.mangacopy.com/comic/diyuanzuigao/chapter/4fc803ae-0abd-11ef-8563-3f487b7d9a9a"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy={'server': 'http://127.0.0.1:7897'})
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        
        print("1. 加载页面...")
        page.goto(URL, timeout=30000, wait_until='domcontentloaded')
        
        # Wait for JS to execute and decrypt
        page.wait_for_timeout(5000)
        
        # Try to extract decrypted data from various sources
        print("\n2. 提取解密数据...")
        
        # Check if there's a global variable with decrypted URLs
        result = page.evaluate("""
            () => {
                const results = {};
                
                // Check for image data in various possible locations
                results.comicContentList = document.querySelector('.comicContent-list')?.innerHTML?.substring(0, 500) || '(empty)';
                
                // Check all img tags
                const imgs = document.querySelectorAll('.comicContent-list img');
                results.imgCount = imgs.length;
                results.imgSrcs = Array.from(imgs).map(i => i.src || i.getAttribute('data-src')).slice(0, 5);
                
                // Check data attributes
                const container = document.querySelector('.comicContent');
                results.containerDataAttrs = container ? Object.keys(container.dataset).join(',') : 'no container';
                
                // Check all <script> tags for embedded data
                const scripts = document.querySelectorAll('script:not([src])');
                results.inlineScripts = [];
                scripts.forEach(s => {
                    const text = s.textContent;
                    if (text.includes('contentKey') || text.includes('imageData') || text.includes('imgUrl')) {
                        results.inlineScripts.push(text.substring(0, 200));
                    }
                });
                
                // Check imageData div
                const imgData = document.querySelector('.imageData');
                results.imageData = imgData?.innerHTML?.substring(0, 500) || '(empty)';
                
                // Check localStorage
                results.localStorageKeys = Object.keys(localStorage).filter(k => 
                    k.includes('manga') || k.includes('comic') || k.includes('chapter')
                );
                
                // Check sessionStorage
                results.sessionStorageKeys = Object.keys(sessionStorage).filter(k => 
                    k.includes('manga') || k.includes('comic') || k.includes('chapter')
                );
                
                // Check window properties
                results.windowKeys = Object.keys(window).filter(k => 
                    k.includes('manga') || k.includes('comic') || k.includes('chapter') || k.includes('img')
                );
                
                // Check if CryptoJS is available
                results.hasCryptoJS = typeof CryptoJS !== 'undefined';
                
                return JSON.stringify(results, null, 2);
            }
        """)
        print(result)
        
        # Now scroll slowly to trigger lazy loading
        print("\n3. 滚动加载更多图片...")
        for i in range(10):
            page.evaluate('window.scrollBy(0, window.innerHeight * 2)')
            page.wait_for_timeout(2000)
            
            img_count = page.evaluate('document.querySelectorAll(".comicContent-list img").length')
            print(f"  滚动 {i+1}: {img_count} 张图片")
        
        # Final image list
        final_imgs = page.evaluate("""
            () => {
                const imgs = document.querySelectorAll('.comicContent-list img');
                return Array.from(imgs).map(i => ({
                    src: i.src?.substring(0, 150),
                    naturalWidth: i.naturalWidth,
                    naturalHeight: i.naturalHeight
                }));
            }
        """)
        print(f"\n4. 最终图片列表 ({len(json.loads(final_imgs))} 张):")
        for img in json.loads(final_imgs):
            if 'mangafunb' in img.get('src', ''):
                print(f"  ✅ {img['src']}")
            else:
                print(f"  ⬜ {img.get('src', '')}")
        
        browser.close()

if __name__ == '__main__':
    main()
