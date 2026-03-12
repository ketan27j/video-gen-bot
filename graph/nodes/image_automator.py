import os
from .image_browser import ImageGenerator
from ..state import PipelineState

async def generate_images_node(state: PipelineState) -> PipelineState:
    scene_index = state["current_scene_index"]
    scene = state["scenes"][scene_index]
    
    output_dir = os.getenv("OUTPUT_IMAGES_DIR", "output/images")
    gen = ImageGenerator(output_dir)
    
    generated_paths = []
    for i, prompt in enumerate(scene["image_prompts"]):
        path = await gen.generate(prompt, scene["scene_number"], i + 1)
        if path:
            generated_paths.append(path)
            
    updated_scenes = list(state["scenes"])
    updated_scenes[scene_index] = {
        **scene,
        "generated_images": generated_paths
    }
    
    return {
        **state,
        "scenes": updated_scenes
    }
