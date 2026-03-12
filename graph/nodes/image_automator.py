import os
from automation.image_browser import get_image_generator
from graph.state import PipelineState

async def generate_images_node(state: PipelineState) -> PipelineState:
    scene_index = state["current_scene_index"]
    scene = state["scenes"][scene_index]
    
    output_dir = os.getenv("OUTPUT_IMAGES_DIR", "output/images")
    gen = get_image_generator()
    await gen.start()
    
    generated_paths = []
    for i, prompt in enumerate(scene["image_prompts"]):
        output_path = os.path.join(output_dir, f"scene_{scene['scene_number']}_image_{i + 1}.png")
        path = await gen.generate(prompt, output_path)
        if path:
            generated_paths.append(path)
    
    await gen.stop()
            
    updated_scenes = list(state["scenes"])
    updated_scenes[scene_index] = {
        **scene,
        "generated_images": generated_paths
    }
    
    return {
        **state,
        "scenes": updated_scenes
    }
