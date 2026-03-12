from telegram import Update
from telegram.ext import ContextTypes
from .conversation import send_scene_for_approval

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    graph = context.bot_data["graph"]
    
    config = {"configurable": {"thread_id": str(chat_id)}}
    
    if data == "approve_all_scenes":
        await query.edit_message_text(text="✅ Story approved! Starting scene processing...")
        # Update state and resume
        graph.update_state(config, {"scenes_approved": True})
        # Note: In a production bot, you'd run this in a background task
        async for _ in graph.astream(None, config, stream_mode="values"):
            pass
        
        # After resuming, the graph will hit the next interrupt (scene approval)
        new_state = graph.get_state(config).values
        from .conversation import send_scene_for_approval
        await send_scene_for_approval(update, context, new_state)

    elif data.startswith("approve_scene_"):
        scene_index = int(data.split("_")[-1])
        await query.edit_message_text(text=f"✅ Scene {scene_index + 1} approved! Generating image/video...")
        
        graph.update_state(config, {"current_scene_approved": True})
        
        async for _ in graph.astream(None, config, stream_mode="values"):
             pass
             
        # Check next state
        new_state = graph.get_state(config).values
        if new_state["current_scene_index"] < len(new_state["scenes"]):
             await send_scene_for_approval(update, context, new_state)
        else:
             await query.message.reply_text("🎬 All scenes complete! Check your /output folder.")
