# bot.py — единый файл
import os
import io
import json
import time
import math
import random
import logging
from collections import defaultdict, deque

import discord
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from dotenv import load_dotenv

from keep_alive import keep_alive

# Загружаем .env (локально). На Render переменные берутся из Environment Variables.
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
initially_locked: set[int] = set()
original_limits: dict[int, int] = {}
custom_limits: dict[int, int] = {}
dm_notifications: dict[int, bool] = defaultdict(lambda: True)

trusted_users: dict[int, set[int]] = defaultdict(set)
whitelist_mode: set[int] = set()

banned_users: dict[int, dict[int, dict]] = defaultdict(dict)
channel_stats: dict[int, dict] = {}

panel_ping_mode: dict[int, str] = defaultdict(lambda: "ping")
PANEL_PING_CYCLE = ["none", "text_ping", "ping"]
PANEL_PING_LABELS = {
    "none": "Без пинга",
    "text_ping": "Текст + пинг",
    "ping": "Только пинг",
}

_shutdown_done = False


# ============================================================
# ПЕРСОНАЛЬНЫЕ НАСТРОЙКИ
# ============================================================
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Не могу прочитать {SETTINGS_FILE}: {e}")
        return
    for uid_str, enabled in data.get("dm_notifications", {}).items():
        if str(uid_str).isdigit():
            dm_notifications[int(uid_str)] = bool(enabled)
    for uid_str, mode in data.get("panel_ping_mode", {}).items():
        if str(uid_str).isdigit() and mode in PANEL_PING_CYCLE:
            panel_ping_mode[int(uid_str)] = mode


def save_settings():
    data = {
        "dm_notifications": {str(k): bool(v) for k, v in dm_notifications.items()},
        "panel_ping_mode": {str(k): v for k, v in panel_ping_mode.items()},
    }
    try:
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
    except OSError as e:
        log.warning(f"Не могу сохранить {SETTINGS_FILE}: {e}")


# ============================================================
# ПРОВЕРКА ВЛАДЕЛЬЦА
# ============================================================
def is_bot_owner(user):
    return user.id in OWNER_IDS


def owner_only():
    async def predicate(ctx):
        if not is_bot_owner(ctx.author):
            await ctx.reply("🚫 Только владелец бота.", mention_author=False)
            return False
        return True
    return commands.check(predicate)


# ============================================================
# УТИЛИТЫ
# ============================================================
def is_human(member):
    return member is not None and not member.bot


def dm_enabled(user_id):
    return dm_notifications.get(user_id, True)


def get_panel_ping_mode(user_id):
    mode = panel_ping_mode.get(user_id, "ping")
    if mode not in PANEL_PING_CYCLE:
        mode = "ping"
    return mode


def set_panel_ping_mode(user_id, mode):
    panel_ping_mode[user_id] = mode


def build_panel_content(user_id):
    mode = get_panel_ping_mode(user_id)
    if mode == "none":
        return "Панель управления"
    if mode == "text_ping":
        return f"Панель управления <@{user_id}>"
    return f"<@{user_id}>"


def clean_channel(channel_id):
    voice_queues.pop(channel_id, None)
    voice_leaders.pop(channel_id, None)
    for mid in [m for m, c in member_channel.items() if c == channel_id]:
        member_channel.pop(mid, None)


def remove_member_from_queue(channel_id, member_id):
    q = voice_queues.get(channel_id)
    if q is None:
        return
    try:
        q.remove(member_id)
    except ValueError:
        return


def voice_flags(member):
    if not member.voice:
        return ""
    flags = []
    if member.voice.mute:
        flags.append("🔇")
    if member.voice.deaf:
        flags.append("🎧")
    return (" " + "".join(flags)) if flags else ""


def everyone_can_connect(channel):
    ow = channel.overwrites_for(channel.guild.default_role)
    if ow.connect is None:
        return channel.guild.default_role.permissions.connect
    return bool(ow.connect)


def is_locked(channel):
    return channel.id in locked_channels


def get_limit(channel):
    if channel.id in custom_limits:
        return custom_limits[channel.id]
    return channel.user_limit or 0


async def apply_limit(channel, limit):
    try:
        await channel.edit(user_limit=limit, reason="Мазафака: лимит")
        custom_limits[channel.id] = limit
        return True
    except discord.Forbidden:
        return False


# ============================================================
# WHITELIST
# ============================================================
def is_trusted(channel_id, user_id):
    return user_id in trusted_users.get(channel_id, set())


def whitelist_enabled(channel_id):
    return channel_id in whitelist_mode


# ============================================================
# БАНЫ
# ============================================================
def is_banned(channel_id, member_id):
    entries = banned_users.get(channel_id, {})
    rec = entries.get(member_id)
    if not rec:
        return False
    if rec.get("type") == "temp" and rec.get("expires_at"):
        if rec["expires_at"] <= time.time():
            entries.pop(member_id, None)
            return False
    return True


def add_ban(channel_id, guild_id, user_id, ban_type, reason, issued_by, duration_sec=None):
    now = time.time()
    rec = {
        "user_id": user_id,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "type": ban_type,
        "reason": reason or "—",
        "issued_by": issued_by,
        "issued_at": now,
        "expires_at": (now + duration_sec) if (ban_type == "temp" and duration_sec) else None,
    }
    banned_users[channel_id][user_id] = rec
    stats_bump(channel_id, "bans", 1)
    return rec


def remove_ban(channel_id, user_id):
    entries = banned_users.get(channel_id)
    if not entries or user_id not in entries:
        return False
    entries.pop(user_id, None)
    stats_bump(channel_id, "unbans", 1)
    return True


def cleanup_expired_bans():
    now = time.time()
    for cid, entries in banned_users.items():
        for uid, rec in list(entries.items()):
            if rec.get("type") == "temp" and rec.get("expires_at") and rec["expires_at"] <= now:
                entries.pop(uid, None)


# ============================================================
# СТАТИСТИКА
# ============================================================
def new_stats_record(leader_id):
    return {
        "leader_id": leader_id,
        "started_at": time.time(),
        "unique_visitors": [],
        "joins": 0,
        "kicks": 0,
        "mutes": 0,
        "deafs": 0,
        "bans": 0,
        "unbans": 0,
        "requests": 0,
        "approved": 0,
        "denied": 0,
        "sessions": [],
        "active_sessions": {},
    }


def ensure_stats(channel_id, leader_id):
    st = channel_stats.get(channel_id)
    if not st or st.get("leader_id") != leader_id:
        channel_stats[channel_id] = new_stats_record(leader_id)
    return channel_stats[channel_id]


def reset_stats(channel_id, new_leader_id):
    if new_leader_id is None:
        channel_stats.pop(channel_id, None)
    else:
        channel_stats[channel_id] = new_stats_record(new_leader_id)


def stats_track_join(channel_id, user_id):
    st = channel_stats.get(channel_id)
    if not st:
        return
    st["joins"] = st.get("joins", 0) + 1
    if user_id not in st["unique_visitors"]:
        st["unique_visitors"].append(user_id)
    st["active_sessions"][str(user_id)] = time.time()


def stats_track_leave(channel_id, user_id):
    st = channel_stats.get(channel_id)
    if not st:
        return
    start = st["active_sessions"].pop(str(user_id), None)
    if start:
        st["sessions"].append({
            "user_id": user_id, "start": start, "end": time.time(),
        })


def stats_bump(channel_id, key, delta=1):
    st = channel_stats.get(channel_id)
    if not st:
        return
    st[key] = st.get(key, 0) + delta


# ============================================================
# УВЕДОМЛЕНИЯ
# ============================================================
async def notify_dm(member, content=None, embed=None):
    if not dm_enabled(member.id):
        return
    kwargs = {}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if not kwargs:
        return
    try:
        await member.send(**kwargs)
    except (discord.Forbidden, discord.HTTPException):
        pass


def _channel_humans(channel):
    result = []
    for member in channel.guild.members:
        if member.bot:
            continue
        vs = member.voice
        if vs and vs.channel and vs.channel.id == channel.id:
            result.append(member)
    return result


async def notify_all_voice_channels(text):
    for guild in bot.guilds:
        for channel in guild.voice_channels:
            if not _channel_humans(channel):
                continue
            try:
                await channel.send(text)
            except (discord.Forbidden, discord.HTTPException):
                pass


# ============================================================
# БЕЗОПАСНЫЕ ОТВЕТЫ
# ============================================================
async def safe_respond(interaction, content=None, embed=None, view=None, ephemeral=True):
    kwargs = {"ephemeral": ephemeral}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view
    try:
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)
    except discord.InteractionResponded:
        try:
            await interaction.followup.send(**kwargs)
        except discord.HTTPException:
            pass
    except discord.HTTPException:
        pass


async def safe_edit_original(interaction, embed=None, view=None, content=None):
    kwargs = {}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view
    if not kwargs:
        return
    try:
        await interaction.edit_original_response(**kwargs)
    except (discord.NotFound, discord.HTTPException):
        pass


async def safe_reply(ctx, content=None, embed=None, view=None, delete_after=None, files=None):
    kwargs = {"mention_author": False}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view
    if delete_after is not None:
        kwargs["delete_after"] = delete_after
    if files is not None:
        kwargs["files"] = files
    try:
        return await ctx.reply(**kwargs)
    except discord.HTTPException:
        try:
            return await ctx.send(**kwargs)
        except discord.HTTPException:
            return None


# ============================================================
# РЕНДЕР СТАТИСТИКИ — GLASSMORPHISM (без эмодзи)
# ============================================================
W_STATS, H_STATS = 1400, 900

C_BG1 = (10, 8, 6)
C_BG2 = (22, 16, 10)
C_GLASS = (255, 240, 210, 16)
C_GLASS_B = (255, 200, 120, 70)
C_ACCENT = (255, 165, 0)
C_ACCENT2 = (255, 210, 60)
C_ACCENT3 = (255, 120, 0)
C_TEXT = (250, 245, 235)
C_DIM = (170, 160, 145)
C_DANGER = (255, 90, 70)
C_GOOD = (140, 210, 100)
C_INFO = (120, 180, 255)


def _font(size, bold=False):
    candidates = []
    if bold:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "assets/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
        ]
    else:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/Library/Fonts/Arial.ttf",
            "assets/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
        ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    log.warning("Не найден TTF-шрифт, использую load_default() — кириллица может быть квадратами")
    return ImageFont.load_default()


def _fsize(font, default=12):
    try:
        return font.size
    except AttributeError:
        return default


def _text_w(d, text, font):
    try:
        return d.textlength(text, font=font)
    except Exception:
        try:
            return d.textsize(text, font=font)[0]
        except Exception:
            return len(str(text)) * _fsize(font) // 2


def _fmt_dur(seconds):
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"


def _h_gradient(w, h, c1, c2):
    w = max(1, int(w))
    h = max(1, int(h))
    img = Image.new("RGB", (w, h), c1)
    gd = ImageDraw.Draw(img)
    for x in range(w):
        t = x / max(1, w - 1)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        gd.line([(x, 0), (x, h)], fill=(r, g, b))
    return img.convert("RGBA")


def _gradient_bg(w, h):
    top = (14, 10, 6)
    bot = (26, 18, 10)
    img = Image.new("RGB", (w, h), top)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] * (1 - t) + bot[0] * t)
        g = int(top[1] * (1 - t) + bot[1] * t)
        b = int(top[2] * (1 - t) + bot[2] * t)
        d.line([(0, y), (w, y)], fill=(r, g, b))
    return img.convert("RGBA")


def _radial_glow(size, center, radius, color, max_alpha=100):
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    steps = 24
    for i in range(steps, 0, -1):
        r = int(radius * (i / steps))
        a = int(max_alpha * (1 - i / steps) ** 1.5)
        if a <= 0 or r <= 0:
            continue
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=(color[0], color[1], color[2], a))
    try:
        return layer.filter(ImageFilter.GaussianBlur(radius=radius * 0.15))
    except Exception:
        return layer


def _draw_glass(img, box, radius=18, tint=(255, 240, 210, 14),
                border=(255, 200, 120, 60), border_w=1):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=tint, outline=border, width=border_w)
    x1, y1, x2, y2 = box
    d.line([(x1 + radius, y1 + 1), (x2 - radius, y1 + 1)],
           fill=(255, 240, 200, 55), width=1)
    img.alpha_composite(layer)


def _paste_bar(img, x, y, w, h, ratio, c1, c2, radius=None):
    if w <= 0 or h <= 0:
        return
    x, y, w, h = int(x), int(y), int(w), int(h)
    bg_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg_layer)
    bd.rounded_rectangle([x, y, x + w, y + h], radius=(radius or h // 2),
                         fill=(60, 46, 30, 150))
    img.alpha_composite(bg_layer)

    fw = int(w * max(0.0, min(1.0, ratio)))
    if fw < 3:
        return
    grad = _h_gradient(fw, h, c1, c2)
    r = radius if radius is not None else h // 2
    mask = Image.new("L", (fw, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, fw, h], radius=r, fill=255)
    img.paste(grad, (x, y), mask)


def _draw_donut(img, cx, cy, r_out, r_in, segments, empty_color=(70, 60, 50)):
    total = sum(v for v, _ in segments)
    if total <= 0:
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out],
                  outline=empty_color, width=max(1, r_out - r_in))
        img.alpha_composite(layer)
        return

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    start = -90
    for value, color in segments:
        if value <= 0:
            continue
        angle = 360 * (value / total)
        end = start + angle
        d.pieslice([cx - r_out, cy - r_out, cx + r_out, cy + r_out],
                   start=start, end=end, fill=color)
        start = end
    img.alpha_composite(layer)

    inner = Image.new("RGBA", (r_in * 2, r_in * 2), (0, 0, 0, 0))
    idd = ImageDraw.Draw(inner)
    idd.ellipse([0, 0, r_in * 2, r_in * 2], fill=(26, 20, 14, 255))
    img.alpha_composite(inner, (cx - r_in, cy - r_in))


def _draw_dot(d, x, y, r, color):
    d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def _draw_pill(img, x, y, w, h, value, color, font):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                        fill=(color[0], color[1], color[2], 55),
                        outline=color, width=1)
    img.alpha_composite(layer)
    d2 = ImageDraw.Draw(img)
    s = str(value)
    tw = _text_w(d2, s, font)
    fs = _fsize(font, 14)
    ty = y + (h - fs) / 2 - 2
    d2.text((x + (w - tw) / 2, ty), s, font=font, fill=color)


def render_stats_png(channel_name, leader_name, stats):
    W, H = 1400, 1000
    PAD = 32

    img = _gradient_bg(W, H)
    for center, radius, color, alpha in [
        ((240, 220), 420, (255, 165, 0), 70),
        ((W - 180, 140), 340, (255, 210, 60), 55),
        ((W - 300, H - 120), 420, (255, 120, 0), 60),
        ((160, H - 160), 320, (255, 200, 100), 40),
    ]:
        try:
            glow = _radial_glow((W, H), center, radius, color, max_alpha=alpha)
            img = Image.alpha_composite(img, glow)
        except Exception as e:
            log.warning(f"glow skip: {e}")

    f_h1 = _font(30, True)
    f_h2 = _font(16)
    f_label = _font(12, True)
    f_label_s = _font(11)
    f_big = _font(44, True)
    f_mid = _font(19, True)
    f_val = _font(15, True)
    f_small = _font(11)

    head = [PAD, PAD, W - PAD, PAD + 92]
    _draw_glass(img, head, radius=20, tint=(255, 235, 200, 18),
                border=(255, 200, 120, 70), border_w=2)
    d = ImageDraw.Draw(img)

    lx, ly = PAD + 24, PAD + 22
    d.rounded_rectangle([lx, ly, lx + 48, ly + 48], radius=12, fill=(255, 165, 0))
    for i, w_bar in enumerate([30, 22, 26]):
        d.rounded_rectangle([lx + 9, ly + 12 + i * 10,
                             lx + 9 + w_bar, ly + 12 + i * 10 + 4],
                            radius=2, fill=(30, 18, 6))

    d.text((PAD + 92, PAD + 20), "СТАТИСТИКА ВОЙСА", font=f_h1, fill=(255, 215, 60))
    d.text((PAD + 94, PAD + 60),
           f"{channel_name}   •   Владелец: {leader_name}",
           font=f_h2, fill=(200, 185, 165))

    started = stats.get("started_at", time.time())
    period_str = time.strftime("%d.%m.%Y %H:%M", time.localtime(started))
    d.text((W - PAD - 200, PAD + 20), "ПЕРИОД ВЛАДЕНИЯ",
           font=f_label, fill=(170, 160, 145))
    d.text((W - PAD - 200, PAD + 38), period_str, font=f_h2, fill=(255, 210, 60))
    d.text((W - PAD - 200, PAD + 60), "активный", font=f_small, fill=(140, 210, 100))

    unique = len(stats.get("unique_visitors", []))
    joins = stats.get("joins", 0)
    sessions = stats.get("sessions", [])
    total_time = sum(s["end"] - s["start"] for s in sessions if s.get("end"))
    avg = (total_time / len(sessions)) if sessions else 0

    kpi_y = PAD + 108
    kpi_h = 150
    gap = 16
    kpi_w = (W - PAD * 2 - gap * 3) // 4
    kpi_max_raw = max(unique, joins, int(total_time), int(avg))
    kpi_den = max(5.0, float(kpi_max_raw))
    kpi_ratios = [unique / kpi_den, joins / kpi_den, total_time / kpi_den, avg / kpi_den]
    kpis = [
        ("УНИКАЛЬНЫХ", str(unique), kpi_ratios[0], (255, 210, 60)),
        ("ПОДКЛЮЧЕНИЙ", str(joins), kpi_ratios[1], (255, 165, 0)),
        ("АКТИВНОСТЬ", _fmt_dur(total_time), kpi_ratios[2], (255, 120, 0)),
        ("СРЕДНЯЯ СЕССИЯ", _fmt_dur(avg), kpi_ratios[3], (255, 215, 60)),
    ]
    for i, (label, value, ratio, accent) in enumerate(kpis):
        x = PAD + i * (kpi_w + gap)
        _draw_glass(img, [x, kpi_y, x + kpi_w, kpi_y + kpi_h],
                    radius=16, tint=(255, 235, 200, 16),
                    border=(255, 200, 120, 55))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([x + 18, kpi_y + 16, x + 18 + 36, kpi_y + 21],
                            radius=3, fill=accent)
        d.text((x + 18, kpi_y + 30), label, font=f_label, fill=(170, 160, 145))
        d.text((x + 18, kpi_y + 54), value, font=f_big, fill=(250, 245, 235))
        _paste_bar(img, x + 18, kpi_y + kpi_h - 26, kpi_w - 36, 8,
                   ratio, (255, 120, 0), accent)
        d = ImageDraw.Draw(img)

    left_x = PAD
    left_y = kpi_y + kpi_h + 16
    left_w = int(W * 0.58)
    left_h = 400
    _draw_glass(img, [left_x, left_y, left_x + left_w, left_y + left_h],
                radius=20, tint=(255, 235, 200, 16),
                border=(255, 200, 120, 60))
    d = ImageDraw.Draw(img)
    d.text((left_x + 24, left_y + 20), "АКТИВНОСТЬ ПО СЕССИЯМ",
           font=f_mid, fill=(255, 215, 60))
    leg_line_y = left_y + 34
    d.rounded_rectangle([left_x + left_w - 210, leg_line_y - 2,
                         left_x + left_w - 196, leg_line_y + 2],
                        radius=2, fill=(255, 165, 0))
    d.text((left_x + left_w - 188, leg_line_y - 8), "длительность сессии",
           font=f_small, fill=(150, 140, 125))

    gx1 = left_x + 58
    gx2 = left_x + left_w - 28
    gy_top = left_y + 76
    gy_bot = left_y + left_h - 78
    label_y = gy_bot + 20

    grid_n = 5
    f_axis = _font(11)
    for i in range(grid_n + 1):
        yy = gy_top + (gy_bot - gy_top) * i // grid_n
        d.line([(gx1, yy), (gx2, yy)], fill=(255, 200, 120, 22), width=1)
        val_lbl = (grid_n - i) * 20
        d.text((left_x + 14, yy - 7), str(val_lbl),
               font=f_axis, fill=(150, 140, 125))

    durations = [s["end"] - s["start"] for s in sessions[-8:] if s.get("end")]
    n_bars = 8
    bar_area_w = gx2 - gx1 - 20
    bar_gap = 14
    bar_w = max(20, (bar_area_w - (n_bars - 1) * bar_gap) // n_bars)
    max_dur = max(durations) if durations else 1

    for i in range(n_bars):
        bx = gx1 + 10 + i * (bar_w + bar_gap)
        dur = durations[i] if i < len(durations) else 0

        if dur <= 0:
            ph = 12
            by = gy_bot - ph
            d.rounded_rectangle([bx, by, bx + bar_w, gy_bot], radius=4,
                                fill=(70, 55, 36, 200))
            d.rounded_rectangle([bx, by, bx + bar_w, by + 3], radius=2,
                                fill=(140, 100, 50))
        else:
            bh = int((dur / max_dur) * (gy_bot - gy_top - 10))
            bh = max(12, bh)
            by = gy_bot - bh
            try:
                glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                gd = ImageDraw.Draw(glow_layer)
                gd.ellipse([bx - 6, gy_bot - 10, bx + bar_w + 6, gy_bot + 14],
                           fill=(255, 165, 0, 90))
                glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(8))
                img.alpha_composite(glow_layer)
            except Exception:
                pass
            grad = _h_gradient(bar_w, bh, (255, 120, 0), (255, 215, 60))
            mask = Image.new("L", (bar_w, bh), 0)
            md = ImageDraw.Draw(mask)
            md.rounded_rectangle([0, 0, bar_w, bh], radius=6, fill=255)
            img.paste(grad, (bx, by), mask)
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([bx, by - 3, bx + bar_w, by], radius=2,
                                fill=(255, 230, 140))

        label_txt = f"#{i+1:02d}"
        tw = _text_w(d, label_txt, f_axis)
        d.text((bx + bar_w / 2 - tw / 2, label_y), label_txt,
               font=f_axis, fill=(150, 140, 125))

    right_x = left_x + left_w + 16
    right_w = W - PAD - right_x

    pr_y = left_y
    pr_h = 180
    _draw_glass(img, [right_x, pr_y, right_x + right_w, pr_y + pr_h],
                radius=20, tint=(255, 235, 200, 16),
                border=(255, 200, 120, 60))
    d = ImageDraw.Draw(img)
    d.text((right_x + 22, pr_y + 16), "ПОСЕТИТЕЛИ", font=f_mid, fill=(255, 215, 60))

    active_n = len(stats.get("active_sessions", {}))
    vis_max = max(5.0, float(max(unique, joins, active_n)))
    rows = [
        ("Уникальных", unique, unique / vis_max, (255, 215, 60)),
        ("Подключений", joins, joins / vis_max, (255, 165, 0)),
        ("Активных сейчас", active_n, active_n / vis_max, (140, 210, 100)),
    ]
    ry = pr_y + 54
    for label, val, ratio, color in rows:
        d.text((right_x + 22, ry), label, font=f_label_s, fill=(170, 160, 145))
        d.text((right_x + right_w - 60, ry - 2), str(val),
               font=f_val, fill=(250, 245, 235))
        _paste_bar(img, right_x + 22, ry + 18, right_w - 100, 8, ratio,
                   color, color)
        d = ImageDraw.Draw(img)
        ry += 40

    dn_y = pr_y + pr_h + 16
    dn_h = 190
    _draw_glass(img, [right_x, dn_y, right_x + right_w, dn_y + dn_h],
                radius=20, tint=(255, 235, 200, 16),
                border=(255, 200, 120, 60))
    d = ImageDraw.Draw(img)
    d.text((right_x + 22, dn_y + 16), "ДЕЙСТВИЯ", font=f_mid, fill=(255, 215, 60))

    kicks = stats.get("kicks", 0)
    mutes = stats.get("mutes", 0)
    deafs = stats.get("deafs", 0)
    bans_c = stats.get("bans", 0)
    total_actions = kicks + mutes + deafs + bans_c

    cx = right_x + 90
    cy = dn_y + dn_h // 2 + 10
    r_out = 52
    r_in = 34
    segments = [
        (kicks, (255, 90, 70)),
        (mutes, (255, 165, 0)),
        (deafs, (255, 215, 60)),
        (bans_c, (120, 180, 255)),
    ]
    _draw_donut(img, cx, cy, r_out, r_in, segments)

    d = ImageDraw.Draw(img)
    f_center_n = _font(22, True)
    tw = _text_w(d, str(total_actions), f_center_n)
    d.text((cx - tw / 2, cy - 13), str(total_actions),
           font=f_center_n, fill=(250, 245, 235))
    tw2 = _text_w(d, "ВСЕГО", f_label_s)
    d.text((cx - tw2 / 2, cy + 12), "ВСЕГО", font=f_label_s, fill=(170, 160, 145))

    leg_x = right_x + 180
    leg_y = dn_y + 46
    legend_items = [
        ("Кики", kicks, (255, 90, 70)),
        ("Мьюты микро", mutes, (255, 165, 0)),
        ("Мьюты ушей", deafs, (255, 215, 60)),
        ("Баны", bans_c, (120, 180, 255)),
    ]
    for i, (label, val, color) in enumerate(legend_items):
        yy = leg_y + i * 30
        _draw_dot(d, leg_x + 8, yy + 8, 6, color)
        d.text((leg_x + 24, yy), label, font=f_label_s, fill=(170, 160, 145))
        d.text((right_x + right_w - 40, yy), str(val), font=f_val,
               fill=(250, 245, 235))

    bottom_y = max(dn_y + dn_h + 16, left_y + left_h + 16)
    bottom_h = H - PAD - 44 - bottom_y
    half_w = (W - PAD * 2 - 16) // 2

    _draw_glass(img, [PAD, bottom_y, PAD + half_w, bottom_y + bottom_h],
                radius=20, tint=(255, 235, 200, 16),
                border=(255, 200, 120, 60))
    d = ImageDraw.Draw(img)
    d.text((PAD + 22, bottom_y + 14), "МОДЕРАЦИЯ",
           font=f_mid, fill=(255, 215, 60))

    mod_rows = [
        ("Кики", kicks, (255, 90, 70)),
        ("Мьюты микро", mutes, (255, 165, 0)),
        ("Мьюты ушей", deafs, (255, 215, 60)),
        ("Баны", bans_c, (120, 180, 255)),
        ("Разбаны", stats.get("unbans", 0), (140, 210, 100)),
    ]
    ry = bottom_y + 52
    for label, val, color in mod_rows:
        _draw_dot(d, PAD + 30, ry + 9, 5, color)
        d.text((PAD + 46, ry), label, font=f_label_s, fill=(170, 160, 145))
        _draw_pill(img, PAD + half_w - 90, ry - 1, 62, 24, val, color, f_val)
        d = ImageDraw.Draw(img)
        ry += 30

    rx2 = PAD + half_w + 16
    _draw_glass(img, [rx2, bottom_y, rx2 + half_w, bottom_y + bottom_h],
                radius=20, tint=(255, 235, 200, 16),
                border=(255, 200, 120, 60))
    d = ImageDraw.Draw(img)
    d.text((rx2 + 22, bottom_y + 14), "ЗАПРОСЫ НА ВХОД",
           font=f_mid, fill=(255, 215, 60))

    req_rows = [
        ("Всего запросов", stats.get("requests", 0), (255, 215, 60)),
        ("Одобрено", stats.get("approved", 0), (140, 210, 100)),
        ("Отклонено", stats.get("denied", 0), (255, 90, 70)),
    ]
    ry = bottom_y + 52
    for label, val, color in req_rows:
        _draw_dot(d, rx2 + 30, ry + 9, 5, color)
        d.text((rx2 + 46, ry), label, font=f_label_s, fill=(170, 160, 145))
        _draw_pill(img, rx2 + half_w - 90, ry - 1, 62, 24, val, color, f_val)
        d = ImageDraw.Draw(img)
        ry += 34

    pb_y = bottom_y + bottom_h - 40
    d.text((rx2 + 22, pb_y - 22), "АКТИВНОСТЬ ЗА 24Ч",
           font=f_label, fill=(170, 160, 145))
    ratio = min(1.0, total_time / 86400) if total_time else 0
    _paste_bar(img, rx2 + 22, pb_y, half_w - 120, 14, ratio,
               (255, 120, 0), (255, 215, 60))
    d = ImageDraw.Draw(img)
    pct = f"{int(ratio * 100)}%"
    pct_w = _text_w(d, pct, f_val)
    d.text((rx2 + half_w - 22 - pct_w, pb_y - 2), pct,
           font=f_val, fill=(255, 215, 60))

    d.text((PAD, H - 20), "Мазафака Войс  •  статистика текущего владельца",
           font=f_small, fill=(150, 140, 125))

    out = img.convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


# ============================================================
# ПУБЛИЧНОЕ СООБЩЕНИЕ
# ============================================================
class OpenPanelButton(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="Открыть панель", emoji="👑", style=discord.ButtonStyle.primary)
    async def open_btn(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send(
                "🚫 Только владелец войса может открыть панель.", ephemeral=True)
            return
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return
        member = channel.guild.get_member(interaction.user.id)
        if not member or not member.voice or member.voice.channel != channel:
            await interaction.followup.send(
                "🚫 Ты должен быть в своём голосовом канале.", ephemeral=True)
            return
        embed = build_panel_embed(channel, member)
        if PANEL_IMAGE_URL:
            embed.set_image(url=PANEL_IMAGE_URL)
        view = LeaderPanel(channel.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


def build_open_embed(channel, leader):
    locked = is_locked(channel)
    banned_count = len(banned_users.get(channel.id, {}))
    cur_limit = get_limit(channel)
    limit_str = f"👥 Лимит: **{cur_limit}**" if cur_limit else "👥 Лимит: **нет**"
    wl = "🔒 включён" if whitelist_enabled(channel.id) else "🔓 выключен"

    embed = discord.Embed(
        title=f"👑 Владелец войса: {leader.display_name}",
        description=(
            f"🔊 Канал: **{channel.name}**\n"
            f"{limit_str}\n"
            f"Вход: {'🔒 **закрыт для всех**' if locked else '🔓 **открыт**'}\n"
            f"👥 Только свои: {wl}\n"
            f"🚫 Забанено: **{banned_count}**\n\n"
            "Нажми **👑 Открыть панель**, чтобы управлять каналом.\n"
            "*Кнопка доступна только владельцу.*"
        ),
        color=discord.Color.red() if locked else discord.Color.gold(),
    )
    embed.set_footer(text="Мазафака Войс")
    return embed


async def send_open_message(channel, leader_id):
    leader = channel.guild.get_member(leader_id)
    if not leader:
        return
    old = lock_messages.pop(channel.id, None)
    if old:
        try:
            await old.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
    try:
        embed = build_open_embed(channel, leader)
        view = OpenPanelButton(channel.id)
        content = build_panel_content(leader.id)
        msg = await channel.send(content=content, embed=embed, view=view)
        lock_messages[channel.id] = msg
    except (discord.Forbidden, AttributeError) as e:
        log.warning(f"Не могу отправить панель в {channel.name}: {e}")


async def refresh_lock_message(channel):
    leader_id = voice_leaders.get(channel.id)
    if leader_id:
        await send_open_message(channel, leader_id)
    else:
        old = lock_messages.pop(channel.id, None)
        if old:
            try:
                await old.delete()
            except (discord.NotFound, discord.Forbidden):
                pass


# ============================================================
# ГЛАВНАЯ ПАНЕЛЬ ЛИДЕРА
# ============================================================
class LeaderPanel(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    async def _require_leader(self, interaction):
        await interaction.response.defer(ephemeral=True)
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return None
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send(
                "🚫 Только **лидер канала** может управлять.", ephemeral=True)
            return None
        member = channel.guild.get_member(interaction.user.id)
        if not member or not member.voice or member.voice.channel != channel:
            await interaction.followup.send(
                "🚫 Ты должен быть в своём голосовом канале.", ephemeral=True)
            return None
        return channel

    @discord.ui.button(label="Кикнуть", emoji="🦶", style=discord.ButtonStyle.danger, row=0)
    async def kick_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="kick")
        embed = build_member_select_embed(channel, "kick")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Микро", emoji="🔇", style=discord.ButtonStyle.primary, row=0)
    async def mute_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="mute")
        embed = build_member_select_embed(channel, "mute")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Уши", emoji="🎧", style=discord.ButtonStyle.primary, row=0)
    async def deaf_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="deaf")
        embed = build_member_select_embed(channel, "deaf")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Закрыть вход", emoji="🔒", style=discord.ButtonStyle.danger, row=1)
    async def lock_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        locked_channels.add(channel.id)
        await interaction.followup.send("🔒 Вход закрыт для всех.", ephemeral=True)
        await refresh_lock_message(channel)

    @discord.ui.button(label="Открыть вход", emoji="🔓", style=discord.ButtonStyle.success, row=1)
    async def unlock_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        locked_channels.discard(channel.id)
        await interaction.followup.send("🔓 Вход открыт для всех.", ephemeral=True)
        await refresh_lock_message(channel)

    @discord.ui.button(label="Только свои", emoji="👥", style=discord.ButtonStyle.primary, row=1)
    async def whitelist_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = WhitelistPanel(channel)
        embed = build_whitelist_embed(channel)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Забанить", emoji="🚫", style=discord.ButtonStyle.danger, row=2)
    async def ban_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = BanTypeView(channel)
        embed = discord.Embed(
            title="🚫 Забанить вход — выбери тип",
            description=(
                "**⏳ Временный бан** — блокировка на срок, автоснятие\n"
                "**🔒 Постоянный бан** — навсегда, до ручного разбана"
            ),
            color=discord.Color.dark_red(),
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Разбанить", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def unban_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        if not banned_users.get(channel.id):
            await interaction.followup.send("Список банов пуст 🤷", ephemeral=True)
            return
        view = BanListView(channel, page=0)
        embed = build_banlist_embed(channel, 0)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Список банов", emoji="📋", style=discord.ButtonStyle.secondary, row=2)
    async def banlist_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        if not banned_users.get(channel.id):
            await interaction.followup.send("Список банов пуст 🤷", ephemeral=True)
            return
        view = BanListView(channel, page=0)
        embed = build_banlist_embed(channel, 0)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Лимит", emoji="🔢", style=discord.ButtonStyle.primary, row=3)
    async def limit_btn(self, interaction, button):
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("Канал не найден.", ephemeral=True)
            return
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.response.send_message(
                "🚫 Только **лидер канала** может управлять.", ephemeral=True)
            return
        member = channel.guild.get_member(interaction.user.id)
        if not member or not member.voice or member.voice.channel != channel:
            await interaction.response.send_message(
                "🚫 Ты должен быть в своём голосовом канале.", ephemeral=True)
            return
        await interaction.response.send_modal(LimitModal(channel.id))

    @discord.ui.button(label="Снять лимит", emoji="♻️", style=discord.ButtonStyle.secondary, row=3)
    async def reset_limit_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        ok = await apply_limit(channel, 0)
        text = "♻️ Лимит снят." if ok else "🚫 Не удалось."
        await interaction.followup.send(text, ephemeral=True)
        await refresh_lock_message(channel)

    @discord.ui.button(label="Передать", emoji="👑", style=discord.ButtonStyle.primary, row=4)
    async def transfer_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="transfer")
        embed = build_member_select_embed(channel, "transfer")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Очередь", emoji="📊", style=discord.ButtonStyle.secondary, row=4)
    async def queue_btn(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return
        q = voice_queues.get(self.channel_id, deque())
        if not q:
            await interaction.followup.send("Очередь пуста 🤷", ephemeral=True)
            return
        leader_id = voice_leaders.get(self.channel_id)
        lines = []
        for i, mid in enumerate(q, 1):
            mem = channel.guild.get_member(mid)
            name = mem.display_name if mem else f"id={mid}"
            crown = " 👑" if mid == leader_id else ""
            lines.append(f"`{i}.` {name}{crown}")
        embed = discord.Embed(title=f"📊 Очередь — {channel.name}",
                              description="\n".join(lines),
                              color=discord.Color.blurple())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Статистика", emoji="📈", style=discord.ButtonStyle.success, row=4)
    async def stats_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        st = ensure_stats(channel.id, interaction.user.id)
        leader = channel.guild.get_member(interaction.user.id)
        try:
            buf = render_stats_png(channel.name, leader.display_name if leader else "—", st)
        except Exception as e:
            log.warning(f"Ошибка рендера статистики: {e}")
            await interaction.followup.send(
                "🚫 Не могу сгенерировать картинку (проверь Pillow/шрифты).",
                ephemeral=True)
            return
        file = discord.File(fp=buf, filename="stats.png")
        embed = discord.Embed(title="📈 Статистика текущего владельца",
                              description=f"Канал: **{channel.name}**",
                              color=discord.Color.gold())
        embed.set_image(url="attachment://stats.png")
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    @discord.ui.button(label="Очистить", emoji="🧹", style=discord.ButtonStyle.danger, row=4)
    async def clear_btn(self, interaction, button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        embed = discord.Embed(
            title="🧹 Очистка комнаты",
            description=("Вы действительно хотите вернуть комнату к стандартным настройкам?\n"
                         "**Все изменения владельца будут сброшены.**"),
            color=discord.Color.orange(),
        )
        view = ClearConfirmView(channel)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


def build_panel_embed(channel, leader):
    q = voice_queues.get(channel.id, deque())
    members_count = len([m for m in channel.members if not m.bot])
    locked = is_locked(channel)
    banned_count = len(banned_users.get(channel.id, {}))
    cur_limit = get_limit(channel)
    limit_str = (f"👥 **{members_count} / {cur_limit}**" if cur_limit
                 else f"👥 **{members_count}** (без лимита)")
    wl = "🔒 включён" if whitelist_enabled(channel.id) else "🔓 выключен"

    embed = discord.Embed(
        title=f"👑 {leader.display_name} — панель управления",
        description=(
            f"🔊 Канал: **{channel.name}**\n"
            f"{limit_str}\n"
            f"📊 В очереди: **{len(q)}**\n"
            f"🚫 Забанено: **{banned_count}**\n"
            f"👥 Только свои: {wl}\n"
            f"Вход: {'🔒 **закрыт**' if locked else '🔓 **открыт**'}"
        ),
        color=discord.Color.red() if locked else discord.Color.gold(),
    )
    embed.add_field(
        name="Управление",
        value=(
            "🦶 **Кикнуть**  •  🔇 **Микро**  •  🎧 **Уши**\n"
            "🔒 **Закрыть вход**  •  🔓 **Открыть вход**  •  👥 **Только свои**\n"
            "🚫 **Забанить**  •  ✅ **Разбанить**  •  📋 **Список банов**\n"
            "🔢 **Лимит**  •  ♻️ **Снять лимит**  •  👑 **Передать**\n"
            "📊 **Очередь**  •  📈 **Статистика**  •  🧹 **Очистить**"
        ),
        inline=False,
    )
    embed.set_footer(text="Мазафака Войс • панель видна только тебе")
    return embed


# ============================================================
# МОДАЛКА ЛИМИТА
# ============================================================
class LimitModal(discord.ui.Modal, title="Лимит участников"):
    limit_input = discord.ui.TextInput(
        label="Максимум участников",
        placeholder="Число от 0 до 99. 0 — без лимита.",
        required=True, max_length=2,
    )

    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер канала.", ephemeral=True)
            return
        raw = self.limit_input.value.strip()
        if not raw.isdigit():
            await interaction.followup.send("🚫 Введи число 0..99.", ephemeral=True)
            return
        limit = int(raw)
        if not (0 <= limit <= 99):
            await interaction.followup.send("🚫 Допустимо 0..99.", ephemeral=True)
            return
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return
        if limit == 0:
            ok = await apply_limit(channel, 0)
            if not ok:
                await interaction.followup.send("🚫 Нет прав.", ephemeral=True)
                return
            await interaction.followup.send("♻️ Лимит снят.", ephemeral=True)
            await refresh_lock_message(channel)
            return
        current = len([m for m in channel.members if not m.bot])
        if current > limit:
            leader_id = voice_leaders.get(self.channel_id)
            non_leaders = [m for m in channel.members if not m.bot and m.id != leader_id]
            keep = max(0, limit - 1) if leader_id else limit
            for m in non_leaders[keep:]:
                try:
                    await m.move_to(None)
                except discord.Forbidden:
                    pass
                remove_member_from_queue(self.channel_id, m.id)
                await notify_dm(m, content=(
                    f"👥 **{interaction.user.display_name}** установил лимит "
                    f"**{limit}** в **{channel.name}** — вы выгнаны."))
        ok = await apply_limit(channel, limit)
        if not ok:
            await interaction.followup.send("🚫 Нет прав.", ephemeral=True)
            return
        await interaction.followup.send(f"👥 Лимит: **{limit}**.", ephemeral=True)
        await refresh_lock_message(channel)


# ============================================================
# WHITELIST PANEL
# ============================================================
class WhitelistPanel(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=300)
        self.channel_id = channel.id
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        enabled = whitelist_enabled(self.channel_id)

        toggle = discord.ui.Button(
            label="Отключить" if enabled else "Включить",
            emoji="🔓" if enabled else "🔒",
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
            row=0,
        )
        toggle.callback = self._toggle_cb()
        self.add_item(toggle)

        add_btn = discord.ui.Button(label="Добавить", emoji="➕",
                                    style=discord.ButtonStyle.primary, row=0,
                                    disabled=not enabled)
        add_btn.callback = self._add_cb()
        self.add_item(add_btn)

        rem_btn = discord.ui.Button(label="Убрать", emoji="➖",
                                    style=discord.ButtonStyle.secondary, row=0,
                                    disabled=not enabled)
        rem_btn.callback = self._remove_cb()
        self.add_item(rem_btn)

        close_btn = discord.ui.Button(label="Закрыть", emoji="✖️",
                                      style=discord.ButtonStyle.danger, row=0)
        close_btn.callback = self._close_cb()
        self.add_item(close_btn)

    async def _check(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
            return None
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return None
        return channel

    def _toggle_cb(self):
        async def cb(interaction):
            channel = await self._check(interaction)
            if not channel:
                return
            if whitelist_enabled(channel.id):
                whitelist_mode.discard(channel.id)
                trusted_users.pop(channel.id, None)
                await interaction.followup.send(
                    "🔓 Режим «Только свои» отключён.", ephemeral=True)
            else:
                whitelist_mode.add(channel.id)
                await interaction.followup.send(
                    "🔒 Режим «Только свои» включён.", ephemeral=True)
            await refresh_lock_message(channel)
            self._rebuild()
            await safe_edit_original(interaction,
                                     embed=build_whitelist_embed(channel), view=self)
        return cb

    def _add_cb(self):
        async def cb(interaction):
            channel = await self._check(interaction)
            if not channel:
                return
            if not whitelist_enabled(channel.id):
                await interaction.followup.send(
                    "🚫 Сначала включи режим «Только свои».", ephemeral=True)
                return
            view = WhitelistAddSelectView(channel, page=0)
            embed = build_whitelist_add_embed(channel, 0)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        return cb

    def _remove_cb(self):
        async def cb(interaction):
            channel = await self._check(interaction)
            if not channel:
                return
            if not trusted_users.get(channel.id):
                await interaction.followup.send("Список доверенных пуст 🤷", ephemeral=True)
                return
            view = WhitelistRemoveSelectView(channel, page=0)
            embed = build_whitelist_remove_embed(channel, 0)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        return cb

    def _close_cb(self):
        async def cb(interaction):
            try:
                await interaction.response.defer()
                await interaction.delete_original_response()
            except (discord.NotFound, discord.HTTPException):
                pass
        return cb


def build_whitelist_embed(channel):
    enabled = whitelist_enabled(channel.id)
    trusted = trusted_users.get(channel.id, set())
    names = []
    for uid in trusted:
        m = channel.guild.get_member(uid)
        names.append(f"• {m.display_name if m else f'id={uid}'}")
    desc = (
        f"**Статус:** {'🔒 ВКЛЮЧЁН' if enabled else '🔓 выключен'}\n"
        f"**Доверенных:** {len(trusted)}\n\n"
        + ("\n".join(names) if names else "*Список доверенных пуст*")
    )
    return discord.Embed(title="👥 Режим «Только свои»", description=desc,
                         color=discord.Color.orange() if enabled else discord.Color.greyple())


def build_whitelist_add_embed(channel, page):
    leader_id = voice_leaders.get(channel.id)
    members = [m for m in channel.guild.members
               if not m.bot and m.id != leader_id and not is_trusted(channel.id, m.id)]
    start = page * PER_PAGE
    lines = [f"• {m.display_name}" for m in members[start:start + PER_PAGE]]
    desc = "\n".join(lines) if lines else "Некого добавлять 🤷"
    return discord.Embed(title="➕ Добавить доверенного", description=desc,
                         color=discord.Color.green())


def build_whitelist_remove_embed(channel, page):
    trusted = list(trusted_users.get(channel.id, set()))
    start = page * PER_PAGE
    lines = []
    for uid in trusted[start:start + PER_PAGE]:
        m = channel.guild.get_member(uid)
        lines.append(f"• {m.display_name if m else f'id={uid}'}")
    desc = "\n".join(lines) if lines else "Список пуст 🤷"
    return discord.Embed(title="➖ Убрать доверенного", description=desc,
                         color=discord.Color.orange())


class WhitelistAddSelectView(discord.ui.View):
    def __init__(self, channel, page=0):
        super().__init__(timeout=180)
        self.channel_id = channel.id
        leader_id = voice_leaders.get(channel.id)
        members = [m for m in channel.guild.members
                   if not m.bot and m.id != leader_id and not is_trusted(channel.id, m.id)]
        self.total_pages = max(1, (len(members) + PER_PAGE - 1) // PER_PAGE)
        self.page = max(0, min(page, self.total_pages - 1))
        start = self.page * PER_PAGE
        for i, m in enumerate(members[start:start + PER_PAGE]):
            btn = discord.ui.Button(label=m.display_name[:18],
                                    style=discord.ButtonStyle.secondary, row=i // 5)
            btn.callback = self._make_add_cb(m.id)
            self.add_item(btn)
        prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.primary, row=4,
                                 disabled=(self.page == 0))
        prev.callback = self._prev_cb()
        self.add_item(prev)
        nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary, row=4,
                                disabled=(self.page >= self.total_pages - 1))
        nxt.callback = self._next_cb()
        self.add_item(nxt)
        close = discord.ui.Button(label="Закрыть", emoji="✖️",
                                  style=discord.ButtonStyle.danger, row=4)
        close.callback = self._close_cb()
        self.add_item(close)

    def _make_add_cb(self, user_id):
        async def cb(interaction):
            await interaction.response.defer(ephemeral=True)
            if voice_leaders.get(self.channel_id) != interaction.user.id:
                await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
                return
            trusted_users[self.channel_id].add(user_id)
            channel = bot.get_channel(self.channel_id)
            if channel:
                m = channel.guild.get_member(user_id)
                await interaction.followup.send(
                    f"✅ {m.display_name if m else user_id} добавлен.", ephemeral=True)
                await safe_edit_original(interaction,
                                         embed=build_whitelist_add_embed(channel, 0),
                                         view=WhitelistAddSelectView(channel, page=0))
        return cb

    def _prev_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(interaction,
                                     embed=build_whitelist_add_embed(channel, self.page - 1),
                                     view=WhitelistAddSelectView(channel, page=self.page - 1))
        return cb

    def _next_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(interaction,
                                     embed=build_whitelist_add_embed(channel, self.page + 1),
                                     view=WhitelistAddSelectView(channel, page=self.page + 1))
        return cb

    def _close_cb(self):
        async def cb(interaction):
            try:
                await interaction.response.defer()
                await interaction.delete_original_response()
            except (discord.NotFound, discord.HTTPException):
                pass
        return cb


class WhitelistRemoveSelectView(discord.ui.View):
    def __init__(self, channel, page=0):
        super().__init__(timeout=180)
        self.channel_id = channel.id
        trusted = list(trusted_users.get(channel.id, set()))
        self.total_pages = max(1, (len(trusted) + PER_PAGE - 1) // PER_PAGE)
        self.page = max(0, min(page, self.total_pages - 1))
        start = self.page * PER_PAGE
        for i, uid in enumerate(trusted[start:start + PER_PAGE]):
            m = channel.guild.get_member(uid)
            label = (m.display_name if m else f"id={uid}")[:18]
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=i // 5)
            btn.callback = self._make_rem_cb(uid)
            self.add_item(btn)
        prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.primary, row=4,
                                 disabled=(self.page == 0))
        prev.callback = self._prev_cb()
        self.add_item(prev)
        nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary, row=4,
                                disabled=(self.page >= self.total_pages - 1))
        nxt.callback = self._next_cb()
        self.add_item(nxt)
        close = discord.ui.Button(label="Закрыть", emoji="✖️",
                                  style=discord.ButtonStyle.danger, row=4)
        close.callback = self._close_cb()
        self.add_item(close)

    def _make_rem_cb(self, user_id):
        async def cb(interaction):
            await interaction.response.defer(ephemeral=True)
            if voice_leaders.get(self.channel_id) != interaction.user.id:
                await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
                return
            trusted_users[self.channel_id].discard(user_id)
            channel = bot.get_channel(self.channel_id)
            if channel:
                m = channel.guild.get_member(user_id)
                await interaction.followup.send(
                    f"✅ {m.display_name if m else user_id} убран.", ephemeral=True)
                await safe_edit_original(interaction,
                                         embed=build_whitelist_remove_embed(channel, 0),
                                         view=WhitelistRemoveSelectView(channel, page=0))
        return cb

    def _prev_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(interaction,
                                     embed=build_whitelist_remove_embed(channel, self.page - 1),
                                     view=WhitelistRemoveSelectView(channel, page=self.page - 1))
        return cb

    def _next_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(interaction,
                                     embed=build_whitelist_remove_embed(channel, self.page + 1),
                                     view=WhitelistRemoveSelectView(channel, page=self.page + 1))
        return cb

    def _close_cb(self):
        async def cb(interaction):
            try:
                await interaction.response.defer()
                await interaction.delete_original_response()
            except (discord.NotFound, discord.HTTPException):
                pass
        return cb


# ============================================================
# ВЫБОР УЧАСТНИКА
# ============================================================
ACTION_META = {
    "kick":     {"title": "🦶 Кикнуть — выбери участника", "color": discord.Color.red()},
    "mute":     {"title": "🔇 Микро — выбери участника",   "color": discord.Color.orange()},
    "deaf":     {"title": "🎧 Уши — выбери участника",     "color": discord.Color.blue()},
    "transfer": {"title": "👑 Передать лидерство",         "color": discord.Color.gold()},
}
PER_PAGE = 20


class MemberButton(discord.ui.Button):
    def __init__(self, member, action, channel_id, row):
        suffix = voice_flags(member)
        super().__init__(label=f"{member.display_name[:18]}{suffix}",
                         style=discord.ButtonStyle.secondary, row=row)
        self.member_id = member.id
        self.action = action
        self.channel_id = channel_id

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
            return
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return
        target = channel.guild.get_member(self.member_id)
        if not target:
            await interaction.followup.send("Участник не найден.", ephemeral=True)
            return
        if not target.voice or target.voice.channel != channel:
            await interaction.followup.send(
                f"🚫 {target.display_name} уже не в канале.", ephemeral=True)
            return
        leader = channel.guild.get_member(interaction.user.id)
        leader_name = leader.display_name if leader else "владелец"

        try:
            if self.action == "kick":
                await target.move_to(None)
                stats_bump(channel.id, "kicks", 1)
                msg = f"🦶 {target.display_name} выкинут."
                await notify_dm(target, content=(
                    f"🦶 **{leader_name}** кикнул вас из **{channel.name}**."))
            elif self.action == "mute":
                new_state = not target.voice.mute
                await target.edit(mute=new_state)
                stats_bump(channel.id, "mutes", 1)
                msg = f"{'🔇' if new_state else '🔊'} {target.display_name}: микро {'выкл' if new_state else 'вкл'}."
                await notify_dm(target, content=(
                    f"{'🔇' if new_state else '🔊'} **{leader_name}** "
                    f"{'замьютил' if new_state else 'размьютил'} вас в **{channel.name}**."))
            elif self.action == "deaf":
                new_state = not target.voice.deaf
                await target.edit(deafen=new_state)
                stats_bump(channel.id, "deafs", 1)
                msg = f"{'🎧' if new_state else '🔊'} {target.display_name}: уши {'выкл' if new_state else 'вкл'}."
                await notify_dm(target, content=(
                    f"{'🎧' if new_state else '🔊'} **{leader_name}** "
                    f"{'заглушил' if new_state else 'разглушил'} вас в **{channel.name}**."))
            elif self.action == "transfer":
                q = voice_queues.get(self.channel_id, deque())
                if target.id in q:
                    q.remove(target.id)
                q.appendleft(target.id)
                voice_leaders[self.channel_id] = target.id
                reset_stats(self.channel_id, target.id)
                stats_track_join(self.channel_id, target.id)
                await notify_dm(target, content=(
                    f"👑 **{leader_name}** передал вам владение **{channel.name}**."))
                if leader:
                    await notify_dm(leader, content=(
                        f"👑 Вы передали владение **{channel.name}** — **{target.display_name}**."))
                await interaction.followup.send(
                    f"👑 Лидерство передано: {target.display_name}.", ephemeral=True)
                await refresh_lock_message(channel)
                return
            else:
                msg = "Неизвестное действие."
        except discord.Forbidden:
            await interaction.followup.send(
                "🚫 У бота нет прав или роль ниже.", ephemeral=True)
            return
        await interaction.followup.send(msg, ephemeral=True)
        channel2 = bot.get_channel(self.channel_id)
        if channel2:
            await safe_edit_original(
                interaction,
                embed=build_member_select_embed(channel2, self.action),
                view=MemberSelectView(channel2, action=self.action, page=0),
            )


class MemberSelectView(discord.ui.View):
    def __init__(self, channel, action, page=0):
        super().__init__(timeout=180)
        self.channel_id = channel.id
        self.action = action
        leader_id = voice_leaders.get(channel.id)
        members = [m for m in channel.members if not m.bot and m.id != leader_id]
        self.total_pages = max(1, (len(members) + PER_PAGE - 1) // PER_PAGE)
        self.page = max(0, min(page, self.total_pages - 1))
        start = self.page * PER_PAGE
        for i, m in enumerate(members[start:start + PER_PAGE]):
            self.add_item(MemberButton(m, action, channel.id, row=i // 5))
        prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.primary, row=4,
                                 disabled=(self.page == 0))
        prev.callback = self._prev_cb()
        self.add_item(prev)
        if self.total_pages > 1:
            self.add_item(discord.ui.Button(label=f"Стр. {self.page + 1}/{self.total_pages}",
                                            style=discord.ButtonStyle.secondary, row=4, disabled=True))
        nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary, row=4,
                                disabled=(self.page >= self.total_pages - 1))
        nxt.callback = self._next_cb()
        self.add_item(nxt)
        close = discord.ui.Button(label="Закрыть", emoji="✖️",
                                  style=discord.ButtonStyle.danger, row=4)
        close.callback = self._close_cb()
        self.add_item(close)

    def _prev_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(
                interaction,
                embed=build_member_select_embed(channel, self.action),
                view=MemberSelectView(channel, self.action, page=self.page - 1))
        return cb

    def _next_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(
                interaction,
                embed=build_member_select_embed(channel, self.action),
                view=MemberSelectView(channel, self.action, page=self.page + 1))
        return cb

    def _close_cb(self):
        async def cb(interaction):
            try:
                await interaction.response.defer()
                await interaction.delete_original_response()
            except (discord.NotFound, discord.HTTPException):
                pass
        return cb


def build_member_select_embed(channel, action):
    meta = ACTION_META.get(action, {"title": "Выбор", "color": discord.Color.blurple()})
    leader_id = voice_leaders.get(channel.id)
    leader = channel.guild.get_member(leader_id) if leader_id else None
    members = [m for m in channel.members if not m.bot and m.id != leader_id]
    if members:
        lines = [f"• {m.display_name}{voice_flags(m)}" for m in members[:30]]
        desc = "\n".join(lines)
        if len(members) > 30:
            desc += f"\n… и ещё {len(members) - 30}"
    else:
        desc = "Список пуст 🤷"
    embed = discord.Embed(title=meta["title"], description=desc, color=meta["color"])
    embed.set_footer(text=f"Канал: {channel.name} • Лидер: "
                          f"{leader.display_name if leader else '—'}")
    return embed


# ============================================================
# БАНЫ
# ============================================================
class BanTypeView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=180)
        self.channel_id = channel.id

    async def _check(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
            return None
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return None
        return channel

    @discord.ui.button(label="⏳ Забанить на время",
                       style=discord.ButtonStyle.primary, row=0)
    async def temp_btn(self, interaction, button):
        channel = await self._check(interaction)
        if not channel:
            return
        view = BanMemberSelectView(channel, ban_kind="temp", page=0)
        embed = build_ban_member_select_embed(channel, "temp", 0)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🔒 Забанить навсегда",
                       style=discord.ButtonStyle.danger, row=0)
    async def perm_btn(self, interaction, button):
        channel = await self._check(interaction)
        if not channel:
            return
        view = BanMemberSelectView(channel, ban_kind="perm", page=0)
        embed = build_ban_member_select_embed(channel, "perm", 0)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


def build_ban_member_select_embed(channel, ban_kind, page):
    leader_id = voice_leaders.get(channel.id)
    members = [m for m in channel.guild.members
               if not m.bot and m.id != leader_id
               and not is_banned(channel.id, m.id)
               and not is_bot_owner(m)]
    start = page * PER_PAGE
    lines = [f"• {m.display_name}" for m in members[start:start + PER_PAGE]]
    desc = "\n".join(lines) if lines else "Некого банить 🤷"
    title = ("⏳ Временный бан — выбери участника" if ban_kind == "temp"
             else "🔒 Постоянный бан — выбери участника")
    return discord.Embed(title=title, description=desc, color=discord.Color.dark_red())


class BanMemberSelectView(discord.ui.View):
    def __init__(self, channel, ban_kind, page=0):
        super().__init__(timeout=180)
        self.channel_id = channel.id
        self.ban_kind = ban_kind
        leader_id = voice_leaders.get(channel.id)
        members = [m for m in channel.guild.members
                   if not m.bot and m.id != leader_id
                   and not is_banned(channel.id, m.id)
                   and not is_bot_owner(m)]
        self.total_pages = max(1, (len(members) + PER_PAGE - 1) // PER_PAGE)
        self.page = max(0, min(page, self.total_pages - 1))
        start = self.page * PER_PAGE
        for i, m in enumerate(members[start:start + PER_PAGE]):
            btn = discord.ui.Button(label=m.display_name[:18],
                                    style=discord.ButtonStyle.secondary, row=i // 5)
            btn.callback = self._make_cb(m.id)
            self.add_item(btn)
        prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.primary, row=4,
                                 disabled=(self.page == 0))
        prev.callback = self._prev_cb()
        self.add_item(prev)
        nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary, row=4,
                                disabled=(self.page >= self.total_pages - 1))
        nxt.callback = self._next_cb()
        self.add_item(nxt)
        close = discord.ui.Button(label="Закрыть", emoji="✖️",
                                  style=discord.ButtonStyle.danger, row=4)
        close.callback = self._close_cb()
        self.add_item(close)

    def _make_cb(self, user_id):
        async def cb(interaction):
            await interaction.response.defer(ephemeral=True)
            if voice_leaders.get(self.channel_id) != interaction.user.id:
                await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
                return
            channel = bot.get_channel(self.channel_id)
            if not channel:
                await interaction.followup.send("Канал не найден.", ephemeral=True)
                return
            if self.ban_kind == "perm":
                await interaction.followup.send_modal(
                    PermBanModal(channel.id, user_id, interaction.user.id))
            else:
                await interaction.followup.send_modal(
                    TempBanReasonModal(channel.id, user_id, interaction.user.id,
                                       seconds=3600, label="1 час"))
        return cb

    def _prev_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(
                interaction,
                embed=build_ban_member_select_embed(channel, self.ban_kind, self.page - 1),
                view=BanMemberSelectView(channel, self.ban_kind, page=self.page - 1))
        return cb

    def _next_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(
                interaction,
                embed=build_ban_member_select_embed(channel, self.ban_kind, self.page + 1),
                view=BanMemberSelectView(channel, self.ban_kind, page=self.page + 1))
        return cb

    def _close_cb(self):
        async def cb(interaction):
            try:
                await interaction.response.defer()
                await interaction.delete_original_response()
            except (discord.NotFound, discord.HTTPException):
                pass
        return cb


class TempBanReasonModal(discord.ui.Modal, title="⏳ Временный бан"):
    reason_input = discord.ui.TextInput(
        label="Причина блокировки",
        placeholder="Кратко опиши причину",
        required=True, max_length=200,
    )

    def __init__(self, channel_id, target_id, issued_by, seconds, label):
        super().__init__()
        self.channel_id = channel_id
        self.target_id = target_id
        self.issued_by = issued_by
        self.seconds = seconds
        self.label = label

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
            return
        channel = bot.get_channel(self.channel_id)
        if not channel:
            return
        target = channel.guild.get_member(self.target_id)
        if not target:
            await interaction.followup.send("Участник не найден.", ephemeral=True)
            return
        rec = add_ban(channel.id, channel.guild.id, target.id, "temp",
                      self.reason_input.value, interaction.user.id, self.seconds)
        if target.voice and target.voice.channel == channel:
            try:
                await target.move_to(None)
            except discord.Forbidden:
                pass
        until = rec["expires_at"]
        await notify_dm(target, content=(
            f"⏳ **{interaction.user.display_name}** забанил вас в **{channel.name}** "
            f"на **{self.label}**.\n📝 Причина: **{self.reason_input.value}**\n"
            f"⏳ До: <t:{int(until)}:f>"))
        await interaction.followup.send(
            f"⏳ **{target.display_name}** забанен на **{self.label}**.\n"
            f"📝 Причина: {self.reason_input.value}\n⏳ До: <t:{int(until)}:f>",
            ephemeral=True)
        await refresh_lock_message(channel)


class PermBanModal(discord.ui.Modal, title="🔒 Постоянный бан"):
    reason_input = discord.ui.TextInput(
        label="Причина блокировки",
        placeholder="Кратко опиши причину",
        required=True, max_length=200,
    )

    def __init__(self, channel_id, target_id, issued_by):
        super().__init__()
        self.channel_id = channel_id
        self.target_id = target_id
        self.issued_by = issued_by

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
            return
        channel = bot.get_channel(self.channel_id)
        if not channel:
            return
        target = channel.guild.get_member(self.target_id)
        if not target:
            await interaction.followup.send("Участник не найден.", ephemeral=True)
            return
        add_ban(channel.id, channel.guild.id, target.id, "perm",
                self.reason_input.value, interaction.user.id)
        if target.voice and target.voice.channel == channel:
            try:
                await target.move_to(None)
            except discord.Forbidden:
                pass
        await notify_dm(target, content=(
            f"🚫 **{interaction.user.display_name}** забанил вас навсегда "
            f"в **{channel.name}**.\n📝 Причина: **{self.reason_input.value}**"))
        await interaction.followup.send(
            f"🔒 **{target.display_name}** забанен навсегда.\n"
            f"📝 Причина: {self.reason_input.value}",
            ephemeral=True)
        await refresh_lock_message(channel)


class BanListView(discord.ui.View):
    def __init__(self, channel, page=0):
        super().__init__(timeout=180)
        self.channel_id = channel.id
        entries = list(banned_users.get(channel.id, {}).items())
        self.total_pages = max(1, (len(entries) + 5 - 1) // 5)
        self.page = max(0, min(page, self.total_pages - 1))
        start = self.page * 5
        for uid, rec in entries[start:start + 5]:
            btn = discord.ui.Button(label="Разбанить", emoji="✅",
                                    style=discord.ButtonStyle.success,
                                    row=len(self.children))
            btn.callback = self._make_unban_cb(uid)
            self.add_item(btn)
        if self.total_pages > 1:
            prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.primary, row=4,
                                     disabled=(self.page == 0))
            prev.callback = self._prev_cb()
            self.add_item(prev)
            nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary, row=4,
                                    disabled=(self.page >= self.total_pages - 1))
            nxt.callback = self._next_cb()
            self.add_item(nxt)
        close = discord.ui.Button(label="Закрыть", emoji="✖️",
                                  style=discord.ButtonStyle.danger, row=4)
        close.callback = self._close_cb()
        self.add_item(close)

    def _make_unban_cb(self, user_id):
        async def cb(interaction):
            await interaction.response.defer(ephemeral=True)
            if voice_leaders.get(self.channel_id) != interaction.user.id:
                await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
                return
            ok = remove_ban(self.channel_id, user_id)
            if ok:
                await interaction.followup.send(f"✅ <@{user_id}> разбанен.", ephemeral=True)
            else:
                await interaction.followup.send("🚫 Запись не найдена.", ephemeral=True)
            channel = bot.get_channel(self.channel_id)
            if channel:
                await safe_edit_original(interaction,
                                         embed=build_banlist_embed(channel, 0),
                                         view=BanListView(channel, 0))
        return cb

    def _prev_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(interaction,
                                     embed=build_banlist_embed(channel, self.page - 1),
                                     view=BanListView(channel, self.page - 1))
        return cb

    def _next_cb(self):
        async def cb(interaction):
            await interaction.response.defer()
            channel = bot.get_channel(self.channel_id)
            if not channel:
                return
            await safe_edit_original(interaction,
                                     embed=build_banlist_embed(channel, self.page + 1),
                                     view=BanListView(channel, self.page + 1))
        return cb

    def _close_cb(self):
        async def cb(interaction):
            try:
                await interaction.response.defer()
                await interaction.delete_original_response()
            except (discord.NotFound, discord.HTTPException):
                pass
        return cb


def build_banlist_embed(channel, page):
    entries = list(banned_users.get(channel.id, {}).items())
    if not entries:
        return discord.Embed(title="📋 Список банов", description="Пусто 🤷",
                             color=discord.Color.greyple())
    start = page * 5
    lines = []
    for uid, rec in entries[start:start + 5]:
        m = channel.guild.get_member(uid)
        name = m.display_name if m else f"id={uid}"
        btype = "⏳ Временный" if rec.get("type") == "temp" else "🔒 Постоянный"
        exp = rec.get("expires_at")
        exp_str = f"<t:{int(exp)}:R>" if exp else "Навсегда"
        issuer = channel.guild.get_member(rec.get("issued_by"))
        lines.append(
            f"**{name}** (`{uid}`)\n"
            f"• Тип: {btype}\n"
            f"• Причина: {rec.get('reason', '—')}\n"
            f"• Выдал: {issuer.display_name if issuer else rec.get('issued_by')}\n"
            f"• Осталось: {exp_str}"
        )
    return discord.Embed(
        title="📋 Список банов",
        description="\n\n".join(lines),
        color=discord.Color.dark_red(),
    ).set_footer(text=f"Стр. {page + 1}/{max(1, (len(entries) + 4) // 5)}")


# ============================================================
# ОЧИСТКА
# ============================================================
class ClearConfirmView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=120)
        self.channel_id = channel.id

    async def _check(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
            return None
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return None
        return channel

    @discord.ui.button(label="✅ Да, очистить", style=discord.ButtonStyle.danger, row=0)
    async def confirm(self, interaction, button):
        channel = await self._check(interaction)
        if not channel:
            return
        await do_clear_channel(channel, interaction)
        try:
            await interaction.delete_original_response()
        except (discord.NotFound, discord.HTTPException):
            pass

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction, button):
        try:
            await interaction.response.defer()
            await interaction.delete_original_response()
        except (discord.NotFound, discord.HTTPException):
            pass


async def do_clear_channel(channel, interaction):
    cid = channel.id
    orig = original_limits.get(cid, 0)
    custom_limits.pop(cid, None)
    try:
        await channel.edit(user_limit=orig, reason="Мазафака: очистка")
    except (discord.Forbidden, discord.HTTPException):
        pass
    locked_channels.discard(cid)
    whitelist_mode.discard(cid)
    trusted_users.pop(cid, None)
    banned_users.pop(cid, None)
    leader_id = voice_leaders.get(cid)
    if leader_id:
        reset_stats(cid, leader_id)
    await refresh_lock_message(channel)
    await interaction.followup.send(
        "🧹 Комната очищена. Все настройки владельца сброшены.", ephemeral=True)


# ============================================================
# !settings
# ============================================================
class SettingsView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        dm_on = dm_enabled(self.user_id)
        dm_btn = discord.ui.Button(
            label=f"ЛС-уведомления: {'ВКЛ ✅' if dm_on else 'ВЫКЛ ❌'}",
            style=discord.ButtonStyle.success if dm_on else discord.ButtonStyle.danger,
            row=0,
        )
        dm_btn.callback = self._make_dm_callback()
        self.add_item(dm_btn)
        mode = get_panel_ping_mode(self.user_id)
        ping_btn = discord.ui.Button(
            label=f"Пинг панели: {PANEL_PING_LABELS[mode]}",
            style=discord.ButtonStyle.primary, row=1,
        )
        ping_btn.callback = self._make_ping_callback()
        self.add_item(ping_btn)

    def _make_dm_callback(self):
        async def cb(interaction):
            if interaction.user.id != self.user_id:
                await safe_respond(interaction, "🚫 Это не твоя панель.")
                return
            dm_notifications[self.user_id] = not dm_enabled(self.user_id)
            save_settings()
            self._rebuild()
            await interaction.response.edit_message(
                embed=build_settings_embed(self.user_id, interaction.user), view=self)
        return cb

    def _make_ping_callback(self):
        async def cb(interaction):
            if interaction.user.id != self.user_id:
                await safe_respond(interaction, "🚫 Это не твоя панель.")
                return
            cur = get_panel_ping_mode(self.user_id)
            idx = PANEL_PING_CYCLE.index(cur)
            new_mode = PANEL_PING_CYCLE[(idx + 1) % len(PANEL_PING_CYCLE)]
            set_panel_ping_mode(self.user_id, new_mode)
            save_settings()
            self._rebuild()
            await interaction.response.edit_message(
                embed=build_settings_embed(self.user_id, interaction.user), view=self)
            cid = member_channel.get(self.user_id)
            if cid:
                ch = bot.get_channel(cid)
                if ch and voice_leaders.get(cid) == self.user_id:
                    await refresh_lock_message(ch)
        return cb


def build_settings_embed(user_id, user=None):
    dm_on = dm_enabled(user_id)
    mode = get_panel_ping_mode(user_id)
    embed = discord.Embed(
        title="⚙️ Мои настройки — Мазафака Войс",
        description=(
            f"Пользователь: **{user.display_name if user else '—'}**\n\n"
            "**ЛС-уведомления** — бот пишет тебе в ЛС, когда владелец войса "
            "применяет к тебе действия.\n"
            "**Пинг панели** — как бот упоминает тебя в панели войса."
        ),
        color=discord.Color.green() if dm_on else discord.Color.red(),
    )
    embed.add_field(
        name="Текущее состояние",
        value=(
            f"🔔 ЛС-уведомления: **{'ВКЛ ✅' if dm_on else 'ВЫКЛ ❌'}**\n"
            f"📣 Пинг панели: **{PANEL_PING_LABELS[mode]}**"
        ),
        inline=False,
    )
    return embed


@bot.command(name="settings", aliases=["настройки"])
@commands.guild_only()
async def settings_cmd(ctx):
    embed = build_settings_embed(ctx.author.id, ctx.author)
    view = SettingsView(ctx.author.id)
    await safe_reply(ctx, embed=embed, view=view)


@settings_cmd.error
async def settings_cmd_error(ctx, error):
    if isinstance(error, commands.NoPrivateMessage):
        await safe_reply(ctx, "🚫 Команда только для серверов.")


# ============================================================
# АВТО-КИК
# ============================================================
async def enforce_limit_on_join(channel, member):
    limit = get_limit(channel)
    if not limit or limit <= 0:
        return False
    leader_id = voice_leaders.get(channel.id)
    if member.id == leader_id:
        return False
    humans = [m for m in channel.members if not m.bot]
    if len(humans) <= limit:
        return False
    try:
        await member.move_to(None)
    except discord.Forbidden:
        return False
    remove_member_from_queue(channel.id, member.id)
    leader = channel.guild.get_member(leader_id) if leader_id else None
    leader_name = leader.display_name if leader else "владелец"
    await notify_dm(member, content=(
        f"👥 В войсе **{channel.name}** лимит **{limit}**.\n"
        f"Владелец **{leader_name}** — мест нет."))
    return True


# ============================================================
# СБРОС
# ============================================================
async def reset_channel_state(channel):
    cid = channel.id
    orig = original_limits.get(cid, 0)
    if custom_limits.get(cid) != orig or channel.user_limit != orig:
        try:
            await channel.edit(user_limit=orig, reason="Мазафака: сброс")
        except (discord.Forbidden, discord.HTTPException):
            pass
    custom_limits.pop(cid, None)
    locked_channels.discard(cid)
    whitelist_mode.discard(cid)
    trusted_users.pop(cid, None)
    banned_users.pop(cid, None)
    clean_channel(cid)
    channel_stats.pop(cid, None)
    await refresh_lock_message(channel)


# ============================================================
# СОБЫТИЯ
# ============================================================
@bot.event
async def on_ready():
    log.info(f"Бот запущен: {bot.user}")
    for guild in bot.guilds:
        for ch in guild.voice_channels:
            if not everyone_can_connect(ch):
                initially_locked.add(ch.id)
            original_limits[ch.id] = ch.user_limit
    if not rotate_status.is_running():
        rotate_status.start()
    if not auto_cleanup_bans.is_running():
        auto_cleanup_bans.start()
    await notify_all_voice_channels("🟢 **Бот запущен и готов к работе!**")


@tasks.loop(minutes=1)
async def auto_cleanup_bans():
    cleanup_expired_bans()


@auto_cleanup_bans.before_loop
async def before_cleanup():
    await bot.wait_until_ready()


@bot.event
async def on_disconnect():
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True
    try:
        save_settings()
    except Exception:
        pass
    try:
        await notify_all_voice_channels("🔴 **Бот выключается...**")
    except Exception:
        pass


@bot.event
async def on_voice_state_update(member, before, after):
    if not is_human(member):
        return
    old_ch, new_ch = before.channel, after.channel
    if old_ch == new_ch:
        if new_ch and voice_leaders.get(new_ch.id) == member.id:
            await refresh_lock_message(new_ch)
        return
    if old_ch is not None:
        before_members = list(old_ch.members)
        await handle_leave(old_ch, member, before_members=before_members)
    if new_ch is not None:
        await handle_join(new_ch, member)


async def handle_join(channel, member):
    cid = channel.id
    if is_bot_owner(member):
        try:
            await channel.send(content="👑 **В войс зашел создатель бота**")
        except (discord.Forbidden, discord.HTTPException):
            pass

    leader_id = voice_leaders.get(cid)
    leader = channel.guild.get_member(leader_id) if leader_id else None
    leader_name = leader.display_name if leader else "владелец"

    if is_banned(cid, member.id) and member.id != leader_id:
        try:
            await member.move_to(None)
        except discord.Forbidden:
            return
        rec = banned_users.get(cid, {}).get(member.id, {})
        exp = rec.get("expires_at")
        exp_str = f"\n⏳ До: <t:{int(exp)}:f>" if exp else "\n🔒 Навсегда"
        await notify_dm(member, content=(
            f"🚫 **{leader_name}** запретил вам вход в **{channel.name}**.\n"
            f"📝 Причина: **{rec.get('reason', '—')}**{exp_str}"))
        return

    if whitelist_enabled(cid) and member.id != leader_id and not is_bot_owner(member):
        if not is_trusted(cid, member.id):
            try:
                await member.move_to(None)
            except discord.Forbidden:
                return
            await notify_dm(member, content=(
                f"🔒 **Режим «Только свои»** в **{channel.name}**.\n"
                f"Владелец **{leader_name}** не добавил вас в доверенные."))
            return

    if is_locked(channel) and member.id != leader_id and not is_bot_owner(member):
        try:
            await member.move_to(None)
        except discord.Forbidden:
            return
        await notify_dm(member, content=(
            f"🔒 **Вам закрыт доступ к войсу**\n"
            f"Сервер: **{channel.guild.name}**\n"
            f"Канал: **{channel.name}**\n"
            f"Владелец **{leader_name}** закрыл вход."))
        return

    if not is_bot_owner(member):
        if await enforce_limit_on_join(channel, member):
            await refresh_lock_message(channel)
            return

    q = voice_queues[cid]
    if not q:
        q.append(member.id)
        voice_leaders[cid] = member.id
        member_channel[member.id] = cid
        ensure_stats(cid, member.id)
        await refresh_lock_message(channel)
        stats_track_join(cid, member.id)
        return

    if member.id in q:
        member_channel[member.id] = cid
        stats_track_join(cid, member.id)
        return

    q.append(member.id)
    member_channel[member.id] = cid
    if cid not in voice_leaders:
        voice_leaders[cid] = q[0]
        ensure_stats(cid, q[0])
    await refresh_lock_message(channel)
    stats_track_join(cid, member.id)


async def handle_leave(channel, member, before_members=None):
    cid = channel.id
    member_channel.pop(member.id, None)
    stats_track_leave(cid, member.id)

    was_leader = (voice_leaders.get(cid) == member.id)
    q = voice_queues.get(cid)
    if q is not None:
        remove_member_from_queue(cid, member.id)

    if before_members is not None:
        remaining = [m for m in before_members if m.id != member.id and not m.bot]
    else:
        remaining = [m for m in channel.members if m.id != member.id and not m.bot]

    if not remaining:
        await reset_channel_state(channel)
        log.info(f"[{channel.guild.name} / 🔊 {channel.name}] пусто — сброс")
        return

    if was_leader:
        new_leader = random.choice(remaining)
        voice_leaders[cid] = new_leader.id
        q = voice_queues.get(cid)
        if q is not None:
            if new_leader.id in q:
                q.remove(new_leader.id)
            q.appendleft(new_leader.id)
        member_channel[new_leader.id] = cid
        reset_stats(cid, new_leader.id)
        stats_track_join(cid, new_leader.id)
        await notify_dm(new_leader, content=(
            f"👑 Вы стали новым владельцем **{channel.name}** "
            f"на сервере **{channel.guild.name}**."))
        await refresh_lock_message(channel)
        return

    if voice_leaders.get(cid):
        await refresh_lock_message(channel)


# ============================================================
# АДМИН-КОМАНДЫ
# ============================================================
@bot.command(name="voices", aliases=["войсы"])
@owner_only()
async def voices_cmd(ctx):
    if not voice_leaders:
        await safe_reply(ctx, "Нет активных войсов.")
        return
    lines = []
    for cid, leader_id in voice_leaders.items():
        ch = ctx.guild.get_channel(cid)
        leader = ctx.guild.get_member(leader_id)
        if not ch:
            continue
        humans = len([m for m in ch.members if not m.bot])
        lock = "🔒" if is_locked(ch) else "🔓"
        lim = get_limit(ch)
        lim_str = f" / лимит {lim}" if lim else ""
        wl = " / whitelist" if whitelist_enabled(cid) else ""
        lines.append(f"{lock} 🔊 **{ch.name}** — 👑 "
                     f"{leader.display_name if leader else leader_id} ({humans} чел{lim_str}{wl})")
    embed = discord.Embed(title="🎧 Активные войсы", description="\n".join(lines),
                         color=discord.Color.blurple())
    await safe_reply(ctx, embed=embed)


@bot.command(name="setleader", aliases=["влад"])
@owner_only()
@commands.guild_only()
async def setleader_cmd(ctx, member: discord.Member, channel: discord.VoiceChannel = None):
    if channel is None:
        if member.voice and member.voice.channel:
            channel = member.voice.channel
        else:
            await safe_reply(ctx, "🚫 Укажи канал: `!setleader @user #войс`")
            return
    cid = channel.id
    q = voice_queues[cid]
    if member.id in q:
        q.remove(member.id)
    q.appendleft(member.id)
    voice_leaders[cid] = member.id
    reset_stats(cid, member.id)
    stats_track_join(cid, member.id)
    if member.voice and member.voice.channel != channel:
        try:
            await member.move_to(channel)
        except discord.Forbidden:
            pass
    await safe_reply(ctx, f"👑 Владелец **{channel.name}** — **{member.display_name}**.")
    await refresh_lock_message(channel)


@bot.command(name="say", aliases=["сказать"])
@owner_only()
async def say_cmd(ctx, channel: discord.TextChannel, *, text: str):
    try:
        await channel.send(text)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await safe_reply(ctx, f"✅ Отправлено в {channel.mention}.", delete_after=5)
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 Нет прав.")


@bot.command(name="embed")
@owner_only()
async def embed_cmd(ctx, channel: discord.TextChannel, title: str, *, description: str):
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    try:
        await channel.send(embed=embed)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await safe_reply(ctx, f"✅ Embed в {channel.mention}.", delete_after=5)
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 Нет прав.")


@bot.command(name="dm", aliases=["лс"])
@owner_only()
async def dm_cmd(ctx, member: discord.Member, *, text: str):
    try:
        await member.send(text)
        await safe_reply(ctx, f"✅ ЛС **{member.display_name}**.", delete_after=5)
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 У пользователя закрыты ЛС.")


@bot.command(name="del")
@owner_only()
async def del_cmd(ctx, message_id: int, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    try:
        msg = await channel.fetch_message(message_id)
        await msg.delete()
        await safe_reply(ctx, "🗑 Удалено.", delete_after=5)
    except discord.NotFound:
        await safe_reply(ctx, "🚫 Не найдено.")
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 Нет прав.")


@bot.command(name="vkick", aliases=["вкик"])
@owner_only()
@commands.guild_only()
async def vkick_cmd(ctx, member: discord.Member):
    if not member.voice or not member.voice.channel:
        await safe_reply(ctx, "🚫 Не в войсе.")
        return
    try:
        ch = member.voice.channel
        await member.move_to(None)
        await safe_reply(ctx, f"🦶 {member.display_name} выкинут из **{ch.name}**.")
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 Нет прав.")


@bot.command(name="vreset", aliases=["сброс"])
@owner_only()
@commands.guild_only()
async def vreset_cmd(ctx, channel: discord.VoiceChannel = None):
    if channel is None:
        if ctx.author.voice and ctx.author.voice.channel:
            channel = ctx.author.voice.channel
        else:
            await safe_reply(ctx, "🚫 Укажи канал.")
            return
    await reset_channel_state(channel)
    await safe_reply(ctx, f"♻️ Сброшен **{channel.name}**.")


@bot.command(name="vbans", aliases=["баны"])
@owner_only()
@commands.guild_only()
async def vbans_cmd(ctx, channel: discord.VoiceChannel):
    entries = banned_users.get(channel.id, {})
    if not entries:
        await safe_reply(ctx, f"В **{channel.name}** нет банов.")
        return
    lines = []
    for uid, rec in entries.items():
        m = ctx.guild.get_member(uid)
        btype = "⏳" if rec.get("type") == "temp" else "🔒"
        exp = rec.get("expires_at")
        exp_str = f"<t:{int(exp)}:R>" if exp else "навсегда"
        lines.append(f"{btype} {m.mention if m else uid} — {rec.get('reason', '—')} ({exp_str})")
    embed = discord.Embed(title=f"🚫 Баны — {channel.name}",
                         description="\n".join(lines), color=discord.Color.dark_red())
    await safe_reply(ctx, embed=embed)


@bot.command(name="vclear", aliases=["клеарбаны"])
@owner_only()
@commands.guild_only()
async def vclear_cmd(ctx, channel: discord.VoiceChannel):
    banned_users.pop(channel.id, None)
    await safe_reply(ctx, f"✅ Все баны **{channel.name}** сняты.")


@bot.command(name="adminhelp", aliases=["апомощь"])
@owner_only()
async def adminhelp_cmd(ctx):
    embed = discord.Embed(title="🛠 Админ-команды", color=discord.Color.dark_green())
    embed.add_field(name="👑 Войсы", value=(
        "`!voices` — список войсов\n"
        "`!setleader @user [#ch]` — сменить владельца\n"
        "`!vkick @user` — выкинуть из войса\n"
        "`!vreset [#ch]` — сбросить войс\n"
        "`!vbans #ch` — список банов\n"
        "`!vclear #ch` — снять все баны"
    ), inline=False)
    embed.add_field(name="💬 Сообщения", value=(
        "`!say #ch текст`\n`!embed #ch \"Заголовок\" текст`\n"
        "`!dm @user текст`\n`!del ID [#ch]`"
    ), inline=False)
    await safe_reply(ctx, embed=embed)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await safe_reply(ctx, f"🚫 Не хватает аргумента: `{error.param.name}`")
    elif isinstance(error, commands.BadArgument):
        await safe_reply(ctx, f"🚫 Неверный аргумент: {error}")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        log.warning(f"Ошибка команды: {error}")


# ============================================================
# ЗАПУСК
# ============================================================
def main():
    if not TOKEN:
        log.error("❌ Токен не задан! Установи переменную окружения DISCORD_TOKEN.")
        return
    if not OWNER_IDS:
        log.warning("⚠️ OWNER_ID не задан — админ-команды недоступны никому.")
    if not PANEL_IMAGE_URL:
        log.warning("⚠️ PANEL_IMAGE_URL не задан — картинка панели не будет показана.")

    load_settings()

    # запускаем веб-сервер для Render, чтобы UptimeRobot мог «пинать» бота
    keep_alive()

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        log.error("❌ Неверный токен.")
    except discord.PrivilegedIntentsRequired:
        log.error(
            "❌ Включи привилегированные интенты:\n"
            "   PRESENCE INTENT\n   SERVER MEMBERS INTENT\n   MESSAGE CONTENT INTENT"
        )
    except KeyboardInterrupt:
        log.info("Бот остановлен.")


if __name__ == "__main__":
    main()
