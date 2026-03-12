import os
import aiohttp
from playwright.async_api import async_playwright

class ImageGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    async def generate(self, prompt: str, scene_num: int, image_num: int) -> str:
        output_path = os.path.join(self.output_dir, f"scene_{scene_num:02d}_image_{image_num:02d}.png")
        
        async with async_playwright() as p:
            # Note: headless=False for debugging, HEADLESS_BROWSER env for prod
            headless = os.getenv("HEADLESS_BROWSER", "false").lower() == "true"
            browser = await p.chromium.launch(headless=headless)
            
            # Use storage_state if available to reuse login session
            storage_path = "storage_state.json"
            if os.path.exists(storage_path):
                context = await browser.new_context(storage_state=storage_path)
            else:
                context = await browser.new_context()
                
            page = await context.new_page()

            try:
                await page.goto(os.getenv("IMAGE_GEN_TOOL_URL", "https://app.leonardo.ai/ai-generations"))
                
                # Check if we need to login (basic check)
                if "login" in page.url:
                    print("Please log in to Leonardo.ai and ensure storage_state.json is updated.")
                    await browser.close()
                    return ""

                await page.wait_for_selector("[data-testid='prompt-input']", timeout=10000)
                await page.fill("[data-testid='prompt-input']", prompt)
                await page.click("[data-testid='generate-button']")

                # Wait for generation (this is highly subject to UI changes)
                await page.wait_for_selector(".generated-image", timeout=120_000)
                image_element = await page.query_selector(".generated-image img")
                image_url = await image_element.get_attribute("src")

                if image_url:
                    await self._download_image(image_url, output_path)
                    return output_path
                
            except Exception as e:
                print(f"Error during image generation: {e}")
            finally:
                await browser.close()
                
            return ""

    async def _download_image(self, url: str, path: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f:
                        f.write(await resp.read())
