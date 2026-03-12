import re
from typing import List, Dict
from langchain_anthropic import ChatAnthropic
from ..state import PipelineState, SceneData

def parse_scenes(content: str) -> (str, Dict[str, str], List[SceneData]):
    # Very basic parser for the sake of initial implementation
    # In a real scenario, this would be more robust (e.g. using PydanticOutputParser)
    
    story_snapshot = ""
    character_definitions = {}
    scenes = []

    # Extract Story Snapshot
    snapshot_match = re.search(r"\*\*Story Snapshot\*\*:(.*?)(?=\*\*Character Definitions\*\*|$)", content, re.DOTALL)
    if snapshot_match:
        story_snapshot = snapshot_match.group(1).strip()

    # Extract Character Definitions
    char_match = re.search(r"\*\*Character Definitions\*\*:(.*?)(?=\*\*Scene Breakdown\*\*|$)", content, re.DOTALL)
    if char_match:
        chars_text = char_match.group(1).strip()
        for line in chars_text.split("\n"):
            if ":" in line:
                name, desc = line.split(":", 1)
                character_definitions[name.strip("- ").strip()] = desc.strip()

    # Extract Scenes
    scene_matches = re.finditer(r"- Scene Number: (\d+).*?- Setting: (.*?)- Detailed Description: (.*?)- Characters Present: (.*?)(?=- Scene Number:|$)", content, re.DOTALL)
    for match in scene_matches:
        num = int(match.group(1))
        setting = match.group(2).strip()
        desc = match.group(3).strip()
        chars = [c.strip() for c in match.group(4).split(",")]
        
        scenes.append({
            "scene_number": num,
            "scene_text": f"Setting: {setting}\n\nDescription: {desc}",
            "characters_present": chars,
            "image_prompts": [],
            "video_prompts": [],
            "optimized_video_prompts": [],
            "generated_images": [],
            "generated_videos": [],
            "approved": False
        })

    return story_snapshot, character_definitions, scenes

async def generate_scenes_node(state: PipelineState) -> PipelineState:
    llm = ChatAnthropic(model="claude-3-5-sonnet-20240620") # Standard version
    
    with open("prompts/char_scene_gen.txt", "r") as f:
        prompt_template = f.read()
    
    prompt = prompt_template.format(movie_idea=state["movie_idea"])
    response = await llm.ainvoke(prompt)
    
    story, chars, scenes = parse_scenes(response.content)
    
    return {
        **state,
        "story_snapshot": story,
        "character_definitions": chars,
        "scenes": scenes,
        "current_scene_index": 0,
        "scenes_approved": False
    }
