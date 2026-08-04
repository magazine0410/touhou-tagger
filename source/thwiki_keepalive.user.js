// ==UserScript==
// @name         THBWiki cookie keep-alive
// @namespace    touhou-tagger
// @version      0.1.0
// @description  Keeps the THBWiki SafeLine/Cloudflare session cookie fresh by silently pinging the main page on a randomized interval, so Touhou Tagger's cookie stays valid for longer without re-solving the human-verification challenge. Never reloads the visible tab.
// @match        *://thwiki.cc/*
// @match        *://*.thwiki.cc/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    // --- Configuration ----------------------------------------------------
    // The page that gets pinged. Deliberately ONLY the site root — album pages
    // are left completely untouched so active slug-hunting browsing is never
    // disturbed (this is a background fetch, not a tab reload, either way).
    const PING_URL = 'https://thwiki.cc/';

    // Randomized spacing between pings, in milliseconds. A jittered interval
    // is harder to flag as automated than a fixed cadence.
    const MIN_MS = 60 * 1000;   // 60s
    const MAX_MS = 120 * 1000;  // 120s

    // How often each tab wakes up to check whether a ping is due. Cheap; the
    // actual ping cadence is governed by the shared schedule below, not this.
    const CHECK_MS = 5 * 1000;

    // localStorage keys used to coordinate across multiple open THBWiki tabs,
    // so N tabs still produce only ~one ping per interval (not N pings).
    const K_NEXT  = 'thwiki_keepalive_next';   // epoch ms of the next due ping
    const K_OWNER = 'thwiki_keepalive_owner';  // claim token of the winning tab

    const TAB_ID = Math.random().toString(36).slice(2);
    const rand = (lo, hi) => lo + Math.floor(Math.random() * (hi - lo));
    const log = (...a) => console.log('[thwiki-keepalive]', ...a);

    // --- Scheduling -------------------------------------------------------
    function scheduleNext(fromNow) {
        const next = Date.now() + (fromNow != null ? fromNow : rand(MIN_MS, MAX_MS));
        localStorage.setItem(K_NEXT, String(next));
        return next;
    }

    // First tab to load seeds the schedule; later tabs inherit it.
    if (!localStorage.getItem(K_NEXT)) {
        scheduleNext(rand(MIN_MS, MAX_MS));
        log('seeded schedule; first ping in ~%ds', Math.round((Number(localStorage.getItem(K_NEXT)) - Date.now()) / 1000));
    }

    async function ping() {
        const url = PING_URL + '?_=' + Date.now();   // cache-bust so SafeLine sees a real request
        try {
            const r = await fetch(url, { credentials: 'include', cache: 'no-store', redirect: 'follow' });
            log('ping ok', r.status, new Date().toLocaleTimeString());
        } catch (e) {
            log('ping failed:', e && e.message);
        }
    }

    // --- Cross-tab claim --------------------------------------------------
    // Each tab checks every CHECK_MS. When the shared "next" time has passed,
    // tabs race to claim it: write our token, then re-read after a tiny delay;
    // only the tab whose token survives actually pings. A rare double-ping is
    // harmless, so the guard is intentionally lightweight rather than a lock.
    async function tick() {
        const next = Number(localStorage.getItem(K_NEXT) || 0);
        if (Date.now() < next) return;

        const token = TAB_ID + ':' + Date.now() + ':' + Math.random();
        localStorage.setItem(K_OWNER, token);
        await new Promise(res => setTimeout(res, 50 + Math.random() * 100));
        if (localStorage.getItem(K_OWNER) !== token) return;  // another tab won

        scheduleNext();   // reserve the next slot before pinging, so others stand down
        await ping();
    }

    setInterval(() => { tick(); }, CHECK_MS);
    log('active in this tab (id %s); pinging %s every %d–%ds', TAB_ID, PING_URL, MIN_MS / 1000, MAX_MS / 1000);
})();
