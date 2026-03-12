"""
tests/test_parsers.py
Unit tests for the LLM output parsers (no LLM calls needed).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from graph.nodes.scene_generator import (
    _parse_characters,
    _parse_scenes,
    _parse_story_snapshot,
    _parse_final_resolution,
)
from graph.nodes.video_scripter import (
    _parse_character_image_prompts,
    _parse_image_sequence,
    _parse_video_motion_prompts,
)
from graph.nodes.camera_optimizer import _parse_optimized_prompts


SAMPLE_SCENE_OUTPUT = """
STEP 1: STORY SNAPSHOT
A lonely robot finds a flower and protects it from a scavenging drone.

STEP 2: CHARACTER DEFINITIONS
RUSTY / Main character
A small, round robot with rusty orange panels, wide glowing blue eyes, stubby arms. Wears no clothing. Gentle, curious vibe.

DRONE / Antagonist
A sleek black quadcopter with red sensor eyes, sharp metal claws underneath. Menacing and mechanical.

STEP 3: SCENE BREAKDOWN

SCENE 1:
Scene goal: Establish loneliness and discovery
Location / environment: Ruined grey city, collapsed buildings, dust everywhere
Characters present: RUSTY
Start state: RUSTY wanders alone through rubble
End state: RUSTY spots a tiny flower glowing in a crack
Key actions:
- RUSTY trudges through debris
- Camera reveals vast emptiness
- RUSTY freezes, noticing a soft glow

SCENE 2:
Scene goal: Threat arrives — tension escalates
Location / environment: Same ruined street, dark storm clouds gathering
Characters present: RUSTY, DRONE
Start state: RUSTY protects the flower
End state: DRONE hovers menacingly overhead
Key actions:
- DRONE appears on horizon
- RUSTY tries to hide the flower
- Standoff as DRONE descends

STEP 4: FINAL RESOLUTION
RUSTY successfully drives away the DRONE and the flower blooms in the sunlight.
"""


SAMPLE_VIDEO_OUTPUT = """
SECTION 1: CHARACTER IMAGE PROMPTS
RUSTY: A small round robot with rusty orange panels, wide glowing blue eyes, stubby arms, standing in neutral pose, full body, soft studio lighting, cartoon style.

DRONE: A sleek black quadcopter with red sensor eyes, sharp claws, hovering at neutral height, full body, dramatic lighting, cartoon style.

SECTION 2: SCENE IMAGE SEQUENCE

IMAGE 1:
RUSTY discovers the flower
Wide shot of RUSTY crouching in rubble, back to camera, a tiny glowing flower visible in a crack in the ground, grey desolate city background, soft warm light on the flower, medium-wide angle.

IMAGE 2:
Close-up of the flower
Macro shot of the delicate white flower glowing faintly, RUSTY's hand reaching toward it gently, shallow depth of field, warm bokeh background.

IMAGE 3:
RUSTY holds the flower protectively
Medium shot of RUSTY cradling the flower, looking up with wide eyes, dark storm clouds forming in background, dramatic light contrast.

SECTION 3: VIDEO MOTION PROMPTS

VIDEO PROMPT 1:
Input image(s): Use IMAGE 1
RUSTY slowly turns from the rubble toward the flower, tilting his head in curiosity. Camera performs a slow dolly in.

VIDEO PROMPT 2:
Input image(s): Use IMAGE 2 as start, IMAGE 3 as end
Camera pulls back from macro flower shot to reveal RUSTY picking it up gently.
"""


SAMPLE_CAMERA_OUTPUT = """
PROMPT 1: SLOW DOLLY IN on RUSTY as he slowly turns toward the glowing flower in the rubble, the grey desolate city gradually expanding in depth behind him, warm light blooming from the crack in the ground, emphasizing his quiet sense of wonder. Camera glides forward on a track toward RUSTY.

PROMPT 2: SLOW DOLLY OUT from a macro shot of the delicate flower to reveal RUSTY gently lifting it from the rubble, the vast empty city unveiling behind him as the camera smoothly tracks backward, reducing the flower's screen presence while exposing the world around it.
"""


def test_parse_story_snapshot():
    result = _parse_story_snapshot(SAMPLE_SCENE_OUTPUT)
    assert "lonely robot" in result.lower()


def test_parse_final_resolution():
    result = _parse_final_resolution(SAMPLE_SCENE_OUTPUT)
    assert "rusty" in result.lower() or "drone" in result.lower()


def test_parse_characters():
    chars = _parse_characters(SAMPLE_SCENE_OUTPUT)
    assert len(chars) >= 1
    names = [k.upper() for k in chars.keys()]
    assert any("RUSTY" in n for n in names)


def test_parse_scenes():
    scenes = _parse_scenes(SAMPLE_SCENE_OUTPUT)
    assert len(scenes) == 2
    assert scenes[0]["scene_number"] == 1
    assert scenes[1]["scene_number"] == 2
    # Scene 1 should have RUSTY only
    assert any("RUSTY" in c.upper() for c in scenes[0]["characters_present"])
    # Scene 2 should have both
    assert len(scenes[1]["characters_present"]) >= 1


def test_parse_character_image_prompts():
    prompts = _parse_character_image_prompts(SAMPLE_VIDEO_OUTPUT)
    assert len(prompts) >= 1
    assert any("robot" in p.lower() or "rusty" in p.lower() for p in prompts)


def test_parse_image_sequence():
    images = _parse_image_sequence(SAMPLE_VIDEO_OUTPUT)
    assert len(images) == 3
    assert images[0]["number"] == 1
    assert images[1]["number"] == 2
    assert "flower" in images[0]["prompt"].lower() or "flower" in images[0]["label"].lower()


def test_parse_video_motion_prompts():
    prompts = _parse_video_motion_prompts(SAMPLE_VIDEO_OUTPUT)
    assert len(prompts) == 2
    assert prompts[0]["number"] == 1
    assert "IMAGE 1" in prompts[0]["input_images"]
    assert prompts[1]["number"] == 2


def test_parse_optimized_prompts():
    result = _parse_optimized_prompts(SAMPLE_CAMERA_OUTPUT, expected_count=2)
    assert len(result) == 2
    assert "dolly" in result[0].lower()
    assert len(result[1]) > 10


if __name__ == "__main__":
    test_parse_story_snapshot()
    test_parse_final_resolution()
    test_parse_characters()
    test_parse_scenes()
    test_parse_character_image_prompts()
    test_parse_image_sequence()
    test_parse_video_motion_prompts()
    test_parse_optimized_prompts()
    print("✅ All parser tests passed!")