"""
graph/nodes/scene_generator.py
Agent 1 — takes movie_idea, fills prompt 1, calls LLM, parses output into
structured scene data and character definitions.
"""

import re
import os
import logging
from pathlib import Path
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from graph.state import PipelineState, SceneData
from utils.llm import get_llm

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "char_scene_gen.txt"


def _load_prompt(movie_idea: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    # Strip the "Prompts Used:" header line and separator
    lines = template.splitlines()
    # Find the actual system prompt start (skip header lines)
    start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("You are an AI animation planner"):
            start = i
            break
    prompt = "\n".join(lines[start:])
    prompt = prompt.replace("{ movie-idea }", movie_idea)
    prompt = prompt.replace("---------------------------------", "").strip()
    return prompt


def _parse_characters(raw: str) -> Dict[str, str]:
    """Extract STEP 2 character definitions into { name: description }."""
    chars: Dict[str, str] = {}

    # Find the STEP 2 block
    match = re.search(
        r"STEP 2[:\s]+CHARACTER DEFINITIONS(.*?)(?=STEP 3|$)",
        raw, re.DOTALL | re.IGNORECASE
    )
    if not match:
        return chars

    block = match.group(1).strip()

    # Split on lines that look like character names (short, possibly bold/titled)
    # Characters appear as "Name / role" followed by a description paragraph
    entries = re.split(r"\n(?=[A-Z][^\n]{1,50}(?:\s*/\s*[^\n]+)?\n)", block)
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        lines = [l.strip() for l in entry.splitlines() if l.strip()]
        if len(lines) >= 2:
            name_line = lines[0]
            # Clean markdown bold
            name_line = re.sub(r"\*+", "", name_line).strip()
            description = " ".join(lines[1:])
            chars[name_line] = description

    return chars


def _parse_scenes(raw: str) -> List[SceneData]:
    """Extract all SCENE X blocks into SceneData list."""
    scenes: List[SceneData] = []

    scene_blocks = re.findall(
        r"(SCENE\s+\d+.*?)(?=SCENE\s+\d+|\Z)",
        raw, re.DOTALL | re.IGNORECASE
    )

    for i, block in enumerate(scene_blocks):
        block = block.strip()

        # Extract characters present line
        chars_match = re.search(
            r"Characters?\s+present[:\s]+(.*?)(?:\n|$)",
            block, re.IGNORECASE
        )
        chars_present: List[str] = []
        if chars_match:
            raw_chars = chars_match.group(1)
            chars_present = [
                c.strip().strip("*").strip()
                for c in re.split(r"[,;&]|\band\b", raw_chars)
                if c.strip()
            ]

        scene: SceneData = {
            "scene_number": i + 1,
            "scene_text": block,
            "characters_present": chars_present,
            "character_descriptions": {},
            "character_image_prompts": [],
            "image_sequence": [],
            "video_motion_prompts": [],
            "optimized_video_prompts": [],
            "generated_images": [],
            "generated_videos": [],
            "approved": False,
            "skip": False,
        }
        scenes.append(scene)

    return scenes


def _parse_story_snapshot(raw: str) -> str:
    match = re.search(
        r"STEP 1[:\s]+STORY SNAPSHOT\s*(.*?)(?=STEP 2|$)",
        raw, re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return ""


def _parse_final_resolution(raw: str) -> str:
    match = re.search(
        r"STEP 4[:\s]+FINAL RESOLUTION\s*(.*?)$",
        raw, re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return ""


async def generate_scenes_node(state: PipelineState) -> dict:
    """
    LangGraph node: calls LLM with prompt 1, parses full scene plan.
    Returns partial state update.
    """
    logger.info("generate_scenes_node: generating scene plan for idea: %s", state["movie_idea"][:60])

    llm = get_llm()
    prompt_text = _load_prompt(state["movie_idea"])

    messages = [
        SystemMessage(content="You are an expert AI animation planner. Follow the output structure exactly."),
        HumanMessage(content=prompt_text),
    ]

    response = await llm.ainvoke(messages)
    raw_output: str = response.content

    logger.debug("Raw scene output:\n%s", raw_output[:500])

    characters = _parse_characters(raw_output)
    scenes = _parse_scenes(raw_output)

    # Attach filtered character descriptions to each scene
    for scene in scenes:
        scene["character_descriptions"] = {
            name: desc
            for name, desc in characters.items()
            if any(
                name.lower() in cp.lower() or cp.lower() in name.lower()
                for cp in scene["characters_present"]
            )
        }
        # Fallback: if no match, include all characters
        if not scene["character_descriptions"]:
            scene["character_descriptions"] = characters

    story_snapshot = _parse_story_snapshot(raw_output)
    final_resolution = _parse_final_resolution(raw_output)

    logger.info(
        "Parsed %d scenes, %d characters",
        len(scenes), len(characters)
    )

    return {
        "raw_scene_output": raw_output,
        "story_snapshot": story_snapshot,
        "character_definitions": characters,
        "scenes": scenes,
        "final_resolution": final_resolution,
        "scenes_approved": False,
        "regenerate_scenes": False,
        "current_scene_index": 0,
        "messages": [HumanMessage(content=prompt_text), response],
    }