import re
from langchain_anthropic import ChatAnthropic
from ..state import PipelineState

def parse_prompts(content: str):
    image_prompts = []
    video_prompts = []
    
    image_section = re.search(r"SECTION 2: IMAGE PROMPTS(.*?)(?=SECTION 3:|$)", content, re.DOTALL)
    if image_section:
        image_prompts = [line.split(".", 1)[1].strip() for line in image_section.group(1).strip().split("\n") if "." in line]
        
    video_section = re.search(r"SECTION 3: VIDEO PROMPTS(.*?)$", content, re.DOTALL)
    if video_section:
        video_prompts = [line.split(".", 1)[1].strip() for line in video_section.group(1).strip().split("\n") if "." in line]
        
    return image_prompts, video_prompts

async def video_scripter_node(state: PipelineState) -> PipelineState:
    llm = ChatAnthropic(model="claude-3-5-sonnet-20240620")
    
    scene_index = state["current_scene_index"]
    scene = state["scenes"][scene_index]
    
    with open("prompts/video_gen.txt", "r") as f:
        prompt_template = f.read()
    
    prompt = prompt_template.format(
        scene_text=scene["scene_text"],
        character_definitions=state["character_definitions"],
        characters_present=", ".join(scene["characters_present"])
    )
    
    response = await llm.ainvoke(prompt)
    
    image_prompts, video_prompts = parse_prompts(response.content)
    
    # Update the specific scene in the state
    updated_scenes = list(state["scenes"])
    updated_scenes[scene_index] = {
        **scene,
        "image_prompts": image_prompts,
        "video_prompts": video_prompts,
        "current_scene_approved": False
    }
    
    return {
        **state,
        "scenes": updated_scenes
    }
