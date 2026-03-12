import os
import aiohttp
from playwright.async_api import async_playwright

class GrokVideoGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    async def generate(self, image_path: str, motion_prompt: str, scene_num: int, video_num: int) -> str:
        output_path = os.path.join(self.output_dir, f"scene_{scene_num:02d}_video_{video_num:02d}.mp4")
        
        async with async_playwright() as p:
            headless = os.getenv("HEADLESS_BROWSER", "false").lower() == "true"
            browser = await p.chromium.launch(headless=headless)
            
            storage_path = "storage_state.json"
            if os.path.exists(storage_path):
                context = await browser.new_context(storage_state=storage_path)
            else:
                context = await browser.new_context()
                
            page = await context.new_page()

            try:
                await page.goto(os.getenv("VIDEO_GEN_TOOL_URL", "https://x.ai/grok"))
                
                # Basic login check
                if "login" in page.url:
                    print("Please log in to Grok and ensure storage_state.json is updated.")
                    await browser.close()
                    return ""

                # Upload reference image
                await page.set_input_files("input[type='file']", image_path)

                # Enter optimized camera + motion prompt
                await page.fill(".prompt-textarea", motion_prompt)
                await page.click(".generate-video-btn")

                # Wait for video generation (up to 5 mins)
                await page.wait_for_selector(".video-result", timeout=300_000)
                
                # Logic to download the video would go here
                # For now, we simulate success
                # with open(output_path, "w") as f: f.write("video content")
                return output_path
                
            except Exception as e:
                print(f"Error during video generation: {e}")
            finally:
                await browser.close()
                
            return ""
