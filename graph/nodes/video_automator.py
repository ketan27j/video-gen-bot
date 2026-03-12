import os
from automation.video_browser import get_video_generator
from ..state import PipelineState

async def generate_videos_node(state: PipelineState) -> PipelineState:
    scene_index = state["current_scene_index"]
    scene = state["scenes"][scene_index]
    
    output_dir = os.getenv("OUTPUT_VIDEOS_DIR", "output/videos")
    gen = get_video_generator()
    await gen.start()
    
    generated_paths = []
    image_path = scene["generated_images"][0] if scene["generated_images"] else ""
    
    if image_path:
        for i, prompt in enumerate(scene["optimized_video_prompts"]):
            output_path = os.path.join(output_dir, f"scene_{scene['scene_number']}_video_{i + 1}.mp4")
            path = await gen.generate(image_path, prompt, output_path)
            if path:
                generated_paths.append(path)
    
    await gen.stop()
            
    updated_scenes = list(state["scenes"])
    updated_scenes[scene_index] = {
        **scene,
        "generated_videos": generated_paths
    }
    
    return {
        **state,
        "scenes": updated_scenes
    }