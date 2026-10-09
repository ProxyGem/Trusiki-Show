import os
import json
import signal
import asyncio
import random
import logging
from collections import defaultdict, deque

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from keep_alive import keep_alive

# Загружаем .env (локально), на Render переменные берутся из Environment
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

# ============================================================

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
# СЛУЧАЙНАЯ СМЕНА СТАТУСА
# ============================================================
STATUS_PHRASES = [
    "хелоу мазафако",
    "тупо мазасрака",
    "я тут просто чиллю",
    "не пиши мне больше, иза тебя я потерял всех своих друзей",
    "вертитоп лашара",
    "мазафако",
    "войсы под контролем",
    "кого кикнуть сегодня?",
    "кого замутить сегодня?",
    "мазафака на связи",
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
        log.info(f"Статус обновлён: {phrase}")
    except Exception as e:
        log.warning(f"Не удалось сменить статус: {e}")


@rotate_status.before_loop
async def before_rotate_status():
    await bot.wait_until_ready()


# ---------- Хранилище ----------
voice_queues: dict[int, deque[int]] = defaultdict(deque)
voice_leaders: dict[int, int] = {}
member_channel: dict[int, int] = {}
lock_messages: dict[int, discord.Message] = {}
locked_channels: set[int] = set()
initially_locked: set[int] = set()
original_limits: dict[int, int] = {}
banned_users: dict[int, set[int]] = defaultdict(set)
custom_limits: dict[int, int] = {}
dm_notifications: dict[int, bool] = defaultdict(lambda: True)

panel_ping_mode: dict[int, str] = defaultdict(lambda: "ping")
PANEL_PING_CYCLE = ["none", "text_ping", "ping"]
PANEL_PING_LABELS = {
    "none": "Без пинга",
    "text_ping": "Текст + пинг",
    "ping": "Только пинг",
}

_shutdown_done = False


# ============================================================
# СОХРАНЕНИЕ / ЗАГРУЗКА ПЕРСОНАЛЬНЫХ НАСТРОЕК
# ============================================================
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        log.info(f"{SETTINGS_FILE} не найден — старт с настройками по умолчанию")
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

    log.info(
        f"Настройки загружены: ЛС={len(dm_notifications)}, "
        f"пинг={len(panel_ping_mode)}"
    )


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


# ---------- Проверка владельца ----------
def is_bot_owner(user: discord.abc.User) -> bool:
    return user.id in OWNER_IDS


def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if not is_bot_owner(ctx.author):
            await ctx.reply("🚫 Только владелец бота может использовать эту команду.",
                            mention_author=False)
            return False
        return True
    return commands.check(predicate)


# ---------- Утилиты ----------
def is_human(member: discord.Member) -> bool:
    return member is not None and not member.bot


def dm_enabled(user_id: int) -> bool:
    return dm_notifications.get(user_id, True)


def get_panel_ping_mode(user_id: int) -> str:
    mode = panel_ping_mode.get(user_id, "ping")
    if mode not in PANEL_PING_CYCLE:
        mode = "ping"
    return mode


def set_panel_ping_mode(user_id: int, mode: str) -> None:
    panel_ping_mode[user_id] = mode


def build_panel_content(user_id: int) -> str:
    mode = get_panel_ping_mode(user_id)
    if mode == "none":
        return "Панель управления"
    if mode == "text_ping":
        return f"Панель управления <@{user_id}>"
    return f"<@{user_id}>"


def clean_channel(channel_id: int) -> None:
    voice_queues.pop(channel_id, None)
    voice_leaders.pop(channel_id, None)
    for mid in [m for m, c in member_channel.items() if c == channel_id]:
        member_channel.pop(mid, None)


def remove_member_from_queue(channel_id: int, member_id: int) -> None:
    q = voice_queues.get(channel_id)
    if q is None:
        return
    try:
        q.remove(member_id)
    except ValueError:
        return


def voice_flags(member: discord.Member) -> str:
    if not member.voice:
        return ""
    flags = []
    if member.voice.mute:
        flags.append("🔇")
    if member.voice.deaf:
        flags.append("🎧")
    return (" " + "".join(flags)) if flags else ""


def everyone_can_connect(channel: discord.VoiceChannel) -> bool:
    ow = channel.overwrites_for(channel.guild.default_role)
    if ow.connect is None:
        return channel.guild.default_role.permissions.connect
    return bool(ow.connect)


async def lock_channel(channel: discord.VoiceChannel) -> bool:
    locked_channels.add(channel.id)
    return True


async def unlock_channel(channel: discord.VoiceChannel) -> bool:
    locked_channels.discard(channel.id)
    return True


def is_locked(channel: discord.VoiceChannel) -> bool:
    return channel.id in locked_channels


def is_banned(channel_id: int, member_id: int) -> bool:
    return member_id in banned_users.get(channel_id, set())


def get_limit(channel: discord.VoiceChannel) -> int:
    if channel.id in custom_limits:
        return custom_limits[channel.id]
    return channel.user_limit or 0


async def apply_limit(channel: discord.VoiceChannel, limit: int) -> bool:
    try:
        await channel.edit(user_limit=limit, reason="Мазафака: лимит")
        custom_limits[channel.id] = limit
        return True
    except discord.Forbidden:
        return False


# ---------- Уведомления ----------
async def notify_dm(member: discord.Member, content: str = None,
                    embed: discord.Embed = None):
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
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning(f"Не могу написать в ЛС {member}: {e}")


def _channel_humans(channel: discord.VoiceChannel) -> list[discord.Member]:
    guild = channel.guild
    result = []
    for member in guild.members:
        if member.bot:
            continue
        vs = member.voice
        if vs and vs.channel and vs.channel.id == channel.id:
            result.append(member)
    return result


async def notify_all_voice_channels(text: str):
    for guild in bot.guilds:
        for channel in guild.voice_channels:
            humans = _channel_humans(channel)
            if not humans:
                continue
            try:
                await channel.send(text)
                log.info(
                    f"[notify] {guild.name} / 🔊 {channel.name}: "
                    f"отправлено ({len(humans)} чел.)"
                )
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning(f"Не могу отправить уведомление в {channel.name}: {e}")


# ---------- Безопасные ответы ----------
async def safe_respond(interaction: discord.Interaction, content: str = None,
                       embed: discord.Embed = None, view: discord.ui.View = None,
                       ephemeral: bool = True):
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
        except discord.HTTPException as e:
            log.warning(f"safe_respond fallback: {e}")
    except discord.HTTPException as e:
        log.warning(f"safe_respond: {e}")


async def safe_edit_original(interaction: discord.Interaction,
                             embed: discord.Embed = None, view: discord.ui.View = None,
                             content: str = None):
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
    except (discord.NotFound, discord.HTTPException) as e:
        log.warning(f"safe_edit_original: {e}")


async def safe_reply(ctx: commands.Context, content: str = None,
                     embed: discord.Embed = None, view: discord.ui.View = None,
                     delete_after: float = None):
    kwargs = {"mention_author": False}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view
    if delete_after is not None:
        kwargs["delete_after"] = delete_after

    try:
        return await ctx.reply(**kwargs)
    except discord.HTTPException:
        try:
            return await ctx.send(**kwargs)
        except discord.HTTPException as e:
            log.warning(f"safe_reply: {e}")
            return None


# ============================================================
# МОДАЛКА ЛИМИТА
# ============================================================
class LimitModal(discord.ui.Modal, title="Лимит участников"):
    limit_input = discord.ui.TextInput(
        label="Максимум участников",
        placeholder="Число от 0 до 99. 0 — без лимита.",
        required=True,
        max_length=2,
    )

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер канала может ставить лимит.", ephemeral=True)
            return

        raw = self.limit_input.value.strip()
        if not raw.isdigit():
            await interaction.followup.send("🚫 Введи целое число от 0 до 99.", ephemeral=True)
            return

        limit = int(raw)
        if not (0 <= limit <= 99):
            await interaction.followup.send("🚫 Допустимо только 0..99.", ephemeral=True)
            return

        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return

        if limit == 0:
            ok = await apply_limit(channel, 0)
            if not ok:
                await interaction.followup.send("🚫 Нет прав Manage Channels.", ephemeral=True)
                return
            await interaction.followup.send("♻️ Лимит снят (без ограничений).", ephemeral=True)
            await refresh_lock_message(channel)
            return

        current = len([m for m in channel.members if not m.bot])
        if current > limit:
            leader_id = voice_leaders.get(self.channel_id)
            non_leaders = [m for m in channel.members if not m.bot and m.id != leader_id]
            keep_non_leaders = max(0, limit - 1) if leader_id else limit
            to_kick = non_leaders[keep_non_leaders:]
            for m in to_kick:
                try:
                    await m.move_to(None)
                except discord.Forbidden:
                    pass
                remove_member_from_queue(self.channel_id, m.id)
                await notify_dm(
                    m,
                    content=(
                        f"👥 Владелец войса **{interaction.user.display_name}** установил лимит "
                        f"**{limit}** чел. в **{channel.name}** — вы были выгнаны (превышен лимит)."
                    ),
                )

        ok = await apply_limit(channel, limit)
        if not ok:
            await interaction.followup.send("🚫 Нет прав Manage Channels.", ephemeral=True)
            return

        await interaction.followup.send(f"👥 Лимит: **{limit}** чел.", ephemeral=True)
        await refresh_lock_message(channel)


# ============================================================
# ОКНО ВЫБОРА УЧАСТНИКА
# ============================================================
ACTION_META = {
    "kick":     {"title": "🦶 Кикнуть — выбери участника", "color": discord.Color.red()},
    "mute":     {"title": "🔇 Микро — выбери участника",   "color": discord.Color.orange()},
    "deaf":     {"title": "🎧 Уши — выбери участника",     "color": discord.Color.blue()},
    "transfer": {"title": "👑 Передать лидерство — выбери участника", "color": discord.Color.gold()},
    "ban":      {"title": "🚫 Забанить вход — выбери участника", "color": discord.Color.dark_red()},
    "unban":    {"title": "✅ Разбанить вход — выбери участника", "color": discord.Color.green()},
}

PER_PAGE = 20


class MemberButton(discord.ui.Button):
    def __init__(self, member: discord.Member, action: str, channel_id: int, row: int):
        suffix = voice_flags(member)
        super().__init__(
            label=f"{member.display_name[:18]}{suffix}",
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.member_id = member.id
        self.action = action
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только лидер канала может управлять.", ephemeral=True)
            return

        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return

        target = channel.guild.get_member(self.member_id)
        if not target:
            await interaction.followup.send("Участник не найден.", ephemeral=True)
            return

        if self.action not in ("ban", "unban"):
            if not target.voice or target.voice.channel != channel:
                await interaction.followup.send(f"🚫 {target.display_name} уже не в канале.", ephemeral=True)
                return

        old_leader_id = voice_leaders.get(self.channel_id)
        guild = channel.guild
        leader = guild.get_member(interaction.user.id)
        leader_name = leader.display_name if leader else "владелец"

        try:
            if self.action == "kick":
                await target.move_to(None)
                msg = f"🦶 {target.display_name} выкинут из канала."
                await notify_dm(
                    target,
                    content=(
                        f"🦶 Владелец войса **{leader_name}** кикнул вас "
                        f"из канала **{channel.name}** на сервере **{guild.name}**."
                    ),
                )
            elif self.action == "mute":
                new_state = not target.voice.mute
                await target.edit(mute=new_state)
                msg = f"{'🔇' if new_state else '🔊'} {target.display_name}: микро {'выкл' if new_state else 'вкл'}."
                await notify_dm(
                    target,
                    content=(
                        f"{'🔇' if new_state else '🔊'} Владелец войса **{leader_name}** "
                        f"{'замьютил' if new_state else 'размьютил'} вас в **{channel.name}**."
                    ),
                )
            elif self.action == "deaf":
                new_state = not target.voice.deaf
                await target.edit(deafen=new_state)
                msg = f"{'🎧' if new_state else '🔊'} {target.display_name}: уши {'выкл' if new_state else 'вкл'}."
                await notify_dm(
                    target,
                    content=(
                        f"{'🎧' if new_state else '🔊'} Владелец войса **{leader_name}** "
                        f"{'заглушил' if new_state else 'разглушил'} вас в **{channel.name}**."
                    ),
                )
            elif self.action == "transfer":
                q = voice_queues.get(self.channel_id, deque())
                if target.id in q:
                    q.remove(target.id)
                q.appendleft(target.id)
                voice_leaders[self.channel_id] = target.id
                msg = f"👑 Лидерство передано: {target.display_name}."
                await notify_dm(
                    target,
                    content=(
                        f"👑 Владелец войса **{leader_name}** передал вам владение "
                        f"каналом **{channel.name}**."
                    ),
                )
                if leader:
                    await notify_dm(
                        leader,
                        content=(
                            f"👑 Вы передали владение каналом **{channel.name}** "
                            f"пользователю **{target.display_name}**. Вы больше не владелец."
                        ),
                    )
            elif self.action == "ban":
                if target.id == old_leader_id:
                    await interaction.followup.send("🚫 Нельзя забанить самого себя.", ephemeral=True)
                    return
                banned_users[self.channel_id].add(target.id)
                if target.voice and target.voice.channel == channel:
                    try:
                        await target.move_to(None)
                    except discord.Forbidden:
                        pass
                remove_member_from_queue(self.channel_id, target.id)
                msg = f"🚫 {target.display_name} забанен во входе в канал."
                await notify_dm(
                    target,
                    content=(
                        f"🚫 **Владелец войса {leader_name} запретил вам вход** "
                        f"в канал **{channel.name}** на сервере **{guild.name}**."
                    ),
                )
            elif self.action == "unban":
                banned_users[self.channel_id].discard(target.id)
                msg = f"✅ {target.display_name} разбанен."
                await notify_dm(
                    target,
                    content=(
                        f"✅ Владелец войса **{leader_name}** **снял запрет** "
                        f"на вход в **{channel.name}**."
                    ),
                )
            else:
                msg = "Неизвестное действие."
        except discord.Forbidden:
            await interaction.followup.send(
                "🚫 У бота нет нужных прав или его роль ниже.", ephemeral=True
            )
            return

        await interaction.followup.send(msg, ephemeral=True)

        channel2 = bot.get_channel(self.channel_id)
        if channel2:
            new_view = MemberSelectView(channel2, action=self.action, page=0)
            new_embed = build_member_select_embed(channel2, self.action)
            await safe_edit_original(interaction, embed=new_embed, view=new_view)

        if self.action == "transfer":
            await refresh_lock_message(channel)


class MemberSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel, action: str, page: int = 0):
        super().__init__(timeout=180)
        self.channel_id = channel.id
        self.action = action
        self.page = page

        if action == "ban":
            members = [
                m for m in channel.guild.members
                if not m.bot
                and m.id != voice_leaders.get(channel.id)
                and not is_banned(channel.id, m.id)
            ]
        elif action == "unban":
            members = [
                channel.guild.get_member(mid)
                for mid in banned_users.get(channel.id, set())
            ]
            members = [m for m in members if m is not None]
        else:
            leader_id = voice_leaders.get(channel.id)
            members = [m for m in channel.members if not m.bot and m.id != leader_id]

        self.total_pages = max(1, (len(members) + PER_PAGE - 1) // PER_PAGE)
        self.page = max(0, min(self.page, self.total_pages - 1))

        start = self.page * PER_PAGE
        end = start + PER_PAGE
        page_members = members[start:end]

        for i, m in enumerate(page_members):
            row = i // 5
            self.add_item(MemberButton(m, action, channel.id, row=row))

        prev_btn = discord.ui.Button(
            label="◀", style=discord.ButtonStyle.primary, row=4,
            disabled=(self.page == 0),
        )
        prev_btn.callback = self._make_prev_callback()
        self.add_item(prev_btn)

        if self.total_pages > 1:
            page_btn = discord.ui.Button(
                label=f"Стр. {self.page + 1}/{self.total_pages}",
                style=discord.ButtonStyle.secondary, row=4, disabled=True,
            )
            self.add_item(page_btn)

        next_btn = discord.ui.Button(
            label="▶", style=discord.ButtonStyle.primary, row=4,
            disabled=(self.page >= self.total_pages - 1),
        )
        next_btn.callback = self._make_next_callback()
        self.add_item(next_btn)

        close_btn = discord.ui.Button(
            label="Закрыть", emoji="✖️",
            style=discord.ButtonStyle.danger, row=4,
        )
        close_btn.callback = self._make_close_callback()
        self.add_item(close_btn)

    def _make_prev_callback(self):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()
            if voice_leaders.get(self.channel_id) != interaction.user.id:
                await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
                return
            channel = bot.get_channel(self.channel_id)
            if not channel:
                await interaction.followup.send("Канал не найден.", ephemeral=True)
                return
            view = MemberSelectView(channel, self.action, page=self.page - 1)
            await safe_edit_original(
                interaction, embed=build_member_select_embed(channel, self.action), view=view
            )
        return callback

    def _make_next_callback(self):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()
            if voice_leaders.get(self.channel_id) != interaction.user.id:
                await interaction.followup.send("🚫 Только лидер.", ephemeral=True)
                return
            channel = bot.get_channel(self.channel_id)
            if not channel:
                await interaction.followup.send("Канал не найден.", ephemeral=True)
                return
            view = MemberSelectView(channel, self.action, page=self.page + 1)
            await safe_edit_original(
                interaction, embed=build_member_select_embed(channel, self.action), view=view
            )
        return callback

    def _make_close_callback(self):
        async def callback(interaction: discord.Interaction):
            if voice_leaders.get(self.channel_id) != interaction.user.id:
                await safe_respond(interaction, "🚫 Только лидер.")
                return
            try:
                await interaction.response.defer()
                await interaction.delete_original_response()
            except (discord.NotFound, discord.HTTPException) as e:
                log.warning(f"close: {e}")
        return callback


def build_member_select_embed(channel: discord.VoiceChannel, action: str) -> discord.Embed:
    meta = ACTION_META.get(action, {"title": "Выбор", "color": discord.Color.blurple()})
    leader_id = voice_leaders.get(channel.id)
    leader = channel.guild.get_member(leader_id) if leader_id else None

    if action == "ban":
        members = [
            m for m in channel.guild.members
            if not m.bot
            and m.id != leader_id
            and not is_banned(channel.id, m.id)
        ]
    elif action == "unban":
        members = [
            channel.guild.get_member(mid)
            for mid in banned_users.get(channel.id, set())
        ]
        members = [m for m in members if m is not None]
    else:
        members = [m for m in channel.members if not m.bot and m.id != leader_id]

    if members:
        lines = []
        for m in members[:30]:
            suffix = voice_flags(m)
            lines.append(f"• {m.display_name}{suffix}")
        desc = "\n".join(lines)
        if len(members) > 30:
            desc += f"\n… и ещё {len(members) - 30}"
    else:
        desc = "Список пуст 🤷"

    embed = discord.Embed(title=meta["title"], description=desc, color=meta["color"])

    banned_count = len(banned_users.get(channel.id, set()))
    embed.set_footer(
        text=(
            f"Канал: {channel.name} • Лидер: {leader.display_name if leader else '—'} "
            f"• Забанено: {banned_count}"
        )
    )
    return embed


# ============================================================
# ГЛАВНАЯ ПАНЕЛЬ ЛИДЕРА
# ============================================================
class LeaderPanel(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    async def _require_leader(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        await interaction.response.defer(ephemeral=True)
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return None
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только **лидер канала** может управлять.", ephemeral=True)
            return None
        member = channel.guild.get_member(interaction.user.id)
        if not member or not member.voice or member.voice.channel != channel:
            await interaction.followup.send("🚫 Ты должен быть в своём голосовом канале.", ephemeral=True)
            return None
        return channel

    @discord.ui.button(label="Кикнуть", emoji="🦶", style=discord.ButtonStyle.danger, row=0)
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="kick")
        embed = build_member_select_embed(channel, "kick")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Микро", emoji="🔇", style=discord.ButtonStyle.primary, row=1)
    async def mute_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="mute")
        embed = build_member_select_embed(channel, "mute")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Уши", emoji="🎧", style=discord.ButtonStyle.primary, row=1)
    async def deaf_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="deaf")
        embed = build_member_select_embed(channel, "deaf")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Закрыть вход", emoji="🔒", style=discord.ButtonStyle.success, row=2)
    async def lock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        if is_locked(channel):
            await unlock_channel(channel)
            text = "🔓 Вход открыт для всех."
        else:
            await lock_channel(channel)
            text = "🔒 Вход закрыт для всех."
        await interaction.followup.send(text, ephemeral=True)
        await refresh_lock_message(channel)

    @discord.ui.button(label="Забанить вход", emoji="🚫", style=discord.ButtonStyle.danger, row=2)
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="ban")
        embed = build_member_select_embed(channel, "ban")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Разбанить вход", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def unban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        if not banned_users.get(channel.id):
            await interaction.followup.send("Список банов пуст 🤷", ephemeral=True)
            return
        view = MemberSelectView(channel, action="unban")
        embed = build_member_select_embed(channel, "unban")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Лимит", emoji="👥", style=discord.ButtonStyle.primary, row=3)
    async def limit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("Канал не найден.", ephemeral=True)
            return
        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.response.send_message(
                "🚫 Только **лидер канала** может управлять.", ephemeral=True
            )
            return
        member = channel.guild.get_member(interaction.user.id)
        if not member or not member.voice or member.voice.channel != channel:
            await interaction.response.send_message(
                "🚫 Ты должен быть в своём голосовом канале.", ephemeral=True
            )
            return
        await interaction.response.send_modal(LimitModal(channel.id))

    @discord.ui.button(label="Снять лимит", emoji="♻️", style=discord.ButtonStyle.secondary, row=3)
    async def reset_limit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        ok = await apply_limit(channel, 0)
        text = "♻️ Лимит снят." if ok else "🚫 Не удалось."
        await interaction.followup.send(text, ephemeral=True)
        await refresh_lock_message(channel)

    @discord.ui.button(label="Передать", emoji="👑", style=discord.ButtonStyle.primary, row=4)
    async def transfer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        view = MemberSelectView(channel, action="transfer")
        embed = build_member_select_embed(channel, "transfer")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Очередь", emoji="📋", style=discord.ButtonStyle.secondary, row=4)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        embed = discord.Embed(
            title=f"📋 Очередь — {channel.name}",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Обновить", emoji="🔄", style=discord.ButtonStyle.secondary, row=4)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await self._require_leader(interaction)
        if not channel:
            return
        await refresh_lock_message(channel)
        await interaction.followup.send("🔄 Панель обновлена.", ephemeral=True)


# ---------- Публичное сообщение "открыть панель" ----------
class OpenPanelButton(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="Открыть панель", emoji="👑", style=discord.ButtonStyle.primary)
    async def open_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if voice_leaders.get(self.channel_id) != interaction.user.id:
            await interaction.followup.send("🚫 Только владелец войса может открыть панель.", ephemeral=True)
            return

        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Канал не найден.", ephemeral=True)
            return

        member = channel.guild.get_member(interaction.user.id)
        if not member or not member.voice or member.voice.channel != channel:
            await interaction.followup.send("🚫 Ты должен быть в своём голосовом канале.", ephemeral=True)
            return

        embed = build_panel_embed(channel, member)

        if PANEL_IMAGE_URL:
            embed.set_image(url=PANEL_IMAGE_URL)
        else:
            log.warning("PANEL_IMAGE_URL не задан — картинка панели не будет показана")

        view = LeaderPanel(channel.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


def build_open_embed(channel: discord.VoiceChannel, leader: discord.Member) -> discord.Embed:
    locked = is_locked(channel)
    banned_count = len(banned_users.get(channel.id, set()))
    cur_limit = get_limit(channel)
    limit_str = f"👥 Лимит: **{cur_limit}**" if cur_limit else "👥 Лимит: **нет**"

    embed = discord.Embed(
        title=f"👑 Владелец войса: {leader.display_name}",
        description=(
            f"🔊 Канал: **{channel.name}**\n"
            f"{limit_str}\n"
            f"Вход: {'🔒 **закрыт для всех**' if locked else '🔓 **открыт**'}\n"
            f"🚫 Забанено: **{banned_count}**\n\n"
            "Нажми **👑 Открыть панель**, чтобы управлять каналом.\n"
            "*Кнопка доступна только владельцу.*"
        ),
        color=discord.Color.red() if locked else discord.Color.gold(),
    )
    embed.set_footer(text="Мазафака Войс")
    return embed


async def send_open_message(channel: discord.VoiceChannel, leader_id: int):
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
        log.warning(f"Не могу отправить сообщение-панель в {channel.name}: {e}")


async def refresh_lock_message(channel: discord.VoiceChannel):
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


# ---------- Ephemeral-панель ----------
def build_panel_embed(channel: discord.VoiceChannel, leader: discord.Member) -> discord.Embed:
    q = voice_queues.get(channel.id, deque())
    members_count = len([m for m in channel.members if not m.bot])
    locked = is_locked(channel)
    banned_count = len(banned_users.get(channel.id, set()))
    cur_limit = get_limit(channel)
    limit_str = (
        f"👥 **{members_count} / {cur_limit}**" if cur_limit
        else f"👥 **{members_count}** (без лимита)"
    )

    embed = discord.Embed(
        title=f"👑 {leader.display_name} — панель управления",
        description=(
            f"🔊 Канал: **{channel.name}**\n"
            f"{limit_str}\n"
            f"📋 В очереди: **{len(q)}**\n"
            f"🚫 Забанено: **{banned_count}**\n"
            f"Вход: {'🔒 **закрыт для всех**' if locked else '🔓 **открыт**'}"
        ),
        color=discord.Color.red() if locked else discord.Color.gold(),
    )
    embed.add_field(
        name="Управление",
        value=(
            "🦶 **Кикнуть** — выкинуть участника\n"
            "🔇 **Микро** — вкл/выкл микрофон\n"
            "🎧 **Уши** — вкл/выкл наушники\n"
            "🔒 **Закрыть вход** — запретить заход **всем**\n"
            "🚫 **Забанить вход** — запретить **конкретным**\n"
            "✅ **Разбанить вход** — снять запрет\n"
            "👥 **Лимит** — задать максимум (0 — снять)\n"
            "♻️ **Снять лимит** — убрать ограничение\n"
            "👑 **Передать** — передать лидерство\n"
            "📋 **Очередь** — список очереди"
        ),
        inline=False,
    )
    embed.set_footer(text="Мазафака Войс • панель видна только тебе")
    return embed


# ============================================================
# КОМАНДА !settings — ПЕРСОНАЛЬНЫЕ НАСТРОЙКИ
# ============================================================
class SettingsView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self._rebuild()

    def _rebuild(self):
        self.clear_items()

        dm_on = dm_enabled(self.user_id)
        dm_btn = discord.ui.Button(
            label=f"ЛС-уведомления: {'ВКЛ ✅' if dm_on else 'ВЫКЛ ❌'}",
            style=discord.ButtonStyle.success if dm_on else discord.ButtonStyle.danger,
            custom_id="mzf_toggle_dm",
            row=0,
        )
        dm_btn.callback = self._make_dm_callback()
        self.add_item(dm_btn)

        mode = get_panel_ping_mode(self.user_id)
        ping_btn = discord.ui.Button(
            label=f"Пинг панели: {PANEL_PING_LABELS[mode]}",
            style=discord.ButtonStyle.primary,
            custom_id="mzf_toggle_ping",
            row=1,
        )
        ping_btn.callback = self._make_ping_callback()
        self.add_item(ping_btn)

    def _make_dm_callback(self):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await safe_respond(
                    interaction,
                    "🚫 Это не твоя панель настроек. Введи `!settings` для своей.",
                )
                return
            current = dm_enabled(self.user_id)
            dm_notifications[self.user_id] = not current
            save_settings()
            self._rebuild()
            embed = build_settings_embed(self.user_id, interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)
        return callback

    def _make_ping_callback(self):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await safe_respond(
                    interaction,
                    "🚫 Это не твоя панель настроек. Введи `!settings` для своей.",
                )
                return
            current = get_panel_ping_mode(self.user_id)
            idx = PANEL_PING_CYCLE.index(current)
            new_mode = PANEL_PING_CYCLE[(idx + 1) % len(PANEL_PING_CYCLE)]
            set_panel_ping_mode(self.user_id, new_mode)
            save_settings()
            self._rebuild()
            embed = build_settings_embed(self.user_id, interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)

            cid = member_channel.get(self.user_id)
            if cid:
                ch = bot.get_channel(cid)
                if ch and voice_leaders.get(cid) == self.user_id:
                    await refresh_lock_message(ch)
        return callback


def build_settings_embed(user_id: int, user: discord.User = None) -> discord.Embed:
    dm_on = dm_enabled(user_id)
    mode = get_panel_ping_mode(user_id)

    embed = discord.Embed(
        title="⚙️ Мои настройки — Мазафака Войс",
        description=(
            f"Пользователь: **{user.display_name if user else '—'}**\n\n"
            "**ЛС-уведомления** — бот пишет **тебе в личные сообщения**, "
            "когда владелец войса применяет к тебе действия "
            "(кик, мьют, бан, лимит и т.д.).\n\n"
            "**Пинг панели** — как бот упоминает тебя в сообщении-панели "
            "под войсом:\n"
            "• `Без пинга` — просто «Панель управления»\n"
            "• `Текст + пинг` — «Панель управления @ты»\n"
            "• `Только пинг` — просто «@ты»\n\n"
            "*Настройки персональные — действуют только на тебя.*"
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
    embed.set_footer(text="Нажми кнопку ниже, чтобы переключить")
    return embed


@bot.command(name="settings", aliases=["настройки"])
@commands.guild_only()
async def settings_cmd(ctx: commands.Context):
    embed = build_settings_embed(ctx.author.id, ctx.author)
    view = SettingsView(ctx.author.id)
    await safe_reply(ctx, embed=embed, view=view)


@settings_cmd.error
async def settings_cmd_error(ctx: commands.Context, error):
    if isinstance(error, commands.NoPrivateMessage):
        await safe_reply(ctx, "🚫 Команда только для серверов.")
    else:
        log.warning(f"Ошибка в !settings: {error}")


# ============================================================
# АВТО-КИК ПРИ ПРЕВЫШЕНИИ ЛИМИТА
# ============================================================
async def enforce_limit_on_join(channel: discord.VoiceChannel, member: discord.Member):
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
        log.warning(f"Не могу выкинуть {member} по лимиту")
        return False

    remove_member_from_queue(channel.id, member.id)

    leader = channel.guild.get_member(leader_id) if leader_id else None
    leader_name = leader.display_name if leader else "владелец"

    await notify_dm(
        member,
        content=(
            f"👥 В войсе **{channel.name}** установлен лимит **{limit}** чел.\n"
            f"Владелец **{leader_name}** — мест нет, вы были выгнаны."
        ),
    )
    return True


# ============================================================
# СБРОС СОСТОЯНИЯ КАНАЛА
# ============================================================
async def reset_channel_state(channel: discord.VoiceChannel) -> None:
    cid = channel.id

    orig = original_limits.get(cid, 0)
    if custom_limits.get(cid) != orig or channel.user_limit != orig:
        try:
            await channel.edit(user_limit=orig, reason="Мазафака: все вышли — сброс лимита")
        except discord.Forbidden:
            log.warning(f"Не могу сбросить лимит в {channel.name} (нет прав)")
        except discord.HTTPException as e:
            log.warning(f"Не могу сбросить лимит в {channel.name}: {e}")
    custom_limits.pop(cid, None)

    locked_channels.discard(cid)
    banned_users.pop(cid, None)
    clean_channel(cid)
    await refresh_lock_message(channel)


# ============================================================
# АДМИН-КОМАНДЫ ВЛАДЕЛЬЦА БОТА
# ============================================================

@bot.command(name="voices", aliases=["войсы"])
@owner_only()
async def voices_cmd(ctx: commands.Context):
    if not voice_leaders:
        await safe_reply(ctx, "Нет активных войсов с владельцами.")
        return

    lines = []
    for cid, leader_id in voice_leaders.items():
        ch = ctx.guild.get_channel(cid)
        leader = ctx.guild.get_member(leader_id)
        if not ch:
            continue
        ch_name = ch.name
        leader_name = leader.display_name if leader else f"id={leader_id}"
        humans = len([m for m in ch.members if not m.bot])
        lock = "🔒" if is_locked(ch) else "🔓"
        lim = get_limit(ch)
        lim_str = f" / лимит {lim}" if lim else ""
        lines.append(f"{lock} 🔊 **{ch_name}** — 👑 {leader_name} ({humans} чел{lim_str})")

    embed = discord.Embed(
        title="🎧 Активные войсы",
        description="\n".join(lines) or "Пусто",
        color=discord.Color.blurple(),
    )
    await safe_reply(ctx, embed=embed)


@bot.command(name="setleader", aliases=["влад"])
@owner_only()
@commands.guild_only()
async def setleader_cmd(ctx: commands.Context, member: discord.Member, channel: discord.VoiceChannel = None):
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

    if member.voice and member.voice.channel == channel:
        await safe_reply(
            ctx,
            f"👑 Владельцем канала **{channel.name}** назначен **{member.display_name}**.",
        )
    else:
        if member.voice and member.voice.channel:
            try:
                await member.move_to(channel)
                await safe_reply(
                    ctx,
                    f"👑 **{member.display_name}** перемещён в **{channel.name}** и назначен владельцем.",
                )
            except discord.Forbidden:
                await safe_reply(
                    ctx,
                    f"👑 Владелец назначен: **{member.display_name}** → **{channel.name}** "
                    f"(не смог переместить — нет прав Move Members).",
                )
            except discord.HTTPException as e:
                await safe_reply(
                    ctx,
                    f"👑 Владелец назначен: **{member.display_name}** → **{channel.name}** "
                    f"(переместить не удалось: {e}).",
                )
        else:
            await safe_reply(
                ctx,
                f"👑 Владельцем канала **{channel.name}** назначен **{member.display_name}**.\n"
                f"*Он не в войсе — как только зайдёт, станет владельцем.*",
            )

    await refresh_lock_message(channel)


@bot.command(name="say", aliases=["сказать"])
@owner_only()
async def say_cmd(ctx: commands.Context, channel: discord.TextChannel, *, text: str):
    try:
        await channel.send(text)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await safe_reply(ctx, f"✅ Отправлено в {channel.mention}.", delete_after=5)
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 Нет прав писать в этот канал.")


@bot.command(name="embed")
@owner_only()
async def embed_cmd(ctx: commands.Context, channel: discord.TextChannel, title: str, *, description: str):
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blurple(),
    )
    try:
        await channel.send(embed=embed)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await safe_reply(ctx, f"✅ Embed отправлен в {channel.mention}.", delete_after=5)
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 Нет прав писать в этот канал.")


@bot.command(name="dm", aliases=["лс"])
@owner_only()
async def dm_cmd(ctx: commands.Context, member: discord.Member, *, text: str):
    try:
        await member.send(text)
        await safe_reply(ctx, f"✅ ЛС отправлено **{member.display_name}**.", delete_after=5)
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 У пользователя закрыты ЛС.")


@bot.command(name="del")
@owner_only()
async def del_cmd(ctx: commands.Context, message_id: int, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    try:
        msg = await channel.fetch_message(message_id)
        await msg.delete()
        await safe_reply(ctx, "🗑 Удалено.", delete_after=5)
    except discord.NotFound:
        await safe_reply(ctx, "🚫 Сообщение не найдено.")
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 Нет прав удалять.")


@bot.command(name="vkick", aliases=["вкик"])
@owner_only()
@commands.guild_only()
async def vkick_cmd(ctx: commands.Context, member: discord.Member):
    if not member.voice or not member.voice.channel:
        await safe_reply(ctx, "🚫 Этот пользователь не в войсе.")
        return
    try:
        ch = member.voice.channel
        await member.move_to(None)
        await safe_reply(ctx, f"🦶 {member.display_name} выкинут из **{ch.name}**.")
    except discord.Forbidden:
        await safe_reply(ctx, "🚫 Нет прав Move Members.")


@bot.command(name="vreset", aliases=["сброс"])
@owner_only()
@commands.guild_only()
async def vreset_cmd(ctx: commands.Context, channel: discord.VoiceChannel = None):
    if channel is None:
        if ctx.author.voice and ctx.author.voice.channel:
            channel = ctx.author.voice.channel
        else:
            await safe_reply(ctx, "🚫 Укажи канал или зайди в войс.")
            return

    await reset_channel_state(channel)
    await safe_reply(ctx, f"♻️ Состояние канала **{channel.name}** сброшено.")


@bot.command(name="vbans", aliases=["баны"])
@owner_only()
@commands.guild_only()
async def vbans_cmd(ctx: commands.Context, channel: discord.VoiceChannel):
    bans = banned_users.get(channel.id, set())
    if not bans:
        await safe_reply(ctx, f"В **{channel.name}** нет банов.")
        return

    lines = []
    for uid in bans:
        m = ctx.guild.get_member(uid)
        lines.append(f"• {m.mention if m else f'id={uid}'}")

    embed = discord.Embed(
        title=f"🚫 Баны — {channel.name}",
        description="\n".join(lines),
        color=discord.Color.dark_red(),
    )
    await safe_reply(ctx, embed=embed)


@bot.command(name="vclear", aliases=["клеарбаны"])
@owner_only()
@commands.guild_only()
async def vclear_cmd(ctx: commands.Context, channel: discord.VoiceChannel):
    banned_users.pop(channel.id, None)
    await safe_reply(ctx, f"✅ Все баны канала **{channel.name}** сняты.")


@bot.command(name="adminhelp", aliases=["апомощь"])
@owner_only()
async def adminhelp_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="🛠 Админ-команды Мазафака Войс",
        color=discord.Color.dark_green(),
    )
    embed.add_field(
        name="👑 Владельцы войсов",
        value=(
            "`!voices` — список всех активных войсов\n"
            "`!setleader @user [#ch]` — сменить владельца\n"
            "`!vkick @user` — выкинуть из войса\n"
            "`!vreset [#ch]` — сбросить войс\n"
            "`!vbans #ch` — список банов\n"
            "`!vclear #ch` — снять все баны"
        ),
        inline=False,
    )
    embed.add_field(
        name="💬 Сообщения от бота",
        value=(
            "`!say #ch текст` — написать от бота\n"
            "`!embed #ch \"Заголовок\" текст` — embed\n"
            "`!dm @user текст` — написать в ЛС\n"
            "`!del ID [#ch]` — удалить сообщение"
        ),
        inline=False,
    )
    embed.set_footer(text="Только для владельца бота")
    await safe_reply(ctx, embed=embed)


@bot.event
async def on_command_error(ctx: commands.Context, error):
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


# ---------- События ----------
@bot.event
async def on_ready():
    log.info(f"Бот запущен: {bot.user}")
    if not PANEL_IMAGE_URL:
        log.warning("PANEL_IMAGE_URL не задан — картинка панели не будет показана")
    for guild in bot.guilds:
        for ch in guild.voice_channels:
            if not everyone_can_connect(ch):
                initially_locked.add(ch.id)
            original_limits[ch.id] = ch.user_limit

    if not rotate_status.is_running():
        rotate_status.start()

    await notify_all_voice_channels("🟢 **Бот запущен и готов к работе!**")


@bot.event
async def on_disconnect():
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True
    log.warning("Бот отключается — рассылаю уведомления в войсы")
    try:
        save_settings()
    except Exception as e:
        log.warning(f"Не удалось сохранить настройки: {e}")
    try:
        await notify_all_voice_channels("🔴 **Бот выключается...**")
    except Exception as e:
        log.warning(f"Не удалось разослать уведомление об отключении: {e}")


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


async def handle_join(channel: discord.VoiceChannel, member: discord.Member):
    cid = channel.id

    if is_bot_owner(member):
        try:
            await channel.send(content="👑 **В войс зашел создатель бота**")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"Не могу написать уведомление создателю: {e}")

    leader_id = voice_leaders.get(cid)
    leader = channel.guild.get_member(leader_id) if leader_id else None
    leader_name = leader.display_name if leader else "владелец"

    if is_banned(cid, member.id) and member.id != leader_id:
        try:
            await member.move_to(None)
        except discord.Forbidden:
            log.warning(f"Не могу выкинуть {member} из канала")
            return
        await notify_dm(
            member,
            content=(
                f"🚫 **Владелец войса {leader_name} запретил вам вход** "
                f"в канал **{channel.name}** на сервере **{channel.guild.name}**."
            ),
        )
        return

    if is_locked(channel) and member.id != leader_id and not is_bot_owner(member):
        try:
            await member.move_to(None)
        except discord.Forbidden:
            log.warning(f"Не могу выкинуть {member} из закрытого канала")
            return
        await notify_dm(
            member,
            content=(
                f"🔒 **Вам закрыт доступ к войсу**\n"
                f"Сервер: **{channel.guild.name}**\n"
                f"Канал: **{channel.name}**\n"
                f"Владелец войса **{leader_name}** закрыл вход для всех."
            ),
        )
        return

    if not is_bot_owner(member):
        kicked = await enforce_limit_on_join(channel, member)
        if kicked:
            await refresh_lock_message(channel)
            return

    q = voice_queues[cid]
    if not q:
        q.append(member.id)
        voice_leaders[cid] = member.id
        member_channel[member.id] = cid
        log.info(f"[{channel.guild.name} / 🔊 {channel.name}] Лидер: {member.display_name}")
        await refresh_lock_message(channel)
        return

    if member.id in q:
        member_channel[member.id] = cid
        return

    q.append(member.id)
    member_channel[member.id] = cid
    if cid not in voice_leaders:
        voice_leaders[cid] = q[0]
    await refresh_lock_message(channel)


async def handle_leave(channel: discord.VoiceChannel, member: discord.Member, before_members: list = None):
    cid = channel.id
    member_channel.pop(member.id, None)

    was_leader = (voice_leaders.get(cid) == member.id)

    q = voice_queues.get(cid)
    if q is not None:
        remove_member_from_queue(cid, member.id)

    if before_members is not None:
        remaining = [
            m for m in before_members
            if m.id != member.id and not m.bot
        ]
    else:
        remaining = [
            m for m in channel.members
            if m.id != member.id and not m.bot
        ]

    if not remaining:
        await reset_channel_state(channel)
        log.info(f"[{channel.guild.name} / 🔊 {channel.name}] пусто — сброс")
        return

    if was_leader:
        new_leader = random.choice(remaining)

        if q is None:
            q = voice_queues[cid]
        remaining_ids = {m.id for m in remaining}
        keep = [mid for mid in q if mid in remaining_ids]
        q.clear()
        q.extend(keep)
        if new_leader.id in q:
            q.remove(new_leader.id)
        q.appendleft(new_leader.id)
        voice_leaders[cid] = new_leader.id

        log.info(
            f"[{channel.guild.name} / 🔊 {channel.name}] "
            f"Владелец вышел, новый (случайный) лидер: {new_leader.display_name}"
        )
        await notify_dm(
            new_leader,
            content=(
                f"👑 Вы стали **владельцем войса** **{channel.name}** "
                f"(предыдущий владелец вышел)."
            ),
        )

    await refresh_lock_message(channel)


# ============================================================
# КОРРЕКТНОЕ ЗАВЕРШЕНИЕ РАБОТЫ
# ============================================================
async def _shutdown_notify(reason: str = "выключение"):
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True

    log.warning(f"Завершение работы ({reason}) — рассылаю уведомления")

    try:
        save_settings()
    except Exception as e:
        log.warning(f"save_settings: {e}")

    try:
        await notify_all_voice_channels("🔴 **Бот выключается...**")
        await asyncio.sleep(1.5)
    except Exception as e:
        log.warning(f"shutdown notify: {e}")

    try:
        if not bot.is_closed():
            await bot.close()
    except Exception as e:
        log.warning(f"bot.close: {e}")


def _handle_signal(signum, frame):
    log.warning(f"Получен сигнал {signum} — запускаю завершение")
    try:
        loop = bot.loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(_shutdown_notify(f"signal {signum}"), loop)
        else:
            raise KeyboardInterrupt
    except Exception as e:
        log.warning(f"Ошибка в обработчике сигнала: {e}")


for _sig in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(_sig, _handle_signal)
    except (ValueError, OSError, AttributeError):
        pass


# ---------- Запуск ----------
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ Не указан DISCORD_TOKEN в переменных окружения")
    if not OWNER_IDS:
        log.warning("⚠️ OWNER_ID не указан — админ-команды недоступны никому")
    if not PANEL_IMAGE_URL:
        log.warning("⚠️ PANEL_IMAGE_URL не указан — картинка панели не будет показана")

    load_settings()

    keep_alive()  # запускаем веб-сервер для Render

    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        log.warning("KeyboardInterrupt — завершение")