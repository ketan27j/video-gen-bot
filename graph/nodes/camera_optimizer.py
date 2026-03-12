from langchain_anthropic import ChatAnthropic
from ..state import PipelineState

CAMERA_OPTIMIZER_PROMPT = """
You are a cinematography expert for AI video generation.

Given these video motion prompts from a scene:
{video_prompts}

And this reference list of camera movements:
{camera_moves_reference}

For EACH video prompt, select the most dramatically appropriate camera move from the reference and integrate it into the prompt.
Output one enhanced prompt per line, numbered to match input.
Keep prompts under 100 words each.
"""

async def optimize_camera_node(state: PipelineState) -> PipelineState:
    llm = ChatAnthropic(model="claude-3-5-sonnet-20240620")
    
    scene_index = state["current_scene_index"]
    scene = state["scenes"][scene_index]
    
    with open("prompts/camera_moves.txt", "r") as f:
        camera_moves = f.read()
    
    prompt = CAMERA_OPTIMIZER_PROMPT.format(
        video_prompts="\n".join(scene["video_prompts"]),
        camera_moves_reference=camera_moves
    )
    
    response = await llm.ainvoke(prompt)
    
    # Simple parsing: assume one prompt per line, maybe numbered
    optimized = []
    for line in response.content.strip().split("\n"):
        if "." in line:
             optimized.append(line.split(".", 1)[1].strip())
        else:
             optimized.append(line.strip())
             
    updated_scenes = list(state["scenes"])
    updated_scenes[scene_index] = {
        **scene,
        "optimized_video_prompts": optimized
    }
    
    return {
        **state,
        "scenes": updated_scenes
    }
