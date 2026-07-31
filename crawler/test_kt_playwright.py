import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "https://membership.kt.com/discount/partner/PartnerList.do"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="ko-KR",
    )
    page = context.new_page()
    try:
        resp = page.goto(url, timeout=20000, wait_until="domcontentloaded")
        print("STATUS:", resp.status if resp else None)
        print("TITLE:", page.title())
        content = page.content()
        print("CONTENT LENGTH:", len(content))
        print("--- first 800 chars of body text ---")
        body_text = page.inner_text("body")
        print(body_text[:800])
    except Exception as e:
        print("ERROR:", repr(e))
    finally:
        browser.close()
