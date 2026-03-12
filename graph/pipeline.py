from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from .state import PipelineState

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from .state import PipelineState

from .nodes.scene_generator import generate_scenes_node
from .nodes.video_scripter import video_scripter_node
from .nodes.camera_optimizer import optimize_camera_node
from .nodes.image_automator import generate_images_node
from .nodes.video_automator import generate_videos_node

# These are state-management nodes that mostly act as pass-throughs for interrupts
async def human_approve_scenes_node(state: PipelineState) -> PipelineState:
    return state

async def human_approve_scene_node(state: PipelineState) -> PipelineState:
    return state

async def next_scene_or_finish_node(state: PipelineState) -> PipelineState:
    return {
        **state,
        "current_scene_index": state["current_scene_index"] + 1
    }

def build_graph(db_path: str = "pipeline_state.db"):
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("generate_scenes",        generate_scenes_node)
    graph.add_node("human_approve_scenes",   human_approve_scenes_node)
    graph.add_node("process_scene",          video_scripter_node) # video_scripter_node handles current scene scripting
    graph.add_node("human_approve_scene",    human_approve_scene_node)
    graph.add_node("optimize_camera",        optimize_camera_node)
    graph.add_node("generate_images",        generate_images_node)
    graph.add_node("generate_videos",        generate_videos_node)
    graph.add_node("next_scene_or_finish",   next_scene_or_finish_node)

    # Set entry point
    graph.set_entry_point("generate_scenes")

    # Define edges
    graph.add_edge("generate_scenes", "human_approve_scenes")

    graph.add_conditional_edges(
        "human_approve_scenes",
        lambda s: "process_scene" if s.get("scenes_approved") else "generate_scenes"
    )

    graph.add_edge("process_scene", "human_approve_scene")

    graph.add_conditional_edges(
        "human_approve_scene",
        lambda s: "optimize_camera" if s.get("current_scene_approved") else "process_scene"
    )

    graph.add_edge("optimize_camera",       "generate_images")
    graph.add_edge("generate_images",       "generate_videos")
    graph.add_edge("generate_videos",       "next_scene_or_finish")

    graph.add_conditional_edges(
        "next_scene_or_finish",
        lambda s: "process_scene" if s["current_scene_index"] < len(s["scenes"]) else END
    )

    checkpointer = SqliteSaver.from_conn_string(db_path)
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approve_scenes", "human_approve_scene"]
    )
