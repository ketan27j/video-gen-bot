import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from graph.pipeline import build_graph
from handlers.conversation import send_story_for_approval
from handlers.callbacks import button_callback

load_dotenv()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Welcome to the AI Storyboard Bot!*\n\n"
        "Send me a movie idea, and I'll generate a full storyboard for you.\n"
        "I'll use LangGraph for orchestration and Playwright for browser automation.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movie_idea = update.message.text
    chat_id = update.effective_chat.id
    
    await update.message.reply_text("🚀 Projecting your movie idea into scenes... please wait.")
    
    graph = context.bot_data["graph"]
    config = {"configurable": {"thread_id": str(chat_id)}}
    
    # Start the graph
    initial_state = {
        "movie_idea": movie_idea,
        "chat_id": chat_id,
        "messages": []
    }
    
    # Run until first interrupt
    async for _ in graph.astream(initial_state, config, stream_mode="values"):
        pass
    
    # Get current state and send for approval
    state = graph.get_state(config).values
    await send_story_for_approval(update, context, state)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        return

    db_path = os.getenv("SQLITE_DB_PATH", "pipeline_state.db")
    graph = build_graph(db_path)

    app = ApplicationBuilder().token(token).build()
    
    # Store graph in bot_data for access in handlers
    app.bot_data["graph"] = graph

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
