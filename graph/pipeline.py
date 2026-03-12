"""
graph/pipeline.py

Builds the LangGraph StateGraph for the full storyboard pipeline.

Flow:
  generate_scenes
    → [interrupt] human_approve_scenes
    → (loop) process_scene
        → [interrupt] human_approve_scene
        → optimize_camera
        → generate_images
        → generate_videos
        → next_scene_or_finish
    → END
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import PipelineState
from graph.nodes.scene_generator import generate_scenes_node
from graph.nodes.video_scripter import process_scene_node
from graph.nodes.camera_optimizer import optimize_camera_node
from graph.nodes.image_automator import generate_images_node
from graph.nodes.video_automator import generate_videos_node

logger = logging.getLogger(__name__)


# ── Passthrough nodes for human checkpoints ───────────────────────────────────

async def human_approve_scenes_node(state: PipelineState) -> dict:
    """
    Interrupt point. The Telegram handler resumes this node by updating:
      scenes_approved = True   → continue to scene loop
      regenerate_scenes = True → re-run generate_scenes
    """
    return {}


async def human_approve_scene_node(state: PipelineState) -> dict:
    """
    Interrupt point. The Telegram handler resumes by updating:
      current_scene_approved = True → continue to camera optimizer
      regenerate_current_scene = True → re-run process_scene for same index
      scenes[idx].skip = True → advance to next scene
    """
    return {}


async def next_scene_or_finish_node(state: PipelineState) -> dict:
    """Advance the scene cursor."""
    next_idx = state["current_scene_index"] + 1
    return {
        "current_scene_index": next_idx,
        "current_scene_approved": False,
        "regenerate_current_scene": False,
    }


# ── Routing functions ─────────────────────────────────────────────────────────

def route_after_scenes_approval(
    state: PipelineState,
) -> Literal["process_scene", "generate_scenes"]:
    if state.get("regenerate_scenes"):
        logger.info("Routing: regenerate scenes")
        return "generate_scenes"
    if state.get("scenes_approved"):
        logger.info("Routing: scenes approved → process_scene")
        return "process_scene"
    # Default: regenerate
    return "generate_scenes"


def route_after_scene_approval(
    state: PipelineState,
) -> Literal["optimize_camera", "process_scene"]:
    idx = state["current_scene_index"]
    scenes = state.get("scenes", [])

    if idx < len(scenes) and scenes[idx].get("skip"):
        logger.info("Routing: scene %d skipped", idx + 1)
        # Mark as approved to skip through
        return "optimize_camera"

    if state.get("regenerate_current_scene"):
        logger.info("Routing: regenerate scene %d", idx + 1)
        return "process_scene"

    if state.get("current_scene_approved"):
        logger.info("Routing: scene %d approved → optimize_camera", idx + 1)
        return "optimize_camera"

    return "process_scene"


def route_after_video_generation(
    state: PipelineState,
) -> Literal["process_scene", "__end__"]:
    idx = state["current_scene_index"] + 1  # next_scene_or_finish already incremented
    total = len(state.get("scenes", []))

    if idx < total:
        logger.info("Routing: moving to scene %d/%d", idx + 1, total)
        return "process_scene"

    logger.info("Routing: all %d scenes complete → END", total)
    return END


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(checkpointer=None):
    """
    Build and compile the LangGraph pipeline.

    Args:
        checkpointer: The Langgraph checkpointer instance to use.
    """
    graph = StateGraph(PipelineState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("generate_scenes",       generate_scenes_node)
    graph.add_node("human_approve_scenes",  human_approve_scenes_node)
    graph.add_node("process_scene",         process_scene_node)
    graph.add_node("human_approve_scene",   human_approve_scene_node)
    graph.add_node("optimize_camera",       optimize_camera_node)
    graph.add_node("generate_images",       generate_images_node)
    graph.add_node("generate_videos",       generate_videos_node)
    graph.add_node("next_scene_or_finish",  next_scene_or_finish_node)

    # ── Entry point ───────────────────────────────────────────────────────────
    graph.set_entry_point("generate_scenes")

    # ── Edges ─────────────────────────────────────────────────────────────────
    graph.add_edge("generate_scenes", "human_approve_scenes")

    graph.add_conditional_edges(
        "human_approve_scenes",
        route_after_scenes_approval,
        {
            "generate_scenes": "generate_scenes",
            "process_scene":   "process_scene",
        },
    )

    graph.add_edge("process_scene", "human_approve_scene")

    graph.add_conditional_edges(
        "human_approve_scene",
        route_after_scene_approval,
        {
            "process_scene":   "process_scene",
            "optimize_camera": "optimize_camera",
        },
    )

    graph.add_edge("optimize_camera",      "generate_images")
    graph.add_edge("generate_images",      "generate_videos")
    graph.add_edge("generate_videos",      "next_scene_or_finish")

    graph.add_conditional_edges(
        "next_scene_or_finish",
        route_after_video_generation,
        {
            "process_scene": "process_scene",
            END:             END,
        },
    )

    # ── Checkpointer ─────────────────────────────────────────────────────────
    if checkpointer is None:
        checkpointer = MemorySaver()
        logger.info("Using MemorySaver (in-memory, non-persistent)")

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approve_scenes", "human_approve_scene"],
    )