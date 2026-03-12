"""
handlers/conversation.py

Telegram conversation handlers.
Manages the multi-turn conversation flow:
  /start  → ask for movie idea
  idea    → run pipeline, send story plan for approval
  /resume → resume an interrupted pipeline
  /status → show current progress
  /cancel → cancel current pipeline
"""

import logging
import os
import uuid
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode

from graph.pipeline import build_graph
from graph.state import PipelineState
from utils.formatting import (
    format_story_plan,
    format_scene_summary,
    format_video_script,
    format_progress,
    format_completion_summary,
)

logger = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────────
AWAITING_IDEA = 0

# ── Module-level graph instance ───────────────────────────────────────────────
_graph = None
_conn = None
_checkpointer = None


async def get_graph():
    global _graph, _conn, _checkpointer
    if _graph is None:
        use_sqlite = os.getenv("SQLITE_DB_PATH") is not None
        db_path = os.getenv("SQLITE_DB_PATH", "pipeline_state.db")
        if use_sqlite:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            _conn = await aiosqlite.connect(db_path)
            _checkpointer = AsyncSqliteSaver(_conn)
        else:
            from langgraph.checkpoint.memory import MemorySaver
            _checkpointer = MemorySaver()
        _graph = build_graph(_checkpointer)
    return _graph


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _scenes_approval_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve All Scenes", callback_data="approve_scenes"),
            InlineKeyboardButton("🔄 Regenerate Plan",   callback_data="regen_scenes"),
        ]
    ])


def _scene_approval_keyboard(scene_index: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve",     callback_data=f"approve_scene_{scene_index}"),
            InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen_scene_{scene_index}"),
        ],
        [
            InlineKeyboardButton("⏭ Skip Scene",  callback_data=f"skip_scene_{scene_index}"),
        ],
    ])


# ── Helper: run pipeline forward until next interrupt or END ──────────────────

async def _run_pipeline(
    thread_id: str,
    initial_state: Optional[dict] = None,
    chat_id: Optional[int] = None,
    bot=None,
) -> Optional[PipelineState]:
    """
    Advance the pipeline. If initial_state is provided, this is a fresh start.
    Returns the state at the interrupt point, or None if pipeline ended.
    """
    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        if initial_state:
            # Fresh run
            async for event in graph.astream(initial_state, config=config):
                node_name = list(event.keys())[0] if event else "unknown"
                logger.debug("Pipeline event: %s", node_name)

                # Send progress update to user
                if bot and chat_id and node_name not in ("__interrupt__",):
                    await _send_progress_update(bot, chat_id, node_name, event)
        else:
            # Resume from interrupt
            async for event in graph.astream(None, config=config):
                node_name = list(event.keys())[0] if event else "unknown"
                logger.debug("Pipeline event: %s", node_name)

                if bot and chat_id and node_name not in ("__interrupt__",):
                    await _send_progress_update(bot, chat_id, node_name, event)

    except Exception as e:
        logger.error("Pipeline error: %s", e, exc_info=True)
        if bot and chat_id:
            await bot.send_message(
                chat_id,
                f"⚠️ An error occurred: `{str(e)[:200]}`\n\nUse /resume to try again.",
                parse_mode=ParseMode.MARKDOWN,
            )
        return None

    # Get current state snapshot
    state = await graph.aget_state(config)
    return state.values if state else None


async def _send_progress_update(bot, chat_id: int, node_name: str, event: dict):
    """Send a brief status update for each completed node."""
    node_messages = {
        "generate_scenes":       "📝 Generating scene plan\\.\\.\\.",
        "process_scene":         "🎥 Writing video script for scene\\.\\.\\.",
        "optimize_camera":       "🎬 Optimising camera movements\\.\\.\\.",
        "generate_images":       "🖼 Generating images\\.\\.\\.",
        "generate_videos":       "📹 Generating videos\\.\\.\\.",
        "next_scene_or_finish":  "➡️ Moving to next scene\\.\\.\\.",
    }
    msg = node_messages.get(node_name)
    if msg:
        try:
            await bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass


async def _send_scenes_for_approval(bot, chat_id: int, state: PipelineState):
    """Send the full story plan with approval buttons."""
    try:
        text = format_story_plan(
            state.get("story_snapshot", ""),
            state.get("character_definitions", {}),
            state.get("scenes", []),
            state.get("final_resolution", ""),
        )
        await bot.send_message(
            chat_id,
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_scenes_approval_keyboard(),
        )
    except Exception as e:
        logger.error("Error sending scenes for approval: %s", e)
        # Send raw fallback
        await bot.send_message(
            chat_id,
            f"Scene plan generated ({len(state.get('scenes', []))} scenes).\n\nApprove?",
            reply_markup=_scenes_approval_keyboard(),
        )


async def _send_scene_for_approval(bot, chat_id: int, state: PipelineState):
    """Send the current scene's video script with approval buttons."""
    idx = state.get("current_scene_index", 0)
    scenes = state.get("scenes", [])

    if idx >= len(scenes):
        return

    scene = scenes[idx]

    try:
        # Send scene summary
        scene_text = format_scene_summary(scene)
        await bot.send_message(chat_id, scene_text, parse_mode=ParseMode.MARKDOWN_V2)

        # Send video script
        script_text = format_video_script(scene)
        await bot.send_message(
            chat_id,
            script_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_scene_approval_keyboard(idx),
        )
    except Exception as e:
        logger.error("Error sending scene for approval: %s", e)
        await bot.send_message(
            chat_id,
            f"Scene {scene['scene_number']} ready for approval.",
            reply_markup=_scene_approval_keyboard(idx),
        )


# ── Command handlers ──────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start — welcome message."""
    await update.message.reply_text(
        "🎬 *Welcome to AI Storyboard Bot\\!*\n\n"
        "I'll turn your movie idea into a fully generated AI cartoon storyboard\\.\n\n"
        "Tell me your movie idea to get started\\!\n\n"
        "_Example: A lonely robot discovers a flower in a post\\-apocalyptic city "
        "and tries to protect it from a scavenging drone_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return AWAITING_IDEA


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    await update.message.reply_text(
        "🤖 *Storyboard Bot Commands*\n\n"
        "/start \\- Start a new storyboard\n"
        "/resume \\- Resume your last pipeline\n"
        "/status \\- Show current progress\n"
        "/cancel \\- Cancel current pipeline\n"
        "/help \\- Show this message\n\n"
        "*Pipeline steps:*\n"
        "1\\. Send your movie idea\n"
        "2\\. Approve the scene plan\n"
        "3\\. Approve each scene's video script\n"
        "4\\. Images and videos are generated automatically\\!",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel."""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Pipeline cancelled\\. Send /start to begin again\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return ConversationHandler.END


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status — show current pipeline state."""
    thread_id = context.user_data.get("thread_id")
    if not thread_id:
        await update.message.reply_text("No active pipeline\\. Send /start to begin\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = await graph.aget_state(config)

    if not state_snapshot or not state_snapshot.values:
        await update.message.reply_text("Could not retrieve pipeline state\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    state = state_snapshot.values
    scenes = state.get("scenes", [])
    idx = state.get("current_scene_index", 0)
    total = len(scenes)

    msg = format_progress(min(idx, total), total, f"Scene {idx + 1}/{total}")
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resume — resume an interrupted pipeline."""
    thread_id = context.user_data.get("thread_id")
    if not thread_id:
        await update.message.reply_text(
            "No pipeline to resume\\. Send /start to begin\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    await update.message.reply_text("⏯ Resuming pipeline\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = await graph.aget_state(config)

    if not state_snapshot or not state_snapshot.values:
        await update.message.reply_text("Could not resume — no saved state found\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    state = state_snapshot.values
    next_nodes = state_snapshot.next

    # Re-send the appropriate approval message based on where we are
    if "human_approve_scenes" in (next_nodes or []):
        await _send_scenes_for_approval(update.effective_chat._bot, update.effective_chat.id, state)
    elif "human_approve_scene" in (next_nodes or []):
        await _send_scene_for_approval(update.effective_chat._bot, update.effective_chat.id, state)
    else:
        await update.message.reply_text(
            "Pipeline is in an unexpected state\\. Try /start for a fresh run\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ── Movie idea handler ────────────────────────────────────────────────────────

async def receive_movie_idea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the user's movie idea text message — kick off the pipeline."""
    movie_idea = update.message.text.strip()
    chat_id = update.effective_chat.id

    if len(movie_idea) < 10:
        await update.message.reply_text(
            "Please describe your movie idea in a bit more detail \\(at least 10 characters\\)\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return AWAITING_IDEA

    # Generate a unique thread ID for this user's pipeline run
    thread_id = f"{chat_id}_{uuid.uuid4().hex[:8]}"
    context.user_data["thread_id"] = thread_id
    context.user_data["chat_id"] = chat_id

    logger.info("Starting pipeline for chat_id=%s, idea=%s", chat_id, movie_idea[:60])

    await update.message.reply_text(
        f"🎬 *Great idea\\!* Starting your storyboard pipeline\\.\\.\\.\n\n"
        f"_{_escape_md(movie_idea[:100])}_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # Initial state
    initial_state: PipelineState = {
        "movie_idea": movie_idea,
        "chat_id": chat_id,
        "story_snapshot": "",
        "character_definitions": {},
        "scenes": [],
        "final_resolution": "",
        "raw_scene_output": "",
        "current_scene_index": 0,
        "scenes_approved": False,
        "current_scene_approved": False,
        "regenerate_scenes": False,
        "regenerate_current_scene": False,
        "last_error": None,
        "messages": [],
    }

    # Run pipeline until first interrupt (human_approve_scenes)
    state = await _run_pipeline(
        thread_id,
        initial_state=initial_state,
        chat_id=chat_id,
        bot=context.bot,
    )

    if state:
        await _send_scenes_for_approval(context.bot, chat_id, state)

    return ConversationHandler.END


def _escape_md(text: str) -> str:
    specials = r"\_*[]()~`>#+-=|{}.!"
    for c in specials:
        text = text.replace(c, f"\\{c}")
    return text


# ── Callback query handler ────────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = update.effective_chat.id
    thread_id = context.user_data.get("thread_id")

    if not thread_id:
        await query.edit_message_text("Session expired\\. Please send /start to begin again\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # ── Approve all scenes ────────────────────────────────────────────────────
    if data == "approve_scenes":
        await query.edit_message_reply_markup(None)
        await context.bot.send_message(chat_id, "✅ Scene plan approved\\! Processing scenes\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

        await graph.aupdate_state(config, {"scenes_approved": True, "regenerate_scenes": False})
        state = await _run_pipeline(thread_id, chat_id=chat_id, bot=context.bot)

        if state:
            # Check if we stopped at scene approval
            state_snapshot = await graph.aget_state(config)
            if state_snapshot and "human_approve_scene" in (state_snapshot.next or []):
                await _send_scene_for_approval(context.bot, chat_id, state)

    # ── Regenerate scenes ─────────────────────────────────────────────────────
    elif data == "regen_scenes":
        await query.edit_message_reply_markup(None)
        await context.bot.send_message(chat_id, "🔄 Regenerating scene plan\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

        await graph.aupdate_state(config, {"regenerate_scenes": True, "scenes_approved": False})
        state = await _run_pipeline(thread_id, chat_id=chat_id, bot=context.bot)

        if state:
            await _send_scenes_for_approval(context.bot, chat_id, state)

    # ── Approve scene ─────────────────────────────────────────────────────────
    elif data.startswith("approve_scene_"):
        scene_idx = int(data.split("_")[-1])
        await query.edit_message_reply_markup(None)
        await context.bot.send_message(
            chat_id,
            f"✅ Scene {scene_idx + 1} approved\\! Generating\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        await graph.aupdate_state(config, {"current_scene_approved": True, "regenerate_current_scene": False})
        state = await _run_pipeline(thread_id, chat_id=chat_id, bot=context.bot)

        if state:
            state_snapshot = await graph.aget_state(config)
            next_nodes = state_snapshot.next if state_snapshot else []

            if state_snapshot and "human_approve_scene" in (next_nodes or []):
                # Next scene ready
                await _send_scene_for_approval(context.bot, chat_id, state)
            elif not next_nodes:
                # Pipeline complete
                scenes = state.get("scenes", [])
                await context.bot.send_message(
                    chat_id,
                    format_completion_summary(scenes),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

    # ── Regenerate current scene ──────────────────────────────────────────────
    elif data.startswith("regen_scene_"):
        scene_idx = int(data.split("_")[-1])
        await query.edit_message_reply_markup(None)
        await context.bot.send_message(
            chat_id,
            f"🔄 Regenerating scene {scene_idx + 1}\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        await graph.aupdate_state(config, {"regenerate_current_scene": True, "current_scene_approved": False})
        state = await _run_pipeline(thread_id, chat_id=chat_id, bot=context.bot)

        if state:
            state_snapshot = await graph.aget_state(config)
            if state_snapshot and "human_approve_scene" in (state_snapshot.next or []):
                await _send_scene_for_approval(context.bot, chat_id, state)

    # ── Skip scene ────────────────────────────────────────────────────────────
    elif data.startswith("skip_scene_"):
        scene_idx = int(data.split("_")[-1])
        await query.edit_message_reply_markup(None)
        await context.bot.send_message(
            chat_id,
            f"⏭ Skipping scene {scene_idx + 1}\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        # Mark scene as skipped and approved to advance
        graph_state = await graph.aget_state(config)
        if graph_state and graph_state.values:
            scenes = list(graph_state.values.get("scenes", []))
            if scene_idx < len(scenes):
                scene = dict(scenes[scene_idx])
                scene["skip"] = True
                scenes[scene_idx] = scene
            await graph.aupdate_state(config, {"scenes": scenes, "current_scene_approved": True})

        state = await _run_pipeline(thread_id, chat_id=chat_id, bot=context.bot)

        if state:
            state_snapshot = await graph.aget_state(config)
            next_nodes = state_snapshot.next if state_snapshot else []
            if "human_approve_scene" in (next_nodes or []):
                await _send_scene_for_approval(context.bot, chat_id, state)
            elif not next_nodes:
                scenes = state.get("scenes", [])
                await context.bot.send_message(
                    chat_id,
                    format_completion_summary(scenes),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

    else:
        logger.warning("Unknown callback data: %s", data)


# ── ConversationHandler builder ───────────────────────────────────────────────

def build_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            AWAITING_IDEA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_movie_idea)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
    )