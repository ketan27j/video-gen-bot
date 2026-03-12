"""
tests/test_pipeline_mock.py

Integration test for the full LangGraph pipeline using a mocked LLM.
No real API calls, no browser automation.

Run with: python tests/test_pipeline_mock.py
"""

import asyncio
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up minimal env
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("IMAGE_GEN_TOOL", "manual")
os.environ.setdefault("VIDEO_GEN_TOOL", "manual")


MOCK_SCENE_OUTPUT = """
STEP 1: STORY SNAPSHOT
A tiny wizard discovers a lost dragon egg and returns it home.

STEP 2: CHARACTER DEFINITIONS
WIZARD / Hero
A small elderly wizard with a long blue robe, white beard, pointy hat. Warm and adventurous vibe.

DRAGON EGG / MacGuffin
A glowing purple egg with golden swirls, about the size of a watermelon.

STEP 3: SCENE BREAKDOWN

SCENE 1:
Scene goal: Discovery and wonder
Location / environment: Ancient forest, dappled sunlight
Characters present: WIZARD
Start state: WIZARD walks through misty forest path
End state: WIZARD finds glowing dragon egg in hollow tree
Key actions:
- WIZARD walks along forest path
- Notices strange glow from hollow tree
- Discovers the egg, eyes wide with wonder

SCENE 2:
Scene goal: Danger and urgency
Location / environment: Rocky mountain pass, storm brewing
Characters present: WIZARD, DRAGON EGG
Start state: WIZARD carries egg up mountain
End state: WIZARD reaches dragon's lair with egg safe
Key actions:
- WIZARD climbs perilous path
- Storm intensifies around mountain
- WIZARD pushes forward despite obstacles

STEP 4: FINAL RESOLUTION
WIZARD places the egg in the dragon's nest as it begins to hatch, and the mother dragon bows her head in gratitude.
"""

MOCK_VIDEO_OUTPUT = """
SECTION 1: CHARACTER IMAGE PROMPTS
WIZARD: An elderly wizard in a long blue robe with white beard and pointy blue hat, neutral standing pose, full body shot, soft forest lighting, cartoon animation style.

SECTION 2: SCENE IMAGE SEQUENCE

IMAGE 1:
Wizard enters the forest
Wide shot of WIZARD walking into misty ancient forest, dappled sunlight filtering through tall trees, warm green tones, medium-wide angle from behind.

IMAGE 2:
Wizard discovers the egg
Medium shot of WIZARD crouching before a hollow tree, face illuminated by purple-golden glow from within, expression of wonder and surprise.

IMAGE 3:
Wizard holds the egg
Close-up of WIZARD carefully cradling the glowing dragon egg in both hands, looking at it with reverence, soft warm bokeh forest background.

SECTION 3: VIDEO MOTION PROMPTS

VIDEO PROMPT 1:
Input image(s): Use IMAGE 1
WIZARD walks forward through the forest path. Camera follows from behind using a forward tracking follow shot.

VIDEO PROMPT 2:
Input image(s): Use IMAGE 2 as start, IMAGE 3 as end
WIZARD leans toward the hollow tree, the glow intensifying. Camera performs a slow dolly in to emphasize discovery.
"""

MOCK_CAMERA_OUTPUT = """
PROMPT 1: Forward tracking follow shot, shoulder-height, stabilized; the camera advances behind WIZARD as he walks deeper into the misty ancient forest, matching his gentle pace and sustaining perspective through dappled shafts of morning light filtering between tall trees.

PROMPT 2: SLOW DOLLY IN toward WIZARD as he discovers the dragon egg, the camera gliding forward on a track, the purple-golden glow expanding in warmth and intensity as WIZARD reaches into the hollow tree with trembling, reverent hands.
"""


async def run_mock_pipeline():
    """Run the full pipeline graph with mocked LLM and image/video generators."""

    from graph.pipeline import build_graph

    graph = build_graph(use_sqlite=False)

    mock_llm_response_scene = MagicMock()
    mock_llm_response_scene.content = MOCK_SCENE_OUTPUT

    mock_llm_response_video = MagicMock()
    mock_llm_response_video.content = MOCK_VIDEO_OUTPUT

    mock_llm_response_camera = MagicMock()
    mock_llm_response_camera.content = MOCK_CAMERA_OUTPUT

    call_count = [0]

    async def mock_ainvoke(messages):
        call_count[0] += 1
        prompt_text = str(messages[-1].content) if messages else ""
        # Route based on prompt content
        if "animation planner" in prompt_text or "movie-idea" in prompt_text.lower() or "movie idea" in prompt_text.lower():
            return mock_llm_response_scene
        elif "cinematography expert" in prompt_text or "camera move" in prompt_text.lower():
            return mock_llm_response_camera
        else:
            return mock_llm_response_video

    with patch("utils.llm.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_ainvoke
        mock_get_llm.return_value = mock_llm

        # Also mock image/video generators
        async def mock_image_gen(prompt, output_path):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"FAKE_PNG_DATA")
            return output_path

        async def mock_video_gen(image_path, prompt, output_path):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"FAKE_MP4_DATA")
            return output_path

        mock_img_generator = MagicMock()
        mock_img_generator.start = AsyncMock()
        mock_img_generator.stop = AsyncMock()
        mock_img_generator.generate = mock_image_gen

        mock_vid_generator = MagicMock()
        mock_vid_generator.start = AsyncMock()
        mock_vid_generator.stop = AsyncMock()
        mock_vid_generator.generate = mock_video_gen

        with patch("automation.image_browser.get_image_generator", return_value=mock_img_generator):
            with patch("automation.video_browser.get_video_generator", return_value=mock_vid_generator):

                initial_state = {
                    "movie_idea": "A tiny wizard discovers a lost dragon egg and returns it home",
                    "chat_id": 12345,
                    "story_snapshot": "",
                    "character_definitions": {},
                    "scenes": [],
                    "final_resolution": "",
                    "raw_scene_output": "",
                    "current_scene_index": 0,
                    "scenes_approved": False,
                    "current_scene_approved": False,
                    "regenerate_scenes": False,
                    "regenerate_current_scene": False,
                    "last_error": None,
                    "messages": [],
                }

                thread_id = "test_thread_001"
                config = {"configurable": {"thread_id": thread_id}}

                print("\n🚀 Starting pipeline...")

                # Step 1: Run until first interrupt (human_approve_scenes)
                events = []
                async for event in graph.astream(initial_state, config=config):
                    events.append(event)
                    print(f"  Event: {list(event.keys())[0]}")

                state_snapshot = graph.get_state(config)
                state = state_snapshot.values
                print(f"\n✅ Scenes generated: {len(state.get('scenes', []))}")
                print(f"   Story: {state.get('story_snapshot', '')[:80]}")
                print(f"   Characters: {list(state.get('character_definitions', {}).keys())}")
                print(f"   Interrupted at: {state_snapshot.next}")

                assert len(state.get("scenes", [])) == 2, "Expected 2 scenes"
                assert "human_approve_scenes" in state_snapshot.next

                # Step 2: Simulate user approving scenes
                print("\n👤 User approves scene plan...")
                graph.update_state(config, {"scenes_approved": True})

                async for event in graph.astream(None, config=config):
                    events.append(event)
                    print(f"  Event: {list(event.keys())[0]}")

                state_snapshot = graph.get_state(config)
                state = state_snapshot.values
                print(f"\n✅ Scene 1 script generated")
                print(f"   Images: {len(state['scenes'][0].get('image_sequence', []))}")
                print(f"   Video prompts: {len(state['scenes'][0].get('video_motion_prompts', []))}")
                print(f"   Interrupted at: {state_snapshot.next}")
                assert "human_approve_scene" in state_snapshot.next

                # Step 3: Simulate user approving scene 1
                print("\n👤 User approves scene 1...")
                graph.update_state(config, {"current_scene_approved": True})

                async for event in graph.astream(None, config=config):
                    events.append(event)
                    print(f"  Event: {list(event.keys())[0]}")

                state_snapshot = graph.get_state(config)
                state = state_snapshot.values
                print(f"\n✅ Scene 1 images: {state['scenes'][0].get('generated_images', [])}")
                print(f"   Scene 1 videos: {state['scenes'][0].get('generated_videos', [])}")
                print(f"   Next: {state_snapshot.next}")

                # Step 4: Approve scene 2
                if "human_approve_scene" in (state_snapshot.next or []):
                    print("\n👤 User approves scene 2...")
                    graph.update_state(config, {"current_scene_approved": True})

                    async for event in graph.astream(None, config=config):
                        events.append(event)
                        print(f"  Event: {list(event.keys())[0]}")

                    state_snapshot = graph.get_state(config)
                    state = state_snapshot.values

                # Final checks
                all_images = [img for s in state["scenes"] for img in s.get("generated_images", [])]
                all_videos = [vid for s in state["scenes"] for vid in s.get("generated_videos", [])]

                print(f"\n🎉 PIPELINE COMPLETE!")
                print(f"   Total images: {len(all_images)}")
                print(f"   Total videos: {len(all_videos)}")
                print(f"   LLM calls made: {call_count[0]}")
                print(f"   Final state next: {state_snapshot.next}")

                assert len(all_images) > 0, "Expected generated images"
                assert len(all_videos) > 0, "Expected generated videos"

                print("\n✅ All assertions passed!")


if __name__ == "__main__":
    asyncio.run(run_mock_pipeline())