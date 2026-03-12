"""
graph/nodes/camera_optimizer.py
Agent 3 — enriches each video motion prompt with the most cinematically
appropriate camera movement from the camera_moves.txt reference library.
"""

import re
import logging
from pathlib import Path
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage

from graph.state import PipelineState
from utils.llm import get_llm

logger = logging.getLogger(__name__)

CAMERA_MOVES_PATH = Path(__file__).parent.parent.parent / "prompts" / "camera_moves.txt"

OPTIMIZER_SYSTEM = """You are a cinematography expert specialising in AI video generation.
Your task: given a list of video motion prompts, enrich each one with the most 
dramatically appropriate camera movement from the provided reference library.

Rules:
- Output ONLY the enhanced prompts, one per line, prefixed with "PROMPT N:" 
- Do NOT add extra commentary or blank lines between prompts
- Keep each enhanced prompt under 120 words
- Integrate the camera move naturally into the existing prompt text
- Choose the move that best matches the emotional and narrative tone
"""

OPTIMIZER_USER = """
=== CAMERA MOVES REFERENCE ===
{camera_moves}

=== VIDEO MOTION PROMPTS TO ENHANCE ===
{video_prompts}

Output one enhanced prompt per line prefixed with PROMPT N: where N matches the input number.
"""


def _load_camera_moves() -> str:
    return CAMERA_MOVES_PATH.read_text(encoding="utf-8")


def _format_video_prompts(video_motion_prompts: list) -> str:
    lines = []
    for vp in video_motion_prompts:
        lines.append(f"PROMPT {vp['number']}: {vp['prompt']}")
    return "\n".join(lines)


def _parse_optimized_prompts(raw: str, expected_count: int) -> List[str]:
    """Extract PROMPT N: lines from LLM response."""
    results: List[str] = []
    matches = re.findall(r"PROMPT\s+\d+[:\s]+(.*?)(?=PROMPT\s+\d+|$)", raw, re.DOTALL)
    for m in matches:
        results.append(m.strip())

    # Pad with empty strings if parsing failed
    while len(results) < expected_count:
        results.append("")

    return results[:expected_count]


async def optimize_camera_node(state: PipelineState) -> dict:
    """
    LangGraph node: enriches video motion prompts with camera movements.
    """
    idx = state["current_scene_index"]
    scenes = list(state["scenes"])
    scene = dict(scenes[idx])

    video_prompts = scene.get("video_motion_prompts", [])
    if not video_prompts:
        logger.warning("optimize_camera_node: no video prompts found for scene %d", scene["scene_number"])
        scene["optimized_video_prompts"] = []
        scenes[idx] = scene
        return {"scenes": scenes}

    logger.info("optimize_camera_node: optimizing %d prompts for scene %d", len(video_prompts), scene["scene_number"])

    llm = get_llm()
    camera_moves = _load_camera_moves()
    formatted_prompts = _format_video_prompts(video_prompts)

    messages = [
        SystemMessage(content=OPTIMIZER_SYSTEM),
        HumanMessage(content=OPTIMIZER_USER.format(
            camera_moves=camera_moves,
            video_prompts=formatted_prompts,
        )),
    ]

    response = await llm.ainvoke(messages)
    raw_output: str = response.content

    logger.debug("Camera optimizer raw output:\n%s", raw_output[:400])

    optimized = _parse_optimized_prompts(raw_output, len(video_prompts))

    # Fallback: use original prompt if optimization result is empty
    for i, opt in enumerate(optimized):
        if not opt and i < len(video_prompts):
            optimized[i] = video_prompts[i]["prompt"]

    scene["optimized_video_prompts"] = optimized
    scenes[idx] = scene

    logger.info("Camera optimization complete for scene %d", scene["scene_number"])

    return {"scenes": scenes}