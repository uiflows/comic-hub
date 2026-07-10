#!/usr/bin/env python3
"""Test: Playwright + stealth"""
import os
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/Volumes/SSD/playwright/browsers'
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

URL = "https://www.mangacopy.com/comic/diyuanzuigao/chapter/4fc803ae-0abd-11ef-8563-3f487b7d9a9a"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        proxy={'server': 'http://127.0.0.1:7897'},
        args=['--no-sandbox']
    )
    context = browser.new_context(
        viewport={'width': 1440, 'height': 900},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        locale='zh-CN'
    )
    page = context.new_page()
    
    stealth = Stealth()
    stealth.apply_stealth_sync(page)
    
    page.goto(URL, timeout=30000, wait_until='networkidle')
    page.wait_for_timeout(3000)
    
    cct = page.evaluate("window.cct || ''")
    ck = page.evaluate("window.contentKey || ''")
    title = page.title()
    imgs = page.query_selector_all('.comicContent-list img')
    
    print(f"Title: {title}")
    print(f"cct: {cct}")
    print(f"contentKey: {ck[:50] if ck else '(empty)'} (len={len(ck)})")
    print(f"Images: {len(imgs)}")
    for img in imgs:
        src = img.get_attribute('src') or ''
        print(f"  {src[:120]}")
    
    browser.close()
