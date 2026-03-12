"""
automation/image_browser.py

Playwright-based browser automation for AI image generation.
Supports Leonardo.ai with a manual fallback mode that prompts the user
to generate and save images themselves.

IMPORTANT: Selectors must be verified against the live site UI.
Run `python -m automation.image_browser --inspect` to open the browser for inspection.
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

IMAGE_GEN_TIMEOUT = int(os.getenv("IMAGE_GEN_TIMEOUT", "120")) * 1000  # ms
HEADLESS = os.getenv("HEADLESS_BROWSER", "false").lower() == "true"
TOOL = os.getenv("IMAGE_GEN_TOOL", "manual")
LEONARDO_URL = os.getenv("IMAGE_GEN_URL", "https://app.leonardo.ai/ai-generations")
LEONARDO_AUTH_STATE = os.getenv("LEONARDO_AUTH_STATE", "auth/leonardo_state.json")


async def _download_file(url: str, dest_path: str) -> bool:
    """Download a remote file to dest_path."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(dest_path, "wb") as f:
                        f.write(await resp.read())
                    return True
    except Exception as e:
        logger.error("Download failed: %s", e)
    return False


class LeonardoImageGenerator:
    """
    Automates image generation on Leonardo.ai.

    NOTE: CSS selectors below are based on Leonardo.ai as of late 2024.
    They WILL need updating if the site changes. Use --inspect mode to verify.
    """

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )

        # Load saved auth state if available
        auth_file = Path(LEONARDO_AUTH_STATE)
        if auth_file.exists():
            self._context = await self._browser.new_context(
                storage_state=str(auth_file),
                viewport={"width": 1280, "height": 900},
            )
            logger.info("Loaded Leonardo auth state from %s", auth_file)
        else:
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            logger.warning(
                "No saved Leonardo auth state found at %s. "
                "You will need to log in manually on first run.",
                auth_file,
            )

    async def save_auth(self):
        """Save current browser cookies/storage for reuse."""
        if self._context:
            Path(LEONARDO_AUTH_STATE).parent.mkdir(parents=True, exist_ok=True)
            await self._context.storage_state(path=LEONARDO_AUTH_STATE)
            logger.info("Saved Leonardo auth state to %s", LEONARDO_AUTH_STATE)

    async def stop(self):
        if self._context:
            await self.save_auth()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def generate(self, prompt: str, output_path: str) -> Optional[str]:
        """
        Generate one image from `prompt` and save it to `output_path`.
        Returns the output path on success, None on failure.
        """
        page: Page = await self._context.new_page()
        try:
            logger.info("Leonardo: navigating to generation page")
            await page.goto(LEONARDO_URL, wait_until="networkidle", timeout=30000)

            # ── Fill the prompt ──────────────────────────────────────────────
            # Selector may need updating — inspect the live page
            prompt_selector = "textarea[placeholder*='prompt' i], textarea[data-testid*='prompt' i], div[contenteditable='true']"
            await page.wait_for_selector(prompt_selector, timeout=15000)
            await page.fill(prompt_selector, prompt)

            # ── Click Generate ───────────────────────────────────────────────
            generate_selector = "button:has-text('Generate'), button[data-testid*='generate' i]"
            await page.click(generate_selector)

            logger.info("Leonardo: waiting for image generation (up to %ds)...", IMAGE_GEN_TIMEOUT // 1000)

            # ── Wait for result image ────────────────────────────────────────
            result_selector = "img[data-testid*='generated' i], .generated-image img, [class*='generationImage'] img"
            await page.wait_for_selector(result_selector, timeout=IMAGE_GEN_TIMEOUT)

            img_el = await page.query_selector(result_selector)
            img_url = await img_el.get_attribute("src")

            if not img_url:
                logger.error("Leonardo: could not extract image URL")
                return None

            # Handle relative URLs
            if img_url.startswith("/"):
                img_url = "https://app.leonardo.ai" + img_url

            success = await _download_file(img_url, output_path)
            if success:
                logger.info("Image saved to %s", output_path)
                return output_path
            return None

        except Exception as e:
            logger.error("Leonardo generation failed: %s", e)
            # Save a screenshot for debugging
            try:
                await page.screenshot(path=f"debug_screenshot_{Path(output_path).stem}.png")
            except Exception:
                pass
            return None
        finally:
            await page.close()


class ManualImageGenerator:
    """
    Fallback: sends the prompt to the Telegram user and waits for them
    to manually generate and upload the image.
    This is handled via a callback set from the Telegram layer.
    """

    def __init__(self, request_image_callback):
        """
        request_image_callback: async callable(prompt, output_path) -> str
        Should send the prompt to the user and wait for their image upload,
        then save it to output_path and return the path.
        """
        self._callback = request_image_callback

    async def start(self):
        pass

    async def stop(self):
        pass

    async def generate(self, prompt: str, output_path: str) -> Optional[str]:
        return await self._callback(prompt, output_path)


def get_image_generator(manual_callback=None):
    """Factory: return the correct generator based on IMAGE_GEN_TOOL env var."""
    if TOOL == "leonardo":
        return LeonardoImageGenerator()
    elif TOOL == "manual" or manual_callback:
        if manual_callback is None:
            raise ValueError("ManualImageGenerator requires a request_image_callback")
        return ManualImageGenerator(manual_callback)
    else:
        raise ValueError(f"Unknown IMAGE_GEN_TOOL: {TOOL}. Options: leonardo, manual")


# ── CLI inspect helper ────────────────────────────────────────────────────────

async def _inspect():
    """Open Leonardo.ai in a non-headless browser so you can inspect selectors."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(LEONARDO_URL)
        print("Browser opened. Press Enter to close...")
        input()
        await browser.close()


if __name__ == "__main__":
    import sys
    if "--inspect" in sys.argv:
        asyncio.run(_inspect())