import discord
from discord.ext import commands
import asyncio
import os

# ===== ПУТЬ К FFMPEG =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.path.join(BASE_DIR, 'ffmpeg.exe')
# =================================================

# ===== КОНФИГУРАЦИЯ =====
# Укажи токен в переменной окружения DISCORD_TOKEN.
# Не вставляй токен прямо в файл.
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 1397635666480861397

HUB_IMAGE = 'hub.png'
PLAY_IMAGE = 'play.png'
UPDATELOGS_IMAGE = 'updatelogs.png'
GUIDE_URL = 'https://discord.com/channels/1397635666480861397/1428791257404018778/1548422657354235975'
TRUSIKI_MUSIC_URL = 'https://slava20222014-create.github.io/TrusikiMusic/'
DEV_MENTION = '<@1104097922909491351>'

TRACKS = {
    'лашара': 'https://videotourl.com/audio/1781775269496-0257b485-9f54-4b2f-8af8-b068911745e4.mp3',
    'вертитоп-лашара': 'https://www.image2url.com/r2/default/audio/1789244815745-7df6bc97-605b-4467-bc02-3f57d8cbad27.mp3',
    'хватит-меня-булить': 'https://videotourl.com/audio/1781792491279-c47792dc-3414-41d8-9779-73dcafcbe31f.mp3',
    'вертитоп-лошадь': 'https://videotourl.com/audio/1781794423800-8b1ffcb7-e533-46e9-a27c-3e9e3fde397a.mp3',
    '1-час-и-1-минуту': 'https://www.image2url.com/r2/default/audio/1786818163101-4fa2be73-2062-4769-a28e-5fa36a435c49.mp3',
    'в-канаве': 'https://www.image2url.com/r2/default/audio/1786818218357-346e6cc2-5961-4dbf-823d-1f7fb1ad226e.mp3',
    'пузико': 'https://www.image2url.com/r2/default/audio/1787222722631-6d97cf0c-6c01-4495-bed6-f1e088fe0870.mp3',
    'династия-гемера': 'https://www.image2url.com/r2/default/audio/1787223125225-0fa5b611-d85b-40c3-a23f-75e25c0f2939.mp3',
    'мазафако': 'https://www.image2url.com/r2/default/audio/1789241629051-6548266c-7672-4e9e-8bcd-1daabb9377e4.mp3',
    'олд-ттд': 'https://www.image2url.com/r2/default/audio/1789293369913-7265a85c-1572-42c2-85cf-df672a462311.mp3',
    'биг-дилда-опять-за-своё': 'https://www.image2url.com/r2/default/audio/1789293508254-462c77a7-1813-483f-b34b-de6f0f3be202.mp3',
    'если-верти-всё-мало': 'https://www.image2url.com/r2/default/audio/1789293540774-54036623-4588-45c2-a8b8-488dac3834db.mp3',
    'верти-мифа-и-ночной-шалун': 'https://www.image2url.com/r2/default/audio/1789293658484-bbb2190e-c381-4a92-871e-42d21b605d7b.mp3',
    'фублин-жирный-говноед': 'https://www.image2url.com/r2/default/audio/1789293707974-f49863b8-7526-448d-ae5b-7bb885acec21.mp3',
    'фубля-лох': 'https://videotourl.com/audio/1789293788569-416bb607-58e9-4145-8f58-bcdb5c838492.mp3',
    'способка-не-работает': 'https://videotourl.com/audio/1791309285608-f05300b9-dc3d-444f-8551-56e7b1dc1386.mp3',
    'blood-in-your-eyes': 'https://videotourl.com/audio/1795359135541-dabcec9b-45b0-46c2-a6f5-4b282d2ad0e6.mp3',
    'love-is-a-long-road': 'https://videotourl.com/audio/1795360025185-f3995f56-6346-43f9-a22f-0344daa76219.mp3',
    'hot-together': 'https://videotourl.com/audio/1795361374732-29d4ab01-0ef2-4df9-a43e-7d485b71f0ea.mp3',
    'rhyno': 'https://videotourl.com/audio/1795361441506-15a1f8ed-7e71-4d2d-9de7-d5f9f87c55ed.mp3',
}

TRACK_LABELS = {
    'лашара': 'Лашара',
    'вертитоп-лашара': 'Вертитоп — лашара',
    'хватит-меня-булить': 'Хватит меня булить',
    'вертитоп-лошадь': 'Вертитоп лошадь',
    '1-час-и-1-минуту': '1 час и 1 минуту',
    'в-канаве': 'В канаве',
    'мазафако': 'Мазафако Funk',
    'олд-ттд': 'Олд ТТД',
    'биг-дилда-опять-за-своё': 'Биг дилда опять за своё',
    'если-верти-всё-мало': 'Если верти всё мало',
    'верти-мифа-и-ночной-шалун': 'Верти, Мифа и ночной шалун',
    'фублин-жирный-говноед': 'Фублин жирный говноед',
    'фубля-лох': 'Фубля лох',
    'способка-не-работает': 'Способка не работает',
    'blood-in-your-eyes': 'Blood In Your Eyes',
    'love-is-a-long-road': 'Love Is A Long Road',
    'hot-together': 'Hot Together',
    'rhyno': 'RHYNO',
}

DEFAULT_AUDIO_URL = TRACKS['лашара']

# === ПЛЕЙЛИСТ GTA 6 ===
EVENT_CHAIN = [
    ('blood-in-your-eyes', 'Blood In Your Eyes'),
    ('love-is-a-long-road', 'Love Is A Long Road'),
    ('hot-together', 'Hot Together'),
    ('rhyno', 'RHYNO'),
]

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)
bot.currently_playing = False
bot.loop_running = False
bot.current_track = None
bot.current_url = None
bot.voice_client = None
bot.volume = 50
bot.current_generation = 0
bot.is_connecting = False
bot.event_chain_active = False
bot.event_chain_index = 0

# ============================================================
# ================   ХЕЛПЕРЫ DEFER / SAFE SEND   =============
# ============================================================

async def safe_defer(interaction: discord.Interaction, ephemeral: bool = True) -> bool:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
        return True
    except discord.errors.NotFound:
        return False
    except discord.errors.InteractionResponded:
        return True
    except Exception as e:
        print(f'❌ defer error: {e}')
        return False

async def safe_followup(interaction: discord.Interaction, content=None, embed=None, view=None, file=None, ephemeral: bool = True):
    try:
        kwargs = {'ephemeral': ephemeral}
        if content is not None: kwargs['content'] = content
        if embed is not None: kwargs['embed'] = embed
        if view is not None: kwargs['view'] = view
        if file is not None: kwargs['file'] = file
        await interaction.followup.send(**kwargs)
    except Exception as e:
        print(f'❌ followup error: {e}')

def get_author_voice_channel(ctx_or_interaction):
    if isinstance(ctx_or_interaction, discord.Interaction):
        member = ctx_or_interaction.user
    else:
        member = ctx_or_interaction.author
    if member is None:
        return None
    if hasattr(member, 'voice') and member.voice and member.voice.channel:
        return member.voice.channel
    return None

def get_bot_voice_channel(guild):
    """Возвращает голосовой канал бота только на указанном сервере."""
    if guild is None:
        return None

    for vc in bot.voice_clients:
        if vc.guild and vc.guild.id == guild.id and vc.is_connected():
            return vc.channel

    return None


def same_voice_channel(channel_a, channel_b):
    """Сравнивает каналы по Discord ID, а не по объектам Python."""
    return (
        channel_a is not None
        and channel_b is not None
        and channel_a.id == channel_b.id
    )

async def ensure_bot_free_or_same(ctx, voice_channel):
    bot_channel = get_bot_voice_channel(voice_channel.guild)
    if bot_channel and not same_voice_channel(bot_channel, voice_channel):
        await ctx.send(
            f'❌ __**Бот уже занят в другом голосовом канале:**__ **{bot_channel.name}**\n'
            f'__**Сначала освободите его командой**__ `!leave`'
        )
        return False
    return True

# ============================================================
# ================       PLAY-VIEW (кнопки)      =============
# ============================================================

class PlayTrackButton(discord.ui.Button):
    def __init__(self, track_key: str, label: str, row: int):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            emoji='▶️',
            custom_id=f'play_track_{track_key}',
            row=row
        )
        self.track_key = track_key

    async def callback(self, interaction: discord.Interaction):
        ok = await safe_defer(interaction, ephemeral=True)
        if not ok:
            return

        url = TRACKS.get(self.track_key)
        label = TRACK_LABELS.get(self.track_key, self.track_key)
        if not url:
            await safe_followup(interaction, content='❌ __**Трек не найден!**__')
            return

        voice_channel = get_author_voice_channel(interaction)
        if not voice_channel:
            await safe_followup(interaction, content='❌ __**Ты не в голосовом канале! Зайди в войс и попробуй снова.**__')
            return

        bot_channel = get_bot_voice_channel(interaction.guild)
        if bot_channel and not same_voice_channel(bot_channel, voice_channel):
            await safe_followup(interaction, content=f'❌ __**Бот уже занят в другом канале:**__ **{bot_channel.name}**')
            return

        if self.track_key in [k for k, _ in EVENT_CHAIN]:
            bot.event_chain_active = True
            bot.event_chain_index = [k for k, _ in EVENT_CHAIN].index(self.track_key)
        else:
            bot.event_chain_active = False

        await safe_followup(interaction, content=f'🎵 __**Включаю:**__ **{label}** в **{voice_channel.name}**')
        asyncio.create_task(connect_and_play_url(voice_channel, url, label, ctx=None))

class PlayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Исключаем из меню "Включить музыку" треки цепочки GTA 6
        excluded = {'blood-in-your-eyes', 'love-is-a-long-road'}
        filtered = {k: v for k, v in TRACK_LABELS.items() if k not in excluded}
        print(f'🔧 PlayView создан, треков: {len(filtered)}')
        row = 0
        col = 0
        for key, label in filtered.items():
            if col >= 5:
                row += 1
                col = 0
            if row >= 5:
                print(f'⚠️ Достигнут лимит рядов, трек пропущен: {key}')
                break
            self.add_item(PlayTrackButton(key, label, row))
            col += 1
        print(f'🔧 Кнопок добавлено: {len(self.children)}')

def build_play_embed(guild: discord.Guild | None) -> discord.Embed:
    embed = discord.Embed(
        title='<:__:1408871102200938709> __**ВКЛЮЧИТЬ МУЗЫКУ**__ <:__:1408871102200938709>',
        description='__**Нажми на кнопку с названием песни, чтобы включить её!**__ 🎶\n__**(бот зайдёт в твой войс)**__',
        color=discord.Color.green()
    )
    embed.set_footer(text='⚡ Кнопки работают всегда ⚡')
    if guild and guild.icon:
        embed.set_author(name='🎧 Музыкальный Трусикинский бот', icon_url=guild.icon.url)
    return embed

# ============================================================
# ================       UPDATE LOGS VIEW        =============
# ============================================================

class UpdateLogButton(discord.ui.Button):
    def __init__(self, version: str, active: bool = False, row: int = 0):
        super().__init__(
            label=version,
            style=discord.ButtonStyle.primary if active else discord.ButtonStyle.secondary,
            custom_id=f'update_log_{version}',
            row=row
        )
        self.version = version

    async def callback(self, interaction: discord.Interaction):
        try:
            view = self.view
            if isinstance(view, UpdateLogsView):
                view.set_active(self.version)
            embed = build_update_log_embed(self.version, interaction.guild)
            try:
                if interaction.message and interaction.message.attachments:
                    embed.set_image(url='attachment://updatelogs.png')
            except Exception:
                pass
            await interaction.response.edit_message(embed=embed, view=view)
        except discord.errors.NotFound:
            return
        except discord.errors.InteractionResponded:
            await safe_followup(interaction, embed=build_update_log_embed(self.version, interaction.guild), view=UpdateLogsView(current=self.version))
        except Exception as e:
            print(f'❌ Ошибка в UpdateLogButton: {e}')

class UpdateLogsView(discord.ui.View):
    def __init__(self, current: str = 'v1.1'):
        super().__init__(timeout=None)
        self.current = current
        self.buttons = {}
        versions = ['v1.1', 'v1.2', 'v1.3', 'v1.4', 'v1.5', 'v1.6']
        for i, v in enumerate(versions):
            row = 0 if i < 5 else 1
            btn = UpdateLogButton(v, active=(v == current), row=row)
            self.buttons[v] = btn
            self.add_item(btn)

    def set_active(self, version: str):
        self.current = version
        for v, btn in self.buttons.items():
            btn.style = discord.ButtonStyle.primary if v == version else discord.ButtonStyle.secondary

def build_update_log_embed(version: str, guild: discord.Guild | None) -> discord.Embed:
    if version == 'v1.1':
        title = '📜 __**UPDATE LOGS — v1.1**__'
        desc = f'>>> __**Релиз бота!**__ 🎉\n\n__**🎵 Песни:**__\n• Лашара\n• Вертитоп лошадь\n• Хватит меня булить\n\n__**📖 Гайд:**__ [нажми сюда]({GUIDE_URL})'
        color = discord.Color.purple()
    elif version == 'v1.2':
        title = '📜 __**UPDATE LOGS — v1.2**__'
        desc = '>>> __**🛠 Фикс:**__ музыка играла раз через раз — теперь играет всегда\n\n__**🎵 Новые песни:**__\n• В канаве\n• 1 час и 1 минуту'
        color = discord.Color.blue()
    elif version == 'v1.3':
        title = '📜 __**UPDATE LOGS — v1.3**__'
        desc = '>>> __**🎵 Новые песни:**__\n• Династия-Гемера\n• Пузико'
        color = discord.Color.green()
    elif version == 'v1.4':
        title = '📜 __**UPDATE LOGS — v1.4**__'
        desc = '>>> __**🛠 Фикс системы проигрывания музыки:**__\nопять перестала играть — теперь работает стабильно'
        color = discord.Color.orange()
    elif version == 'v1.5':
        title = '📜 __**UPDATE LOGS — v1.5**__'
        desc = '>>> __**🆕 Новая команда:**__ `!hub`\n\n__**🔄 Обновления:**__\n• Новый **List Музыки**\n• Кнопка **О мне**\n• Кнопка **Trusiki Music**\n• Кнопки **Play** на каждую песню\n• **Рекодинг системы проигрывания музыки**\n\n__**🎵 Новая песня:**__\n• Мазафако Funk'
        color = discord.Color.gold()
    elif version == 'v1.6':
        title = '📜 __**UPDATE LOGS — v1.6**__'
        desc = ('>>> __**🆕 Новая команда:**__ `!event-gta6 music`\n\n'
                '__**🎵 Плейлист GTA 6:**__\n'
                '• Blood In Your Eyes\n'
                '• Love Is A Long Road\n'
                '• Hot Together\n'
                '• RHYNO\n\n'
                '__**🔁 Плейлист зациклен.**__\n'
                '__**🛠 Подкоманды:**__\n'
                '• `!event-gta6 music next` — следующая\n'
                '• `!event-gta6 music how` — что играет\n'
                '• `!event-gta6 music stop` — остановить')
        color = discord.Color.red()
    else:
        title = '📜 __**UPDATE LOGS**__'
        desc = '>>> __**Патч не найден**__ ❌'
        color = discord.Color.red()

    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_footer(text=f'⚡ Текущий патч: {version} ⚡')
    if guild and guild.icon:
        embed.set_author(name='🎧 Музыкальный Трусикинский бот', icon_url=guild.icon.url)
    return embed

# ============================================================
# ================            HUB UI            ==============
# ============================================================

class HubMusicListButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Лист Музыки', style=discord.ButtonStyle.primary, emoji='🎵', custom_id='hub_music_list', row=0)

    async def callback(self, interaction: discord.Interaction):
        ok = await safe_defer(interaction, ephemeral=True)
        if not ok: return
        try:
            file = discord.File(PLAY_IMAGE, filename='play.png') if os.path.exists(PLAY_IMAGE) else None
            embed = build_music_list_embed(interaction.guild)
            if file:
                embed.set_image(url='attachment://play.png')
                await safe_followup(interaction, embed=embed, file=file)
            else:
                await safe_followup(interaction, embed=embed)
        except Exception as e:
            print(f'❌ Ошибка в music_list_button: {e}')
            await safe_followup(interaction, content='❌ Ошибка при открытии списка.')

class HubPlayMusicButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Включить музыку', style=discord.ButtonStyle.success, emoji='▶️', custom_id='hub_play_music', row=0)

    async def callback(self, interaction: discord.Interaction):
        ok = await safe_defer(interaction, ephemeral=True)
        if not ok: return
        try:
            file = discord.File(PLAY_IMAGE, filename='play.png') if os.path.exists(PLAY_IMAGE) else None
            embed = build_play_embed(interaction.guild)
            view = PlayView()
            if file:
                embed.set_image(url='attachment://play.png')
                await safe_followup(interaction, embed=embed, view=view, file=file)
            else:
                await safe_followup(interaction, embed=embed, view=view)
        except Exception as e:
            print(f'❌ Ошибка в play_music_button: {e}')
            await safe_followup(interaction, content='❌ Ошибка при открытии меню.')

class HubAboutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='О мне', style=discord.ButtonStyle.primary, emoji='ℹ️', custom_id='hub_about', row=1)

    async def callback(self, interaction: discord.Interaction):
        ok = await safe_defer(interaction, ephemeral=True)
        if not ok: return
        try:
            file = discord.File(HUB_IMAGE, filename='hub.png') if os.path.exists(HUB_IMAGE) else None
            embed = discord.Embed(
                title='🎧 __**Музыкальный Трусикинский бот**__',
                description=f'Привет! Я __**Музыкальный Трусикинский бот — РЕАЛ ОЧКОШНИК**__ 🎶\n\nЯ умею играть разные трусикинские песни, и я часто пащу 💀\nНо бывает иногда мне лень, и я иду либо спать, либо отдыхать от рабочей смены 😴\n\nМеня разработал участник этого сервера — {DEV_MENTION}',
                color=discord.Color.purple()
            )
            embed.set_footer(text='⚡ РЕАЛ ОЧКОШНИК ⚡')
            if file:
                embed.set_image(url='attachment://hub.png')
                await safe_followup(interaction, embed=embed, file=file)
            else:
                await safe_followup(interaction, embed=embed)
        except Exception as e:
            print(f'❌ Ошибка в about_button: {e}')
            await safe_followup(interaction, content='❌ Ошибка при открытии "О мне".')

class HubUpdateLogsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Update Logs', style=discord.ButtonStyle.secondary, emoji='📜', custom_id='hub_update_logs', row=1)

    async def callback(self, interaction: discord.Interaction):
        ok = await safe_defer(interaction, ephemeral=True)
        if not ok: return
        try:
            embed = build_update_log_embed('v1.1', interaction.guild)
            file = discord.File(UPDATELOGS_IMAGE, filename='updatelogs.png') if os.path.exists(UPDATELOGS_IMAGE) else None
            if file: embed.set_image(url='attachment://updatelogs.png')
            view = UpdateLogsView(current='v1.1')
            if file:
                await safe_followup(interaction, embed=embed, view=view, file=file)
            else:
                await safe_followup(interaction, embed=embed, view=view)
        except Exception as e:
            print(f'❌ Ошибка в update_logs_button: {e}')
            await safe_followup(interaction, content='❌ Ошибка при открытии Update Logs.')

class HubView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HubMusicListButton())
        self.add_item(HubPlayMusicButton())
        self.add_item(HubAboutButton())
        self.add_item(HubUpdateLogsButton())
        self.add_item(discord.ui.Button(label='Trusiki Music', style=discord.ButtonStyle.link, emoji='🎧', url=TRUSIKI_MUSIC_URL, row=2))
        self.add_item(discord.ui.Button(label='Гайд', style=discord.ButtonStyle.link, emoji='📖', url=GUIDE_URL, row=2))

def build_hub_embed(guild: discord.Guild | None) -> discord.Embed:
    embed = discord.Embed(
        title='<:__:1408871102200938709> __**HUB — Музыкальный Трусикинский бот**__ <:__:1408871102200938709>',
        description='Привет! Я __**Музыкальный Трусикинский бот — РЕАЛ ОЧКОШНИК**__ 🎶\n\nЯ могу включать разные песни из списка 📃\nПолный гайд на все функции — по кнопке **📖 Гайд**\nОткрыть веб-плеер Trusiki Music — по кнопке **🎧 Trusiki Music**\nВключить музыку прямо здесь — по кнопке **▶️ Включить музыку**\n\n⚠️ __**Чтобы бот зашёл — сядь в любой голосовой канал!**__',
        color=discord.Color.purple()
    )
    embed.set_footer(text='⚡ Нажми на кнопки ниже ⚡')
    if guild and guild.icon:
        embed.set_author(name='🎧 Музыкальный Трусикинский бот', icon_url=guild.icon.url)
    return embed

def build_music_list_embed(guild: discord.Guild | None) -> discord.Embed:
    embed = discord.Embed(title='<:__:1408871102200938709> __**ДОСТУПНЫЕ ТРЕКИ**__ <:__:1408871102200938709>', description='__**Выбери свой звук!**__ 🎶', color=discord.Color.purple())
    embed.add_field(name='<:emoji_65:1467848666474745896> __**Лашара**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='<:__:1414229725965975714> __**Вертитоп лошадь**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='<:SDAASD:1469017600649597143> __**Хватит меня булить**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='<:kind_mifa:1536997306103111700> __**1 час и 1 минуту**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='<:wertyuiop_loshara:1536998349658660945> __**Вертитоп — лашара**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='<:emoji_64:1467848488074346546> __**В канаве**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='<:emoji_65:1467848666474745896> __**Пузико**__ 🐾', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='👑 __**Династия-Гемера**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='🎸 __**Мазафако Funk**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='🎤 __**Олд ТТД**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='💪 __**Биг дилда опять за своё**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='🤏 __**Если верти всё мало**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='🌙 __**Верти, Мифа и ночной шалун**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='🐷 __**Фублин жирный говноед**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='🤡 __**Фубля лох**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='🛠️ __**Способка не работает**__', value='>>> __**Трусикинский хит**__', inline=False)
    embed.add_field(name='🩸 __**Blood In Your Eyes**__', value='>>> __**Плейлист GTA 6**__', inline=False)
    embed.add_field(name='🛣️ __**Love Is A Long Road**__', value='>>> __**Плейлист GTA 6**__', inline=False)
    embed.add_field(name='🔥 __**Hot Together**__', value='>>> __**Плейлист GTA 6**__', inline=False)
    embed.add_field(name='🦏 __**RHYNO**__', value='>>> __**Плейлист GTA 6**__', inline=False)
    embed.add_field(name='<:SADSAD:1469017625194663949> __**Всего треков: 20**__ <:SADSAD:1469017625194663949>', value='>>> __**Наслаждайся музыкой!**__ ⚡', inline=False)
    embed.set_footer(text='⚡ Наслаждайся музыкой! ⚡')
    if guild and guild.icon:
        embed.set_author(name='🎧 Музыкальный Трусикинский бот', icon_url=guild.icon.url)
    return embed

async def send_hub(ctx: commands.Context):
    file = discord.File(HUB_IMAGE, filename='hub.png') if os.path.exists(HUB_IMAGE) else None
    embed = build_hub_embed(ctx.guild)
    if file:
        embed.set_image(url='attachment://hub.png')
        await ctx.send(embed=embed, view=HubView(), file=file)
    else:
        await ctx.send(embed=embed, view=HubView())

# ============================================================
# ====================    ВОСПРОИЗВЕДЕНИЕ    =================
# ============================================================

async def play_audio_by_url(voice_client, url, track_name, generation):
    if voice_client is None: return

    bot.current_track = track_name
    bot.current_url = url
    bot.loop_running = True
    await asyncio.sleep(0.3)
    fail_count = 0
    max_fails = 3

    while bot.current_generation == generation:
        if voice_client is None or not voice_client.is_connected():
            print('🔌 Отключён от войса, выхожу из цикла воспроизведения')
            bot.loop_running = False
            bot.currently_playing = False
            break

        try:
            print(f'🎵 Играет: {track_name}')
            # Убран -loglevel error, чтобы видеть все сообщения FFmpeg
            audio_source = discord.FFmpegPCMAudio(
                url,
                executable=FFMPEG_PATH,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            )
            audio_source = discord.PCMVolumeTransformer(audio_source, volume=bot.volume / 100)

            def after_playing(error, _vc=voice_client, _gen=generation):
                if error:
                    print(f'❌ Ошибка воспроизведения: {error}')
                else:
                    print(f'✅ Трек закончился без ошибок: {track_name}')
                if getattr(bot, 'event_chain_active', False) and bot.current_generation == _gen:
                    try:
                        if _vc and _vc.is_connected():
                            asyncio.run_coroutine_threadsafe(_advance_event_chain(_vc), bot.loop)
                    except Exception as e:
                        print(f'❌ Ошибка запуска следующего трека плейлиста: {e}')

            voice_client.play(audio_source, after=after_playing)
            bot.currently_playing = True
            fail_count = 0

            while voice_client.is_playing() and bot.current_generation == generation:
                await asyncio.sleep(0.3)
                if not voice_client.is_connected():
                    print('🔌 Соединение потеряно во время игры')
                    bot.loop_running = False
                    bot.currently_playing = False
                    return
                if bot.current_url != url:
                    print(f'🔄 Смена трека на: {bot.current_track}')
                    voice_client.stop()
                    return
            await asyncio.sleep(0.3)

        except discord.errors.ClientException as e:
            fail_count += 1
            print(f'❌ Клиентская ошибка ({fail_count}/{max_fails}): {e}')
            if fail_count >= max_fails:
                print('🛑 Слишком много ошибок, останавливаюсь')
                bot.loop_running = False
                bot.currently_playing = False
                break
            await asyncio.sleep(2)
        except Exception as e:
            fail_count += 1
            print(f'❌ Ошибка ({fail_count}/{max_fails}): {e}')
            if fail_count >= max_fails:
                print('🛑 Слишком много ошибок, останавливаюсь')
                bot.loop_running = False
                bot.currently_playing = False
                break
            await asyncio.sleep(3)

    bot.loop_running = False

async def _advance_event_chain(voice_client, forced_index: int | None = None):
    if not voice_client or not voice_client.is_connected():
        bot.event_chain_active = False
        return

    if forced_index is not None:
        bot.event_chain_index = forced_index % len(EVENT_CHAIN)
    else:
        bot.event_chain_index = (bot.event_chain_index + 1) % len(EVENT_CHAIN)

    key, label = EVENT_CHAIN[bot.event_chain_index]
    url = TRACKS.get(key)
    if not url:
        bot.event_chain_active = False
        return

    bot.current_generation += 1
    my_gen = bot.current_generation
    bot.current_track = label
    bot.current_url = url
    print(f'🔁 Плейлист GTA 6: переходим к "{label}"')
    await asyncio.sleep(0.5)
    asyncio.create_task(play_audio_by_url(voice_client, url, label, my_gen))

@bot.event
async def on_ready():
    print('=' * 50)
    print(f'✅ Бот {bot.user} успешно запущен!')
    print(f'📡 На серверах: {len(bot.guilds)}')
    print('=' * 50)
    print('🎵 Бот готов к работе!')
    bot.add_view(HubView())
    bot.add_view(PlayView())
    bot.add_view(UpdateLogsView(current='v1.1'))

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user:
        if before.channel and not after.channel:
            print('🔌 Бот отключён от войса')
            bot.currently_playing = False
            bot.loop_running = False
            bot.current_track = None
            bot.current_url = None
            bot.current_generation += 1
            bot.voice_client = None
            bot.event_chain_active = False

async def connect_and_play_url(voice_channel, url, track_name, ctx=None):
    if bot.is_connecting:
        print('⏳ Уже идёт подключение, пропускаю запрос')
        if ctx: await ctx.send('⏳ __**Подожди, бот уже подключается...**__')
        return

    bot.is_connecting = True
    try:
        voice_client = discord.utils.get(bot.voice_clients, guild=voice_channel.guild)

        if (voice_client and voice_client.is_connected()
                and voice_client.channel == voice_channel
                and bot.currently_playing and bot.current_url == url):
            print(f'🎵 Уже играет: {track_name}')
            if ctx: await ctx.send(f'🎵 __**Уже играет:**__ **{track_name}**')
            return

        if voice_client and voice_client.is_playing():
            print(f'🔄 Останавливаю текущий трек')
            voice_client.stop()
            bot.currently_playing = False
            bot.loop_running = False
            await asyncio.sleep(0.5)

        bot.current_generation += 1
        my_gen = bot.current_generation
        bot.current_track = track_name
        bot.current_url = url

        if voice_client is None:
            try:
                print(f'🔊 Подключаюсь к {voice_channel.name}...')
                voice_client = await asyncio.wait_for(
                    voice_channel.connect(timeout=15.0, reconnect=False),
                    timeout=20.0
                )
                print(f'🔊 Подключился к {voice_channel.name}')
            except asyncio.TimeoutError:
                print('❌ Таймаут подключения')
                if ctx: await ctx.send('❌ __**Таймаут подключения к войсу. Проверь интернет.**__')
                return
            except Exception as e:
                print(f'❌ Ошибка подключения: {e}')
                if ctx: await ctx.send(f'❌ __**Ошибка подключения:**__ {e}')
                return
        elif voice_client.channel != voice_channel:
            try:
                print(f'🔊 Перемещаюсь в {voice_channel.name}...')
                await asyncio.wait_for(voice_client.move_to(voice_channel), timeout=15.0)
                print(f'🔊 Переместился в {voice_channel.name}')
            except asyncio.TimeoutError:
                print('❌ Таймаут перемещения')
                if ctx: await ctx.send('❌ __**Таймаут перемещения.**__')
                return
            except Exception as e:
                print(f'❌ Ошибка перемещения: {e}')
                if ctx: await ctx.send(f'❌ __**Ошибка перемещения:**__ {e}')
                return
        else:
            print(f'🔊 Уже в нужном канале: {voice_channel.name}')

        await asyncio.sleep(0.5)

        if voice_client is None or not voice_client.is_connected():
            print('❌ Не удалось подключиться к войсу')
            if ctx: await ctx.send('❌ __**Не удалось подключиться к войсу.**__')
            return

        bot.currently_playing = True
        bot.voice_client = voice_client

        if ctx: await ctx.send(f'🎵 __**Играет:**__ **{track_name}** в **{voice_channel.name}**')
        asyncio.create_task(play_audio_by_url(voice_client, url, track_name, my_gen))

    finally:
        bot.is_connecting = False

# ===== КОМАНДЫ =====

@bot.command(name='play')
async def play_command(ctx):
    voice_channel = get_author_voice_channel(ctx)
    if not voice_channel:
        await ctx.send('❌ __**Ты не в голосовом канале! Зайди в войс и попробуй снова.**__')
        return
    if not await ensure_bot_free_or_same(ctx, voice_channel):
        return
    bot.event_chain_active = False
    await send_hub(ctx)
    await connect_and_play_url(voice_channel, DEFAULT_AUDIO_URL, 'Лашара', ctx)

@bot.command(name='join')
async def join_command(ctx):
    voice_channel = get_author_voice_channel(ctx)
    if not voice_channel:
        await ctx.send('❌ __**Ты не в голосовом канале! Зайди в войс и попробуй снова.**__')
        return
    if not await ensure_bot_free_or_same(ctx, voice_channel):
        return
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client is None:
        try:
            await asyncio.wait_for(voice_channel.connect(timeout=15.0, reconnect=False), timeout=20.0)
            await ctx.send(f'🔊 __**Подключился к**__ **{voice_channel.name}**!')
        except asyncio.TimeoutError:
            await ctx.send('❌ __**Таймаут подключения. Проверь интернет.**__')
        except Exception as e:
            await ctx.send(f'❌ __**Ошибка подключения:**__ {e}')
    elif voice_client.channel != voice_channel:
        try:
            await asyncio.wait_for(voice_client.move_to(voice_channel), timeout=15.0)
            await ctx.send(f'🔊 __**Переместился в**__ **{voice_channel.name}**!')
        except Exception as e:
            await ctx.send(f'❌ __**Ошибка перемещения:**__ {e}')
    else:
        await ctx.send('✅ __**Бот уже в твоём канале!**__')

@bot.command(name='stop')
async def stop_command(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client:
        if voice_client.is_playing(): voice_client.stop()
        bot.currently_playing = False
        bot.loop_running = False
        bot.current_track = None
        bot.current_url = None
        bot.current_generation += 1
        bot.event_chain_active = False
        await ctx.send('⏹️ __**Музыка остановлена!**__ (бот остаётся в канале)')
    else:
        await ctx.send('❌ __**Бот не в канале!**__')

@bot.command(name='leave')
async def leave_command(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client:
        if voice_client.is_playing(): voice_client.stop()
        await voice_client.disconnect(force=True)
        bot.currently_playing = False
        bot.loop_running = False
        bot.current_track = None
        bot.current_url = None
        bot.current_generation += 1
        bot.voice_client = None
        bot.event_chain_active = False
        await ctx.send('👋 __**Бот отключился от голосового канала!**__')
    else:
        await ctx.send('❌ __**Бот не в канале!**__')

@bot.command(name='hub')
async def hub_command(ctx):
    await send_hub(ctx)

@bot.command(name='now')
async def now_command(ctx):
    if bot.currently_playing and bot.current_track:
        await ctx.send(f'🎵 __**Сейчас играет:**__ **{bot.current_track}**')
    else:
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client and voice_client.is_connected():
            await ctx.send('🔇 __**Бот в канале, но музыка не играет**__')
        else:
            await ctx.send('❌ __**Бот не в канале и музыка не играет!**__')

@bot.command(name='volume')
async def volume_command(ctx, value: int = None):
    if value is None:
        await ctx.send(f'🔊 __**Текущая громкость:**__ **{bot.volume}%**')
        return
    if value < 1 or value > 100:
        await ctx.send('❌ __**Громкость должна быть от 1 до 100!**__')
        return
    bot.volume = value
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_playing():
        if isinstance(voice_client.source, discord.PCMVolumeTransformer):
            voice_client.source.volume = value / 100
    await ctx.send(f'🔊 __**Громкость установлена на**__ **{value}%**')

@bot.command(name='list')
async def list_tracks(ctx):
    embed = build_music_list_embed(ctx.guild)
    if os.path.exists(PLAY_IMAGE):
        file = discord.File(PLAY_IMAGE, filename='play.png')
        embed.set_image(url='attachment://play.png')
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)

@bot.command(name='test')
async def test_command(ctx):
    await ctx.send('__**Я пащу**__ 💀')

@bot.command(name='restart')
async def restart_command(ctx):
    if bot.current_url:
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client:
            old_url = bot.current_url
            old_track = bot.current_track
            if voice_client.is_playing(): voice_client.stop()
            bot.currently_playing = False
            bot.current_generation += 1
            await asyncio.sleep(0.5)
            bot.current_generation += 1
            my_gen = bot.current_generation
            bot.current_track = old_track
            bot.current_url = old_url
            bot.currently_playing = True
            asyncio.create_task(play_audio_by_url(voice_client, old_url, old_track, my_gen))
            await ctx.send('🔄 __**Перезапустил воспроизведение**__')
        else:
            await ctx.send('❌ __**Бот не в канале!**__')
    else:
        await ctx.send('❌ __**Нет активного трека!**__')

# === ОБРАБОТЧИК !event-gta6 music ===
@bot.event
async def on_message(message):
    if not message.content: return
    content = message.content.strip().lower()
    parts = content.split()

    if len(parts) >= 2 and parts[0] == '!event-gta6' and parts[1] == 'music':
        sub = parts[2] if len(parts) >= 3 else None

        if sub is None:
            voice_channel = None
            if hasattr(message.author, 'voice') and message.author.voice and message.author.voice.channel:
                voice_channel = message.author.voice.channel

            bot_channel = get_bot_voice_channel(message.guild)
            if bot_channel and (voice_channel is None or not same_voice_channel(bot_channel, voice_channel)):
                await message.channel.send(
                    f'❌ __**Бот уже занят в другом голосовом канале:**__ **{bot_channel.name}**'
                )
                return

            if not voice_channel:
                await message.channel.send('❌ __**Ты не в голосовом канале! Зайди в войс и попробуй снова.**__')
                return

            bot.event_chain_active = True
            bot.event_chain_index = 0
            await connect_and_play_url(
                voice_channel,
                TRACKS['blood-in-your-eyes'],
                'Blood In Your Eyes',
                ctx=None
            )
            await message.channel.send(
                f'🎵 __**Играет:**__ **Blood In Your Eyes** в **{voice_channel.name}**\n'
                f'🎶 __**Плейлист GTA 6:**__ Blood In Your Eyes ➡️ Love Is A Long Road ➡️ Hot Together ➡️ RHYNO (по кругу)'
            )
            return

        if sub == 'next':
            vc = discord.utils.get(bot.voice_clients)
            if not vc or not vc.is_connected():
                await message.channel.send('❌ __**Бот сейчас не играет Плейлист GTA 6.**__')
                return
            bot.event_chain_active = True
            await _advance_event_chain(vc)
            await message.channel.send(f'⏭️ __**Следующая песня Плейлиста GTA 6:**__ **{bot.current_track}**')
            return

        if sub == 'how':
            if bot.current_track and bot.event_chain_active:
                await message.channel.send(f'🎵 __**Сейчас из Плейлиста GTA 6 играет:**__ **{bot.current_track}**')
            else:
                await message.channel.send('❌ __**Плейлист GTA 6 сейчас не играет.**__')
            return

        if sub == 'stop':
            vc = discord.utils.get(bot.voice_clients)
            if vc and vc.is_playing():
                vc.stop()
            bot.currently_playing = False
            bot.loop_running = False
            bot.current_track = None
            bot.current_url = None
            bot.current_generation += 1
            bot.event_chain_active = False
            await message.channel.send('⏹️ __**Плейлист GTA 6 остановлен.**__')
            return

        await message.channel.send('❌ __**Неизвестная подкоманда. Используй:**__ `!event-gta6 music`, `!event-gta6 music next`, `!event-gta6 music how`, `!event-gta6 music stop`')
        return

    await bot.process_commands(message)

if __name__ == '__main__':
    try:
        print('🚀 Запуск бота...')
        if not TOKEN:
            raise RuntimeError(
                'Не задан DISCORD_TOKEN. Добавь токен бота в переменные окружения.'
            )
        bot.run(TOKEN)
    except Exception as e:
        print(f'❌ Ошибка: {e}')
        input('Нажмите Enter для выхода...')
