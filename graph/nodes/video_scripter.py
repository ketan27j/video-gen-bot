"""
graph/nodes/video_scripter.py
Agent 2 — for the current scene, fills prompt 2 with scene text +
filtered character descriptions, calls LLM, parses image and video prompts.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from graph.state import PipelineState
from utils.llm import get_llm

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "video_gen.txt"


def _build_character_desc_block(character_descriptions: Dict[str, str]) -> str:
    """Format character descriptions for injection into prompt 2."""
    lines = []
    for name, desc in character_descriptions.items():
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines) if lines else "No specific character descriptions provided."


def _load_prompt(character_descriptions: Dict[str, str], scene_text: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")

    # The file has the prompt duplicated — keep first clean copy up to "WAIT AFTER OUTPUT"
    first_wait = template.find("WAIT AFTER OUTPUT.")
    if first_wait != -1:
        template = template[: first_wait + len("WAIT AFTER OUTPUT.")]

    char_block = _build_character_desc_block(character_descriptions)
    prompt = template.replace("{ character-description }", char_block)
    prompt = prompt.replace("{ scene }", scene_text)
    return prompt.strip()


def _parse_character_image_prompts(raw: str) -> List[str]:
    """Parse SECTION 1 character image prompts."""
    prompts: List[str] = []
    match = re.search(
        r"SECTION 1[:\s]+CHARACTER IMAGE PROMPTS(.*?)(?=SECTION 2|$)",
        raw, re.DOTALL | re.IGNORECASE
    )
    if not match:
        return prompts

    block = match.group(1).strip()
    # Each character prompt is a paragraph
    entries = [e.strip() for e in re.split(r"\n\s*\n", block) if e.strip()]
    return entries


def _parse_image_sequence(raw: str) -> List[Dict]:
    """Parse SECTION 2 image sequence into list of {label, prompt}."""
    images: List[Dict] = []
    match = re.search(
        r"SECTION 2[:\s]+SCENE IMAGE SEQUENCE(.*?)(?=SECTION 3|$)",
        raw, re.DOTALL | re.IGNORECASE
    )
    if not match:
        return images

    block = match.group(1).strip()
    image_blocks = re.findall(
        r"IMAGE\s+(\d+)[:\s]*(.*?)(?=IMAGE\s+\d+|\Z)",
        block, re.DOTALL | re.IGNORECASE
    )

    for num, content in image_blocks:
        content = content.strip()
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        label = lines[0] if lines else f"Image {num}"
        # The image prompt is everything after the first line
        prompt_text = " ".join(lines[1:]) if len(lines) > 1 else content
        images.append({
            "number": int(num),
            "label": label,
            "prompt": prompt_text,
        })

    return images


def _parse_video_motion_prompts(raw: str) -> List[Dict]:
    """Parse SECTION 3 video motion prompts into list of {number, input_images, prompt}."""
    prompts: List[Dict] = []
    match = re.search(
        r"SECTION 3[:\s]+VIDEO MOTION PROMPTS(.*?)$",
        raw, re.DOTALL | re.IGNORECASE
    )
    if not match:
        return prompts

    block = match.group(1).strip()
    video_blocks = re.findall(
        r"VIDEO PROMPT\s+(\d+)[:\s]*(.*?)(?=VIDEO PROMPT\s+\d+|\Z)",
        block, re.DOTALL | re.IGNORECASE
    )

    for num, content in video_blocks:
        content = content.strip()
        # Extract "Input image(s):" line
        input_match = re.search(
            r"Input image[s]?\s*[:(]\s*(.*?)(?:\n|$)",
            content, re.IGNORECASE
        )
        input_images = input_match.group(1).strip() if input_match else f"IMAGE {num}"

        # Everything else is the motion prompt text
        motion_text = re.sub(
            r"Input image[s]?\s*[:(].*?(?:\n|$)", "", content, flags=re.IGNORECASE
        ).strip()

        prompts.append({
            "number": int(num),
            "input_images": input_images,
            "prompt": motion_text,
        })

    return prompts


async def process_scene_node(state: PipelineState) -> dict:
    """
    LangGraph node: runs Agent 2 for state["current_scene_index"].
    Parses image prompts, image sequence, and video motion prompts.
    """
    idx = state["current_scene_index"]
    scenes = list(state["scenes"])  # copy
    scene = dict(scenes[idx])

    logger.info("process_scene_node: processing scene %d", scene["scene_number"])

    llm = get_llm()
    prompt_text = _load_prompt(scene["character_descriptions"], scene["scene_text"])

    messages = [
        SystemMessage(content="You are an expert AI animation assistant. Follow the output structure exactly."),
        HumanMessage(content=prompt_text),
    ]

    response = await llm.ainvoke(messages)
    raw_output: str = response.content

    logger.debug("Raw video script output:\n%s", raw_output[:500])

    scene["character_image_prompts"] = _parse_character_image_prompts(raw_output)
    scene["image_sequence"] = _parse_image_sequence(raw_output)
    scene["video_motion_prompts"] = _parse_video_motion_prompts(raw_output)
    scene["approved"] = False

    scenes[idx] = scene

    logger.info(
        "Scene %d: %d image prompts, %d video prompts",
        scene["scene_number"],
        len(scene["image_sequence"]),
        len(scene["video_motion_prompts"]),
    )

    return {
        "scenes": scenes,
        "current_scene_approved": False,
        "regenerate_current_scene": False,
    }