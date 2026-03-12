from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

async def send_story_for_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
    text = f"*Story Snapshot*\n\n{state['story_snapshot']}\n\n*Scenes Found: {len(state['scenes'])}*"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve All", callback_data="approve_all_scenes"),
            InlineKeyboardButton("✏️ Edit Idea", callback_data="edit_idea"),
        ]
    ])
    
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def send_scene_for_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
    scene_index = state["current_scene_index"]
    scene = state["scenes"][scene_index]
    
    text = f"*Scene {scene_index + 1} approval*\n\n{scene['scene_text']}"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_scene_{scene_index}"),
            InlineKeyboardButton("🔄 Regen", callback_data=f"regen_scene_{scene_index}"),
        ]
    ])
    
    # In a real app, you'd use the bot instance from context
    message = update.effective_message
    await message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
