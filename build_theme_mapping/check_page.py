from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    r = page.goto("https://www.thpatch.net/wiki/Touhou_Patch_Center:List_of_music_themes/en", wait_until="load", timeout=30000)
    page.wait_for_timeout(5000)
    print(r.status, len(page.content()))
    b.close()
