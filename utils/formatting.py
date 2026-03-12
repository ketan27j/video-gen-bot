"""
utils/formatting.py
Helpers to format LangGraph state data into clean Telegram messages.
Telegram supports MarkdownV2 — we use a safe subset.
"""

from typing import Dict, List


def _escape(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    specials = r"\_*[]()~`>#+-=|{}.!"
    for c in specials:
        text = text.replace(c, f"\\{c}")
    return text


def format_story_plan(
    story_snapshot: str,
    character_definitions: Dict[str, str],
    scenes: list,
    final_resolution: str,
) -> str:
    """Full story plan message for Telegram approval."""
    lines = []
    lines.append("🎬 *STORY PLAN GENERATED*\n")

    lines.append("📖 *Story Snapshot*")
    lines.append(_escape(story_snapshot))
    lines.append("")

    lines.append("👥 *Characters*")
    for name, desc in character_definitions.items():
        lines.append(f"• *{_escape(name)}*: {_escape(desc[:120])}{'...' if len(desc) > 120 else ''}")
    lines.append("")

    lines.append(f"🎭 *{len(scenes)} Scenes*")
    for scene in scenes:
        scene_num = scene["scene_number"]
        # Extract scene goal line
        scene_text = scene["scene_text"]
        goal_line = ""
        for line in scene_text.splitlines():
            if "goal" in line.lower() or "scene goal" in line.lower():
                goal_line = line.split(":", 1)[-1].strip()
                break
        if not goal_line:
            # Use first non-header line as summary
            for line in scene_text.splitlines()[1:]:
                if line.strip():
                    goal_line = line.strip()[:100]
                    break
        lines.append(f"  *Scene {scene_num}:* {_escape(goal_line)}")
    lines.append("")

    lines.append("🏁 *Final Resolution*")
    lines.append(_escape(final_resolution))

    return "\n".join(lines)


def format_scene_summary(scene: dict) -> str:
    """Format a single scene for Telegram approval."""
    lines = []
    num = scene["scene_number"]
    lines.append(f"🎬 *SCENE {num}*\n")
    lines.append(_escape(scene["scene_text"][:800]))
    if len(scene["scene_text"]) > 800:
        lines.append("_\\.\\.\\. \\(truncated\\)_")
    return "\n".join(lines)


def format_video_script(scene: dict) -> str:
    """Format the video script (image + video prompts) for Telegram approval."""
    lines = []
    num = scene["scene_number"]
    lines.append(f"🎥 *SCENE {num} — VIDEO SCRIPT*\n")

    image_seq = scene.get("image_sequence", [])
    if image_seq:
        lines.append("🖼 *Image Sequence:*")
        for img in image_seq:
            lines.append(
                f"  *Image {img['number']}:* {_escape(img['label'])}\n"
                f"  _{_escape(img['prompt'][:120])}_"
            )
        lines.append("")

    video_prompts = scene.get("video_motion_prompts", [])
    if video_prompts:
        lines.append("🎞 *Video Motion Prompts:*")
        for vp in video_prompts:
            lines.append(
                f"  *Video {vp['number']}* \\({_escape(vp['input_images'])}\\):\n"
                f"  _{_escape(vp['prompt'][:120])}_"
            )

    return "\n".join(lines)


def format_progress(
    current_scene: int,
    total_scenes: int,
    step: str,
) -> str:
    """Progress message during generation."""
    bar_filled = "█" * current_scene
    bar_empty = "░" * (total_scenes - current_scene)
    pct = int((current_scene / total_scenes) * 100)
    return (
        f"⚙️ *Processing Scene {current_scene}/{total_scenes}*\n"
        f"`{bar_filled}{bar_empty}` {pct}%\n\n"
        f"Step: {_escape(step)}"
    )


def format_completion_summary(scenes: list) -> str:
    """Final completion message."""
    total_images = sum(len(s.get("generated_images", [])) for s in scenes)
    total_videos = sum(len(s.get("generated_videos", [])) for s in scenes)

    lines = [
        "✅ *STORYBOARD COMPLETE\\!*\n",
        f"📽 *{len(scenes)} scenes* processed",
        f"🖼 *{total_images} images* generated → `output/images/`",
        f"🎬 *{total_videos} videos* generated → `output/videos/`",
        "",
        "Your AI cartoon is ready\\! 🎉",
    ]
    return "\n".join(lines)