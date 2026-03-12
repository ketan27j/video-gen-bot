"""
graph/state.py
Defines the shared pipeline state used by all LangGraph nodes.
"""

from typing import TypedDict, List, Optional, Annotated, Dict
from langgraph.graph.message import add_messages


class SceneData(TypedDict):
    """Data for one scene, built up progressively through the pipeline."""
    scene_number: int
    scene_text: str                   # Raw scene block from prompt 1 output
    characters_present: List[str]     # Character names extracted for this scene
    character_descriptions: Dict[str, str]  # { name: description } filtered for scene

    # From Agent 2 (video_gen)
    character_image_prompts: List[str]    # Section 1 outputs
    image_sequence: List[Dict]            # Section 2: [{label, prompt}, ...]
    video_motion_prompts: List[Dict]      # Section 3: [{input_images, prompt}, ...]

    # From Agent 3 (camera optimizer)
    optimized_video_prompts: List[str]

    # From browser automation
    generated_images: List[str]       # Local file paths  e.g. output/images/scene_01_image_01.png
    generated_videos: List[str]       # Local file paths  e.g. output/videos/scene_01_video_01.mp4

    # Human-in-the-loop
    approved: bool
    skip: bool


class PipelineState(TypedDict):
    """
    Full pipeline state threaded through all LangGraph nodes.
    Persisted via SqliteSaver so the bot can resume after restarts.
    """
    # ── Input ─────────────────────────────────────────────────────────────────
    movie_idea: str
    chat_id: int                          # Telegram chat ID

    # ── Agent 1 outputs ───────────────────────────────────────────────────────
    story_snapshot: str
    character_definitions: Dict[str, str] # { character_name: full_description }
    scenes: List[SceneData]
    final_resolution: str
    raw_scene_output: str                 # Full raw text from Agent 1

    # ── Processing cursor ─────────────────────────────────────────────────────
    current_scene_index: int

    # ── Human checkpoint flags ────────────────────────────────────────────────
    scenes_approved: bool                 # Overall scene plan approved
    current_scene_approved: bool          # Current scene script approved
    regenerate_scenes: bool               # User asked to regenerate full plan
    regenerate_current_scene: bool        # User asked to regenerate this scene

    # ── Error tracking ────────────────────────────────────────────────────────
    last_error: Optional[str]

    # ── LLM message history (for context) ─────────────────────────────────────
    messages: Annotated[list, add_messages]