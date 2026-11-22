# bot.py — единый файл
import os
import io
import json
import time
import math
import random
import logging
import asyncio
from collections import defaultdict, deque

import discord
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from dotenv import load_dotenv

from keep_alive import keep_alive

load_dotenv()
# ============================================================
# НАСТРОЙКИ — БЕРУТСЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ============================================================
TOKEN = os.environ.get("DISCORD_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID", "")
PANEL_IMAGE_URL = os.environ.get(
    "PANEL_IMAGE_URL",
    "https://raw.githubusercontent.com/ProxyGem/Trusiki-Show/main/panel_upravleniya.png",
)
SETTINGS_FILE = "settings.json"

OWNER_IDS: set[int] = set()
for part in OWNER_ID.split(","):
    part = part.strip()
    if part.isdigit():
        OWNER_IDS.add(int(part))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mazafaka")

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ============================================================
# СТАТУСЫ
# ============================================================
STATUS_PHRASES = [
    "хелоу мазафако", "тупо мазасрака", "я тут просто чиллю",
    "не пиши мне больше, иза тебя я потерял всех своих друзей",
    "вертитоп лашара", "мазафако", "войсы под контролем",
    "кого кикнуть сегодня?", "кого замутить сегодня?", "мазафака на связи",
]
STATUS_TYPES = [
    discord.ActivityType.listening,
    discord.ActivityType.watching,
    discord.ActivityType.playing,
]
STATUS_INTERVAL_MINUTES = 5


@tasks.loop(minutes=STATUS_INTERVAL_MINUTES)
async def rotate_status():
    phrase = random.choice(STATUS_PHRASES)
    act_type = random.choice(STATUS_TYPES)
    try:
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=act_type, name=phrase),
        )
    except Exception as e:
        log.warning(f"Не удалось сменить статус: {e}")


@rotate_status.before_loop
async def before_rotate_status():
    await bot.wait_until_ready()


# ============================================================
# ХРАНИЛИЩЕ
# ============================================================
voice_queues: dict[int, deque[int]] = defaultdict(deque)
voice_leaders: dict[int, int] = {}
member_channel: dict[int, int] = {}
lock_messages: dict[int, discord.Message] = {}
locked_channels: set[int] = set()
