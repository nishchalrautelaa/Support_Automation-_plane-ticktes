"""
Takes screenshots of all four pipeline states and saves them to docs/screenshots/.
Run:  python scripts/take_screenshots.py
Requires:  pip install playwright && python -m playwright install chromium
"""
import asyncio, json, time
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
OUT  = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

SCENARIOS = [
    {
        "name": "01_home",
        "subject": "",
        "body": "",
        "desc": "Home screen — form + sample tickets",
        "scroll_to": None,
    },
    {
        "name": "02_auto_resolve",
        "subject": "Can't log in - forgot my password",
        "body": "Hi, I haven't logged in for a while and I can't remember my password. How do I reset it? Thanks!",
        "plan": "pro",
        "desc": "Auto-resolve — high confidence FAQ",
        "scroll_to": "#results",
    },
    {
        "name": "03_escalate",
        "subject": "This is unacceptable - I want my money back NOW",
        "body": "I've been charged for a renewal I never wanted and your product has been broken all week. Refund me immediately.",
        "plan": "pro",
        "desc": "Escalate — angry sentiment + refund guardrails fire",
        "scroll_to": "#results",
    },
    {
        "name": "04_draft_reply",
        "subject": "How do I set up webhooks?",
        "body": "I'd like my server to be notified when events happen in my account. Is it possible to configure webhooks, and how do I verify they're really from you?",
        "plan": "enterprise",
        "desc": "Draft reply — relevant KB found but below auto-resolve bar",
        "scroll_to": "#results",
    },
    {
        "name": "05_history",
        "subject": "I was charged twice this month??",
        "body": "I just looked at my statement and it looks like I got billed two times. Can you explain what's going on?",
        "plan": "pro",
        "desc": "Ticket history panel showing multiple processed tickets",
        "scroll_to": "#history-section",
    },
]


async def shoot():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 860})

        # Screenshot 1: home
        await page.goto(BASE, wait_until="networkidle")
        await page.wait_for_timeout(600)
        path = str(OUT / "01_home.png")
        await page.screenshot(path=path, full_page=False)
        print(f"  saved {path}")

        # Screenshots 2-5: process tickets
        for s in SCENARIOS[1:]:
            await page.goto(BASE, wait_until="networkidle")
            await page.wait_for_timeout(400)
            await page.fill("#subject", s["subject"])
            await page.fill("#body", s["body"])
            if s.get("plan"):
                await page.select_option("#plan", s["plan"])
            await page.click("#run")
            # wait for results to render (pipeline is fast in mock mode)
            await page.wait_for_function(
                "document.querySelector('#results .card') !== null",
                timeout=8000,
            )
            await page.wait_for_timeout(300)
            if s["scroll_to"]:
                await page.eval_on_selector(
                    s["scroll_to"],
                    "el => el.scrollIntoView({block:'start'})"
                )
                await page.wait_for_timeout(200)
            path = str(OUT / f"{s['name']}.png")
            await page.screenshot(path=path, full_page=False)
            print(f"  saved {path}")

        await browser.close()
        print("\nAll screenshots saved to docs/screenshots/")


if __name__ == "__main__":
    asyncio.run(shoot())
