import os
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types import Update
from pytgcalls.types.input_stream import AudioPiped
from pytgcalls.types.input_stream.quality import HighQualityAudio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from config import API_ID, API_HASH, BOT_TOKEN, SESSION_STRING, OWNER_ID

# Configuration (you should put these in a config.py file)
"""
API_ID = 123456  # Your API ID from my.telegram.org
API_HASH = "your_api_hash"  # Your API Hash from my.telegram.org
BOT_TOKEN = "your_bot_token"  # Your bot token from @BotFather
SESSION_STRING = "your_session_string"  # Generate this with generate_session.py
OWNER_ID = 123456789  # Your user ID
"""

# Initialize clients
bot = Client(
    "RocksMusicBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

telethon_client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH
)

pytgcalls = PyTgCalls(telethon_client)

# Queue and state management
queues = {}
current = {}

# Helper functions
async def get_youtube_stream(url: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
        'extract_flat': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        return info['url'], info['title'], info['duration']

async def play_next_song(chat_id: int):
    if chat_id in queues and len(queues[chat_id]) > 0:
        url, title, duration = queues[chat_id].pop(0)
        current[chat_id] = (url, title, duration)
        
        await pytgcalls.change_stream(
            chat_id,
            AudioPiped(url, HighQualityAudio())
        )
        
        return title
    else:
        if chat_id in current:
            del current[chat_id]
        return None

# PyTgCalls event handlers
@pytgcalls.on_stream_end()
async def on_stream_end(client: PyTgCalls, update: Update):
    chat_id = update.chat_id
    await play_next_song(chat_id)

@pytgcalls.on_closed_voice_chat()
async def on_closed(client: PyTgCalls, chat_id: int):
    if chat_id in queues:
        del queues[chat_id]
    if chat_id in current:
        del current[chat_id]

# Telegram command handlers
@bot.on_message(filters.command("start"))
async def start(_, message: Message):
    await message.reply_text(
        "🎵 **Rocks Music Bot**\n\n"
        "I can play music in your Telegram voice chats!\n\n"
        "**Commands:**\n"
        "/play [url/query] - Play a song from YouTube\n"
        "/skip - Skip the current song\n"
        "/pause - Pause the playback\n"
        "/resume - Resume the playback\n"
        "/stop - Stop the playback and clear queue\n"
        "/volume [1-200] - Adjust volume\n"
        "/queue - Show current queue\n"
        "/nowplaying - Show currently playing song\n\n"
        "Created with ❤️ by @RocksMusicBot",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Support", url="https://t.me/RocksSupport")]
        ])
    )

@bot.on_message(filters.command("play") & filters.group)
async def play(_, message: Message):
    if not message.from_user:
        return
    
    if len(message.command) < 2:
        await message.reply_text("❌ Please provide a YouTube URL or search query.")
        return
    
    query = " ".join(message.command[1:])
    
    if not message.chat.id in queues:
        queues[message.chat.id] = []
    
    try:
        if not query.startswith("http"):
            query = f"ytsearch:{query}"
        
        stream_url, title, duration = await get_youtube_stream(query)
        
        if pytgcalls.get_active_call(message.chat.id):
            queues[message.chat.id].append((stream_url, title, duration))
            await message.reply_text(f"🎵 Added to queue: **{title}**")
        else:
            try:
                await pytgcalls.join_group_call(
                    message.chat.id,
                    AudioPiped(stream_url, HighQualityAudio()),
                    stream_type=StreamType().pulse_stream,
                )
                current[message.chat.id] = (stream_url, title, duration)
                await message.reply_text(f"🎶 Now playing: **{title}**")
            except Exception as e:
                await message.reply_text(f"❌ Error joining voice chat: {str(e)}")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("skip") & filters.group)
async def skip(_, message: Message):
    if not pytgcalls.get_active_call(message.chat.id):
        await message.reply_text("❌ Nothing is playing.")
        return
    
    next_title = await play_next_song(message.chat.id)
    if next_title:
        await message.reply_text(f"⏭ Skipped to next song: **{next_title}**")
    else:
        await pytgcalls.leave_group_call(message.chat.id)
        await message.reply_text("⏹ Queue is empty, stopped playback.")

@bot.on_message(filters.command("pause") & filters.group)
async def pause(_, message: Message):
    if not pytgcalls.get_active_call(message.chat.id):
        await message.reply_text("❌ Nothing is playing.")
        return
    
    await pytgcalls.pause_stream(message.chat.id)
    await message.reply_text("⏸ Playback paused.")

@bot.on_message(filters.command("resume") & filters.group)
async def resume(_, message: Message):
    if not pytgcalls.get_active_call(message.chat.id):
        await message.reply_text("❌ Nothing is paused.")
        return
    
    await pytgcalls.resume_stream(message.chat.id)
    await message.reply_text("▶️ Playback resumed.")

@bot.on_message(filters.command("stop") & filters.group)
async def stop(_, message: Message):
    if not pytgcalls.get_active_call(message.chat.id):
        await message.reply_text("❌ Nothing is playing.")
        return
    
    if message.chat.id in queues:
        queues[message.chat.id] = []
    if message.chat.id in current:
        del current[message.chat.id]
    
    await pytgcalls.leave_group_call(message.chat.id)
    await message.reply_text("⏹ Playback stopped and queue cleared.")

@bot.on_message(filters.command("volume") & filters.group)
async def volume(_, message: Message):
    if not pytgcalls.get_active_call(message.chat.id):
        await message.reply_text("❌ Nothing is playing.")
        return
    
    if len(message.command) < 2:
        await message.reply_text("❌ Please provide a volume level (1-200).")
        return
    
    try:
        volume = int(message.command[1])
        if volume < 1 or volume > 200:
            await message.reply_text("❌ Volume must be between 1 and 200.")
            return
        
        await pytgcalls.change_volume_call(message.chat.id, volume)
        await message.reply_text(f"🔊 Volume set to {volume}%")
    except ValueError:
        await message.reply_text("❌ Please provide a valid number for volume.")

@bot.on_message(filters.command("queue") & filters.group)
async def show_queue(_, message: Message):
    if message.chat.id not in queues or len(queues[message.chat.id]) == 0:
        await message.reply_text("❌ Queue is empty.")
        return
    
    queue_text = "📃 **Current Queue:**\n"
    for i, (_, title, duration) in enumerate(queues[message.chat.id], 1):
        queue_text += f"{i}. {title} ({duration} seconds)\n"
    
    await message.reply_text(queue_text)

@bot.on_message(filters.command("nowplaying") & filters.group)
async def now_playing(_, message: Message):
    if message.chat.id not in current:
        await message.reply_text("❌ Nothing is playing.")
        return
    
    url, title, duration = current[message.chat.id]
    await message.reply_text(f"🎶 **Now Playing:** {title}\n⏳ Duration: {duration} seconds")

# Run the bot
async def main():
    await bot.start()
    print("Bot started!")
    await telethon_client.start()
    print("Telethon client started!")
    await pytgcalls.start()
    print("PyTgCalls started!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped!")
