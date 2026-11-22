

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
# ЗАПУСК — БЕЗОПАСНАЯ ВЕРСИЯ
# ============================================================
async def _run_with_retry():
    """
    Безопасный запуск: при 429 (Cloudflare 1015) НЕ долбим Discord,
    а ждём длинную паузу и пробуем ОДИН раз. При 401/403 — выходим.
    """
    try:
        await bot.start(TOKEN)
    except discord.LoginFailure:
        log.error("❌ Неверный токен (401). Останавливаюсь, повторов не будет.")
        return
    except discord.PrivilegedIntentsRequired:
        log.error(
            "❌ Включи привилегированные интенты:\n"
            "   PRESENCE INTENT\n   SERVER MEMBERS INTENT\n   MESSAGE CONTENT INTENT"
        )
        return
    except discord.HTTPException as e:
        if e.status == 429:
            log.error(
                "❌ 429 / Cloudflare 1015: IP временно заблокирован. "
                "Жду 15 минут и пробую ОДИН раз. "
                "Если снова 429 — остановлюсь, чтобы не продлевать блокировку."
            )
            await asyncio.sleep(900)
            try:
                await bot.start(TOKEN)
            except Exception as e2:
                log.error("❌ Повторный запуск не удался: %r. Останавливаюсь.", e2)
                return
        elif e.status == 503:
            log.warning("⚠️ 503 от Discord. Жду 5 минут и пробую один раз…")
            await asyncio.sleep(300)
            try:
                await bot.start(TOKEN)
            except Exception as e2:
                log.error("❌ Повторный запуск не удался: %r. Останавливаюсь.", e2)
                return
        elif e.status in (401, 403):
            log.error("❌ %s: токен недействителен или нет прав. Останавливаюсь.", e.status)
            return
        else:
            log.error("❌ HTTP %s: %r. Останавливаюсь.", e.status, e)
            return
    except Exception as e:
        log.error("❌ Ошибка запуска: %r. Останавливаюсь.", e)
        return


def main():
    if not TOKEN:
        log.error("❌ Токен не задан! Установи переменную окружения DISCORD_TOKEN.")
        return
    if not OWNER_IDS:
        log.warning("⚠️ OWNER_ID не задан — админ-команды недоступны никому.")
    if not PANEL_IMAGE_URL:
        log.warning("⚠️ PANEL_IMAGE_URL не задан — картинка панели не будет показана.")

    load_settings()

    keep_alive()

    try:
        asyncio.run(_run_with_retry())
    except KeyboardInterrupt:
        log.info("Бот остановлен.")


if __name__ == "__main__":
    main()
