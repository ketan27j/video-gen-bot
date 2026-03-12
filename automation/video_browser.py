"""
automation/video_browser.py

Playwright-based browser automation for video generation via Grok (x.ai).
Supports manual fallback mode.

IMPORTANT: Selectors must be verified against the live Grok UI.
Run `python -m automation.video_browser --inspect` to open the browser.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

VIDEO_GEN_TIMEOUT = int(os.getenv("VIDEO_GEN_TIMEOUT", "300")) * 1000  # ms
HEADLESS = os.getenv("HEADLESS_BROWSER", "false").lower() == "true"
TOOL = os.getenv("VIDEO_GEN_TOOL", "manual")
GROK_URL = os.getenv("VIDEO_GEN_URL", "https://x.ai/grok")
GROK_AUTH_STATE = os.getenv("GROK_AUTH_STATE", "auth/grok_state.json")


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


class GrokVideoGenerator:
    """
    Automates video generation on Grok (x.ai).

    Workflow:
    1. Navigate to Grok video generation page
    2. Upload reference image
    3. Enter optimized camera + motion prompt
    4. Click generate
    5. Wait for video
    6. Download video

    NOTE: Grok's video generation UI may differ from its chat interface.
    Selectors below are illustrative and must be verified.
    """

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._playwright = None

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox"],
        )

        auth_file = Path(GROK_AUTH_STATE)
        if auth_file.exists():
            self._context = await self._browser.new_context(
                storage_state=str(auth_file),
                viewport={"width": 1280, "height": 900},
            )
            logger.info("Loaded Grok auth state from %s", auth_file)
        else:
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            logger.warning(
                "No saved Grok auth state at %s. Manual login required on first run.",
                auth_file,
            )

    async def save_auth(self):
        if self._context:
            Path(GROK_AUTH_STATE).parent.mkdir(parents=True, exist_ok=True)
            await self._context.storage_state(path=GROK_AUTH_STATE)
            logger.info("Saved Grok auth state to %s", GROK_AUTH_STATE)

    async def stop(self):
        if self._context:
            await self.save_auth()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def generate(
        self,
        image_path: str,
        motion_prompt: str,
        output_path: str,
    ) -> Optional[str]:
        """
        Generate a video from `image_path` + `motion_prompt`.
        Save to `output_path`. Returns path on success, None on failure.
        """
        page: Page = await self._context.new_page()
        try:
            logger.info("Grok: navigating to video generation page")
            await page.goto(GROK_URL, wait_until="networkidle", timeout=30000)

            # ── Upload reference image ────────────────────────────────────────
            # Grok may use a file input or a drag-drop zone
            file_input_selector = "input[type='file'][accept*='image'], input[type='file']"
            file_input = await page.query_selector(file_input_selector)

            if file_input:
                await file_input.set_input_files(image_path)
                logger.info("Grok: uploaded image via file input")
            else:
                # Try drag-and-drop into upload zone
                upload_zone = await page.query_selector(
                    "[class*='upload' i], [class*='dropzone' i], [data-testid*='upload' i]"
                )
                if upload_zone:
                    # Use JavaScript to simulate file drop
                    await page.evaluate("""
                        (selector) => {
                            const el = document.querySelector(selector);
                            if (el) el.click();
                        }
                    """, "[class*='upload' i]")
                    logger.warning("Grok: drag-drop upload zone found but automated upload may not work. Manual intervention may be needed.")
                else:
                    logger.error("Grok: no file input found — UI may have changed")
                    return None

            # ── Wait for image preview ────────────────────────────────────────
            await page.wait_for_timeout(2000)

            # ── Enter motion prompt ───────────────────────────────────────────
            prompt_selector = (
                "textarea[placeholder*='prompt' i], "
                "textarea[placeholder*='describe' i], "
                "div[contenteditable='true'][class*='prompt' i]"
            )
            await page.wait_for_selector(prompt_selector, timeout=10000)
            await page.fill(prompt_selector, motion_prompt)

            # ── Click Generate ────────────────────────────────────────────────
            generate_selector = (
                "button:has-text('Generate'), "
                "button:has-text('Create'), "
                "button[data-testid*='generate' i], "
                "button[type='submit']"
            )
            await page.click(generate_selector)

            logger.info(
                "Grok: waiting for video generation (up to %ds)...",
                VIDEO_GEN_TIMEOUT // 1000,
            )

            # ── Wait for video element ────────────────────────────────────────
            video_selector = "video[src], video source[src], a[href*='.mp4']"
            await page.wait_for_selector(video_selector, timeout=VIDEO_GEN_TIMEOUT)

            # ── Extract video URL ─────────────────────────────────────────────
            video_el = await page.query_selector("video")
            video_url = None

            if video_el:
                video_url = await video_el.get_attribute("src")
                if not video_url:
                    source_el = await video_el.query_selector("source")
                    if source_el:
                        video_url = await source_el.get_attribute("src")

            if not video_url:
                # Try download link
                link_el = await page.query_selector("a[href*='.mp4'], a[download]")
                if link_el:
                    video_url = await link_el.get_attribute("href")

            if not video_url:
                logger.error("Grok: could not extract video URL")
                await page.screenshot(path=f"debug_video_{Path(output_path).stem}.png")
                return None

            if video_url.startswith("/"):
                video_url = "https://x.ai" + video_url

            success = await _download_file(video_url, output_path)
            if success:
                logger.info("Video saved to %s", output_path)
                return output_path
            return None

        except Exception as e:
            logger.error("Grok video generation failed: %s", e)
            try:
                await page.screenshot(path=f"debug_video_{Path(output_path).stem}.png")
            except Exception:
                pass
            return None
        finally:
            await page.close()


class ManualVideoGenerator:
    """
    Fallback: sends prompt + image to the Telegram user and waits for them
    to manually generate and upload the video.
    """

    def __init__(self, request_video_callback):
        self._callback = request_video_callback

    async def start(self):
        pass

    async def stop(self):
        pass

    async def generate(
        self,
        image_path: str,
        motion_prompt: str,
        output_path: str,
    ) -> Optional[str]:
        return await self._callback(image_path, motion_prompt, output_path)


def get_video_generator(manual_callback=None):
    """Factory: return correct generator based on VIDEO_GEN_TOOL env var."""
    if TOOL == "grok":
        return GrokVideoGenerator()
    elif TOOL == "manual" or manual_callback:
        if manual_callback is None:
            raise ValueError("ManualVideoGenerator requires a request_video_callback")
        return ManualVideoGenerator(manual_callback)
    else:
        raise ValueError(f"Unknown VIDEO_GEN_TOOL: {TOOL}. Options: grok, manual")


# ── CLI inspect helper ────────────────────────────────────────────────────────

async def _inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(GROK_URL)
        print("Browser opened. Press Enter to close...")
        input()
        await browser.close()


if __name__ == "__main__":
    import sys
    if "--inspect" in sys.argv:
        asyncio.run(_inspect())