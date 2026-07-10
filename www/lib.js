/* ComicHub 共享库 — DOM 助手 / 数据访问 / 进度 / 主题
 * 纯原生 JS，零依赖。被 index.html 和 local.html 共用。 */
(function (global) {
  'use strict';

  const DATA = '/data';
  const IMG_RE = /\.(jpg|jpeg|png|webp|gif|avif)$/i;

  // ───────── DOM 助手 ─────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'className') el.className = v;
      else if (k === 'html') el.innerHTML = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      el.append(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    }
    return el;
  }

  // ───────── 数据访问 ─────────
  // 解析 nginx autoindex HTML，返回 [{name, display, isDir, size}]
  function parseIndex(html) {
    const items = [];
    const re = /<a href="([^"]+)">([^<]+)<\/a>\s+(\d{2}-[A-Za-z]{3}-\d{4}\s+[\d:]+|-)\s+(\S+)/g;
    let m;
    while ((m = re.exec(html))) {
      const raw = m[1];
      const name = decodeURIComponent(raw).replace(/\/$/, '');
      if (name === '..' || raw === '../') continue;
      items.push({ name, display: m[2].replace(/\/$/, ''), isDir: raw.endsWith('/'), size: m[4] });
    }
    return items;
  }

  async function listDir(path) {
    const r = await fetch(`${DATA}/${path}`.replace(/\/+$/, '') + '/');
    if (!r.ok) throw new Error(r.status);
    return parseIndex(await r.text());
  }

  // 数字前缀排序 (回退用)
  function natSort(a, b) {
    const na = parseInt(a) || 0, nb = parseInt(b) || 0;
    return na - nb || a.localeCompare(b, 'zh');
  }

  // 列出书架所有漫画 (带 manga.json 元数据；缺失时回退 autoindex)
  async function getMangaList() {
    let dirs;
    try { dirs = (await listDir('')).filter(i => i.isDir); }
    catch { return []; }
    return Promise.all(dirs.map(async d => {
      const meta = await getMangaMeta(d.name);
      return meta || { slug: d.name, title: d.name, chapters: null, cover: null, _fallback: true };
    }));
  }

  // 读取单本漫画的 manga.json；失败返回 null
  async function getMangaMeta(slug) {
    try {
      const r = await fetch(`${DATA}/${slug}/manga.json`);
      if (!r.ok) return null;
      const m = await r.json();
      m.slug = slug;
      if (m.cover) m.coverUrl = `${DATA}/${slug}/${m.cover}`;
      return m;
    } catch { return null; }
  }

  // 获取章节列表：优先 manga.json，回退 autoindex
  async function getChapters(slug) {
    const meta = await getMangaMeta(slug);
    if (meta && meta.chapters && meta.chapters.length) {
      return meta.chapters.map(c => ({ dir: c.dir, title: c.title, pages: c.pages, index: c.index }));
    }
    try {
      const dirs = (await listDir(slug)).filter(i => i.isDir);
      dirs.sort((a, b) => natSort(a.name, b.name));
      return dirs.map((d, i) => ({ dir: d.name, title: d.display.replace(/^\d+_/, ''), index: i + 1 }));
    } catch { return []; }
  }

  // 章节内图片 URL 列表
  async function getPages(slug, chDir) {
    try {
      const imgs = (await listDir(`${slug}/${chDir}`)).filter(i => !i.isDir && IMG_RE.test(i.name));
      imgs.sort((a, b) => natSort(a.name, b.name));
      return imgs.map(i => `${DATA}/${slug}/${chDir}/${i.name}`);
    } catch { return []; }
  }

  // ───────── 阅读进度 (localStorage) ─────────
  const PKEY = 'comichub.progress.v1';
  function loadProgress() {
    try { return JSON.parse(localStorage.getItem(PKEY) || '{}'); } catch { return {}; }
  }
  function getProgress(slug) { return loadProgress()[slug] || null; }
  function saveProgress(slug, data) {
    const all = loadProgress();
    all[slug] = { ...all[slug], ...data, at: Date.now() };
    try { localStorage.setItem(PKEY, JSON.stringify(all)); } catch {}
  }
  // 最近阅读 (按时间倒序)
  function recentReads() {
    const all = loadProgress();
    return Object.entries(all)
      .map(([slug, p]) => ({ slug, ...p }))
      .sort((a, b) => (b.at || 0) - (a.at || 0));
  }

  // ───────── 主题 ─────────
  const TKEY = 'comichub.theme';
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
  }
  function initTheme() {
    const saved = localStorage.getItem(TKEY);
    const t = saved || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    applyTheme(t);
    return t;
  }
  function toggleTheme() {
    const cur = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
    const next = cur === 'light' ? 'dark' : 'light';
    applyTheme(next);
    localStorage.setItem(TKEY, next);
    return next;
  }

  function timeAgo(ts) {
    if (!ts) return '';
    const s = (Date.now() - ts) / 1000;
    if (s < 60) return '刚刚';
    if (s < 3600) return `${Math.floor(s / 60)} 分钟前`;
    if (s < 86400) return `${Math.floor(s / 3600)} 小时前`;
    if (s < 2592000) return `${Math.floor(s / 86400)} 天前`;
    return new Date(ts).toLocaleDateString('zh-CN');
  }

  global.CH = {
    DATA, $, $$, h, parseIndex, listDir,
    getMangaList, getMangaMeta, getChapters, getPages,
    getProgress, saveProgress, recentReads,
    initTheme, toggleTheme, timeAgo,
  };
})(window);
