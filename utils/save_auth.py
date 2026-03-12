"""
auth/save_auth.py

One-time helper script to log in to Leonardo.ai and Grok in a visible browser,
then save the authentication cookies/storage for later headless reuse.

Usage:
    python auth/save_auth.py --tool leonardo
    python auth/save_auth.py --tool grok
    python auth/save_auth.py --tool all
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

LEONARDO_URL = os.getenv("IMAGE_GEN_URL", "https://app.leonardo.ai")
GROK_URL = os.getenv("VIDEO_GEN_URL", "https://x.ai/grok")
LEONARDO_AUTH = os.getenv("LEONARDO_AUTH_STATE", "auth/leonardo_state.json")
GROK_AUTH = os.getenv("GROK_AUTH_STATE", "auth/grok_state.json")


async def save_leonardo_auth():
    print("\n🔐 Opening Leonardo.ai — please log in, then press Enter here to save your session.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(LEONARDO_URL)
        input(">> Press Enter after logging in to Leonardo.ai...")
        Path(LEONARDO_AUTH).parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=LEONARDO_AUTH)
        print(f"✅ Leonardo auth state saved to {LEONARDO_AUTH}")
        await browser.close()


async def save_grok_auth():
    print("\n🔐 Opening Grok — please log in, then press Enter here to save your session.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(GROK_URL)
        input(">> Press Enter after logging in to Grok...")
        Path(GROK_AUTH).parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=GROK_AUTH)
        print(f"✅ Grok auth state saved to {GROK_AUTH}")
        await browser.close()


async def main(tool: str):
    if tool in ("leonardo", "all"):
        await save_leonardo_auth()
    if tool in ("grok", "all"):
        await save_grok_auth()
    print("\n✅ Done. Auth states saved. The bot will use these automatically.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save browser auth state for bot automation.")
    parser.add_argument("--tool", choices=["leonardo", "grok", "all"], default="all")
    args = parser.parse_args()
    asyncio.run(main(args.tool))