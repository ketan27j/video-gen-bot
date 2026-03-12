import os
from .video_browser import GrokVideoGenerator
from ..state import PipelineState

async def generate_videos_node(state: PipelineState) -> PipelineState:
    scene_index = state["current_scene_index"]
    scene = state["scenes"][scene_index]
    
    output_dir = os.getenv("OUTPUT_VIDEOS_DIR", "output/videos")
    gen = GrokVideoGenerator(output_dir)
    
    generated_paths = []
    # Use the first generated image as reference for the video
    image_path = scene["generated_images"][0] if scene["generated_images"] else ""
    
    if image_path:
        for i, prompt in enumerate(scene["optimized_video_prompts"]):
            path = await gen.generate(image_path, prompt, scene["scene_number"], i + 1)
            if path:
                generated_paths.append(path)
            
    updated_scenes = list(state["scenes"])
    updated_scenes[scene_index] = {
        **scene,
        "generated_videos": generated_paths
    }
    
    return {
        **state,
        "scenes": updated_scenes
    }
