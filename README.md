# 🎬 Telegram AI Storyboard Bot

An AI-powered Telegram bot that transforms a simple movie idea into a fully generated storyboard — complete with scene breakdowns, character definitions, AI-generated images, and AI-generated videos — using LangChain, LangGraph, and Playwright browser automation.

---

## 📖 Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [High-Level Pipeline Flow](#high-level-pipeline-flow)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Core Concepts](#core-concepts)
  - [LangGraph State](#langgraph-state)
  - [LangGraph Pipeline](#langgraph-pipeline)
  - [Human-in-the-Loop](#human-in-the-loop)
  - [Browser Automation](#browser-automation)
  - [Camera Move Optimizer](#camera-move-optimizer)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Output Structure](#output-structure)
- [Design Decisions](#design-decisions)
- [Known Limitations & Notes](#known-limitations--notes)

---

## Overview

This bot takes a **movie idea** from the user via Telegram and runs it through a multi-agent AI pipeline:

1. Generates a full scene breakdown with character definitions
2. Presents each scene to the user for approval (human-in-the-loop)
3. For each approved scene, generates image and video prompts
4. Optimizes video prompts with cinematic camera movements
5. Automates image generation via browser (e.g. Leonardo.ai)
6. Automates video generation via browser (Grok)
7. Saves all outputs to organized `/images` and `/videos` folders

---

## System Architecture

```
telegram_storyboard_bot/
├── main.py                        # Telegram bot entry point
├── graph/
│   ├── state.py                   # LangGraph state definition
│   ├── pipeline.py                # Main LangGraph graph
│   └── nodes/
│       ├── scene_generator.py     # Node 1: runs prompt 1 (char-scene-gen)
│       ├── video_scripter.py      # Node 2: runs prompt 2 per scene (video-gen)
│       ├── camera_optimizer.py    # Node 3: enhances video prompts with camera moves
│       ├── image_automator.py     # Node 4: browser automation → image tool
│       └── video_automator.py     # Node 5: browser automation → Grok
├── prompts/
│   ├── char_scene_gen.txt         # Prompt 1: Story & scene breakdown
│   ├── video_gen.txt              # Prompt 2: Image & video script per scene
│   └── camera_moves.txt           # Reference: 38 cinematic camera moves
├── automation/
│   ├── image_browser.py           # Playwright logic for image generation
│   └── video_browser.py           # Playwright logic for Grok video generation
├── handlers/
│   ├── conversation.py            # Telegram conversation handlers
│   └── callbacks.py               # Inline keyboard callbacks
└── output/
    ├── images/                    # All generated scene images
    └── videos/                    # All generated scene videos
```

---

## High-Level Pipeline Flow

```
User sends movie idea via Telegram
            ↓
  Agent 1: Story & Scene Generator
  (LLM + char-scene-gen.txt prompt)
            ↓
  Bot sends full scene breakdown to user
  User: [✅ Approve All] or [✏️ Edit]
            ↓
  ┌─────────────────────────────────┐
  │       For each scene:           │
  │                                 │
  │  Agent 2: Video Script Gen      │
  │  (LLM + video-gen.txt prompt)   │
  │  → Image prompts (Section 2)    │
  │  → Video motion prompts (Sec 3) │
  │            ↓                    │
  │  Bot sends scene script         │
  │  User: [✅ Approve] [🔄 Regen]  │
  │            ↓                    │
  │  Agent 3: Camera Optimizer      │
  │  (LLM + camera_moves.txt ref)   │
  │            ↓                    │
  │  Browser: Generate Images       │
  │  (Playwright → Leonardo.ai)     │
  │            ↓                    │
  │  Browser: Generate Videos       │
  │  (Playwright → Grok)            │
  └─────────────────────────────────┘
            ↓
  All scenes complete
  /images and /videos folders ready
  Bot sends summary to user
```

---

## Tech Stack

| Component | Library / Tool | Purpose |
|---|---|---|
| Telegram Interface | `python-telegram-bot` v20+ | Async bot, inline keyboards |
| Agent Orchestration | `langgraph` | Stateful graph with human-in-the-loop interrupts |
| LLM Calls | `langchain-anthropic` / `langchain-openai` | Scene gen, video scripting, camera optimization |
| Browser Automation | `playwright` (async) | Image gen tool + Grok video gen |
| State Persistence | `SqliteSaver` (LangGraph) | Survives bot restarts, resumes mid-pipeline |
| Async Runtime | `asyncio` | All components run async |

> **Why LangGraph over plain LangChain?**
> LangGraph is purpose-built for stateful, cyclical agent flows with human checkpoints — exactly what "user in the loop" requires. It supports `interrupt_before` nodes that pause execution until the user responds via Telegram.

---

## Core Concepts

### LangGraph State

The entire pipeline shares a single typed state object that is persisted between interrupts:

```python
# graph/state.py
from typing import TypedDict, List, Annotated
from langgraph.graph.message import add_messages

class SceneData(TypedDict):
    scene_number: int
    scene_text: str                  # Raw scene from prompt 1
    characters_present: list         # Extracted character names for this scene
    image_prompts: list              # From prompt 2, Section 2
    video_prompts: list              # From prompt 2, Section 3
    optimized_video_prompts: list    # After camera move optimization
    generated_images: list           # Local file paths
    generated_videos: list           # Local file paths
    approved: bool                   # Human-in-the-loop approval flag

class PipelineState(TypedDict):
    # User input
    movie_idea: str
    chat_id: int                     # Telegram chat ID for sending updates

    # Generated by Agent 1
    story_snapshot: str
    character_definitions: dict      # { name: description }
    scenes: List[SceneData]

    # Processing cursor
    current_scene_index: int

    # Human checkpoint flags
    scenes_approved: bool
    current_scene_approved: bool

    # LLM conversation history
    messages: Annotated[list, add_messages]
```

---

### LangGraph Pipeline

```python
# graph/pipeline.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("generate_scenes",        generate_scenes_node)
    graph.add_node("human_approve_scenes",   human_approve_scenes_node)   # ← interrupt
    graph.add_node("process_scene",          process_scene_node)
    graph.add_node("human_approve_scene",    human_approve_scene_node)    # ← interrupt
    graph.add_node("optimize_camera",        optimize_camera_node)
    graph.add_node("generate_images",        generate_images_node)
    graph.add_node("generate_videos",        generate_videos_node)
    graph.add_node("next_scene_or_finish",   next_scene_or_finish_node)

    graph.set_entry_point("generate_scenes")
    graph.add_edge("generate_scenes", "human_approve_scenes")

    graph.add_conditional_edges(
        "human_approve_scenes",
        lambda s: "process_scene" if s["scenes_approved"] else "generate_scenes"
    )

    graph.add_edge("process_scene", "human_approve_scene")

    graph.add_conditional_edges(
        "human_approve_scene",
        lambda s: "optimize_camera" if s["current_scene_approved"] else "process_scene"
    )

    graph.add_edge("optimize_camera",       "generate_images")
    graph.add_edge("generate_images",       "generate_videos")
    graph.add_edge("generate_videos",       "next_scene_or_finish")

    graph.add_conditional_edges(
        "next_scene_or_finish",
        lambda s: "process_scene" if s["current_scene_index"] < len(s["scenes"]) else END
    )

    checkpointer = SqliteSaver.from_conn_string("pipeline_state.db")
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approve_scenes", "human_approve_scene"]
    )
```

---

### Human-in-the-Loop

When LangGraph hits an `interrupt_before` node, execution **pauses completely**. The Telegram bot sends a message with inline buttons. When the user taps a button, the callback handler resumes the graph with updated state.

```python
# handlers/conversation.py

async def send_scene_for_approval(bot, chat_id, scene_data, scene_index):
    text = f"*Scene {scene_index + 1}*\n\n{scene_data['scene_text']}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve",     callback_data=f"approve_scene_{scene_index}"),
            InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen_scene_{scene_index}"),
        ],
        [
            InlineKeyboardButton("⏭ Skip Scene",  callback_data=f"skip_scene_{scene_index}"),
            InlineKeyboardButton("✏️ Edit Prompt", callback_data=f"edit_scene_{scene_index}"),
        ]
    ])
    await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="Markdown")


# handlers/callbacks.py

async def button_callback(update, context):
    query = update.callback_query
    data  = query.data
    thread_id = context.user_data["thread_id"]

    if data.startswith("approve_scene_"):
        graph.update_state(
            {"configurable": {"thread_id": thread_id}},
            {"current_scene_approved": True}
        )
        await graph.arun(None, config={"configurable": {"thread_id": thread_id}})
```

---

### Browser Automation

#### Image Generation (e.g. Leonardo.ai)

```python
# automation/image_browser.py
from playwright.async_api import async_playwright

class ImageGenerator:
    async def generate(self, prompt: str, output_path: str) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page    = await browser.new_page()

            await page.goto("https://app.leonardo.ai/ai-generations")
            await page.wait_for_selector("[data-testid='prompt-input']")
            await page.fill("[data-testid='prompt-input']", prompt)
            await page.click("[data-testid='generate-button']")

            # Wait up to 2 minutes for generation
            await page.wait_for_selector(".generated-image", timeout=120_000)
            image_element = await page.query_selector(".generated-image img")
            image_url     = await image_element.get_attribute("src")

            await self._download_image(image_url, output_path)
            await browser.close()
            return output_path
```

#### Video Generation (Grok)

```python
# automation/video_browser.py
from playwright.async_api import async_playwright

class GrokVideoGenerator:
    async def generate(self, image_path: str, motion_prompt: str, output_path: str) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page    = await browser.new_page()

            await page.goto("https://x.ai/grok")

            # Upload reference image
            await page.set_input_files("input[type='file']", image_path)

            # Enter optimized camera + motion prompt
            await page.fill(".prompt-textarea", motion_prompt)
            await page.click(".generate-video-btn")

            # Wait up to 5 minutes for video generation
            await page.wait_for_selector(".video-result", timeout=300_000)
            # ... download logic

            await browser.close()
            return output_path
```

> **Note:** Exact CSS selectors for Leonardo.ai and Grok must be inspected and updated to match the current live UI of each platform.

---

### Camera Move Optimizer

After video prompts are generated by Agent 2, Agent 3 enriches each prompt with a cinematically appropriate camera movement chosen from the 38-move reference library (`camera_moves.txt`).

```python
# graph/nodes/camera_optimizer.py

CAMERA_OPTIMIZER_PROMPT = """
You are a cinematography expert for AI video generation.

Given these video motion prompts from a scene:
{video_prompts}

And this reference list of camera movements:
{camera_moves_reference}

For EACH video prompt, select the most dramatically appropriate camera move
from the reference and integrate it into the prompt.

Output one enhanced prompt per line, numbered to match input.
Keep prompts under 100 words each.
"""

async def optimize_camera_node(state: PipelineState) -> PipelineState:
    scene = state["scenes"][state["current_scene_index"]]

    llm = ChatAnthropic(model="claude-sonnet-4-5")

    response = await llm.ainvoke(CAMERA_OPTIMIZER_PROMPT.format(
        video_prompts="\n".join(scene["video_prompts"]),
        camera_moves_reference=open("prompts/camera_moves.txt").read()
    ))

    scene["optimized_video_prompts"] = parse_optimized_prompts(response.content)
    return state
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- An Anthropic or OpenAI API key
- Accounts on Leonardo.ai and Grok (with active sessions for browser automation)

### Install

```bash
git clone https://github.com/yourname/telegram-storyboard-bot.git
cd telegram-storyboard-bot

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

### requirements.txt

```
python-telegram-bot>=20.0
langchain>=0.2.0
langgraph>=0.1.0
langchain-anthropic>=0.1.0
playwright>=1.40.0
aiohttp>=3.9.0
aiosqlite>=0.19.0
python-dotenv>=1.0.0
```

---

## Configuration

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Optional: OpenAI instead of Anthropic
# OPENAI_API_KEY=your_openai_api_key_here

# Browser automation
HEADLESS_BROWSER=false          # Set to true in production
IMAGE_GEN_TOOL_URL=https://app.leonardo.ai/ai-generations
VIDEO_GEN_TOOL_URL=https://x.ai/grok

# Output paths
OUTPUT_IMAGES_DIR=output/images
OUTPUT_VIDEOS_DIR=output/videos

# LangGraph persistence
SQLITE_DB_PATH=pipeline_state.db
```

---

## Usage

1. **Start the bot:**
   ```bash
   python main.py
   ```

2. **In Telegram**, send `/start` to your bot

3. **Send your movie idea**, for example:
   ```
   A lonely robot discovers a single flower growing in a post-apocalyptic city
   and tries to protect it from a scavenging drone
   ```

4. **The bot will:**
   - Generate a full scene breakdown and character definitions
   - Ask you to approve or regenerate the overall plan
   - Walk through each scene one-by-one asking for approval
   - Automatically generate images and videos for each approved scene
   - Send you progress updates throughout

5. **Final output** is saved to:
   ```
   output/
   ├── images/
   │   ├── scene_01_image_01.png
   │   ├── scene_01_image_02.png
   │   ├── scene_02_image_01.png
   │   └── ...
   └── videos/
       ├── scene_01_video_01.mp4
       ├── scene_01_video_02.mp4
       ├── scene_02_video_01.mp4
       └── ...
   ```

---

## Output Structure

| Folder | Content | Naming Convention |
|---|---|---|
| `output/images/` | All AI-generated keyframe images | `scene_NN_image_MM.png` |
| `output/videos/` | All AI-generated animated clips | `scene_NN_video_MM.mp4` |

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Agent framework | LangGraph | Native `interrupt_before` support for human-in-the-loop pauses |
| Browser automation | Playwright (async) | Best support for modern SPAs; async-native |
| State persistence | `SqliteSaver` | Survives bot restarts; users can resume mid-pipeline |
| Image tool | Leonardo.ai | Stable web UI well-suited for automation |
| Scene processing | Sequential | Avoids rate limits and browser session conflicts |
| LLM | Claude Sonnet (Anthropic) | Best instruction-following for structured prompt outputs |
| Character filtering | Per-scene extraction | Only characters present in a given scene are passed to Agent 2 |

---

## Known Limitations & Notes

- **Browser selectors:** CSS selectors for Leonardo.ai and Grok are subject to change when those platforms update their UIs. Inspect and update selectors as needed.

- **Browser authentication:** You must be logged into Leonardo.ai and Grok in the Playwright browser session. Save login cookies using Playwright's `storage_state` and reuse them to avoid re-authentication on every run.

- **Rate limiting:** Image generation can take 30–120 seconds per image. Video generation can take 2–5 minutes per clip. Add appropriate delays between browser automation calls.

- **Telegram file size limits:** Videos larger than 50 MB must be sent as documents (not video messages) via Telegram's API.

- **Resuming sessions:** If the bot restarts mid-pipeline, users can resume by sending `/resume` — the `SqliteSaver` checkpointer will restore the last known state for their `thread_id`.

- **Headless mode:** Set `HEADLESS_BROWSER=true` in production once selectors are stable and authentication is handled via saved cookies.

---

## License

MIT License. See `LICENSE` for details.
