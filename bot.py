# bot.py
import discord
from discord import app_commands, ui
from discord.ext import commands
import aiohttp
import re
import emoji
from emoji import demojize
import time
import asyncio
from typing import Dict, Set, List

EMOJI_REGEX = r"<(a?):([^:]+):(\d+)>"

# --- Bot ---------------------------------------------------------------------------------------
class EmojiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.session: aiohttp.ClientSession | None = None
        self.user_cooldowns: Dict[str, float] = {}       # 'user_id_bucket' -> last timestamp
        self.waiting_for_sticker: Set[int] = set()       # users waiting in /s2img

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        await self.tree.sync(guild=None)
        print(f"Logged in as {self.user} — slash commands synced globally")

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

bot = EmojiBot()

# --- Status ------------------------------------------------------------------------------------
status = discord.Status.online 

# --- Utils -------------------------------------------------------------------------------------
def extract_unicode_emojis(text: str) -> List[str]:
    return [c for c in text if c in emoji.EMOJI_DATA]

def check_and_set_cooldown(user_id: int, cooldown_seconds: float = 5.0, bucket: str = "global") -> bool:
    """
    Checks cooldown for a specific bucket (e.g., 'global' vs 'cleardms').
    """
    now = time.time()
    key = f"{user_id}_{bucket}"
    last = bot.user_cooldowns.get(key, 0.0)
    if now - last < cooldown_seconds:
        return False
    bot.user_cooldowns[key] = now
    return True

# --- UI: More Info button for default stickers ---------------------------------------------------
class StickerInfoButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="More Info", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(name="info", id=1480601139664785499))
    async def more_info(self, interaction: discord.Interaction, button: ui.Button):
        msg = (
            "Discord's default stickers are **Canvas-based** and **NOT** stored as downloadable files.\n"
            "They render inside Discord but aren't exposed as files which you can download.\n\n"
            "Default sticker sets may include:\n"
            "- Mallow the Rascal\n"
            "- Wumpus Beyond\n"
            "- Doggo Replies\n"
            "- Cheerful Choco\n"
            "- Hammy Ham\n"
            "- Smug Shiba\n"
            "- Clyde Bot\n"
            "- Chaos Cat\n"
            "- Robo Nelly\n"
            "- Sassy Peach\n"
            "- Lonely Leif\n"
            "- Wumpus & Co\n"
            "- Daily Routine\n"
            "- Phibi The Scholar\n"
            "- Melty Chihuahua"
        )
        await interaction.response.send_message(msg, ephemeral=True)

# --- Core processing ----------------------------------------------------------------------------
async def process_input(source, text: str, stickers: List[discord.StickerItem]):
    is_interaction = isinstance(source, discord.Interaction)
    clean_input = (text or "").strip().replace('\u200b', '')

    custom_matches = list(re.finditer(EMOJI_REGEX, clean_input))
    unicode_emojis = extract_unicode_emojis(clean_input)
    total_emojis = len(custom_matches) + len(unicode_emojis)
    if total_emojis > 5:
        msg = "<:error:1480600746629136448> You can't put more than 5 emojis at once."
        if is_interaction:
            await source.response.send_message(msg, ephemeral=True)
        else:
            await source.channel.send(msg)
        return

    links: List[str] = []

    for match in custom_matches:
        is_animated, name, emoji_id = match.groups()
        extension = "gif" if is_animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}?quality=lossless"
        links.append(f"<:link:1456686996381499433>[**{name}**]({url})")

    for u in unicode_emojis:
        name = demojize(u).replace(":", "")
        codepoints = '-'.join(f"{ord(c):x}" for c in u)
        url = f"https://twemoji.maxcdn.com/v/latest/72x72/{codepoints}.png"
        links.append(f"<:link:1456686996381499433>[**{name}**]({url})")

    for s in stickers:
        try:
            full_sticker = await bot.fetch_sticker(s.id)
        except discord.NotFound:
            links.append(f"<:error:1480600746629136448> [**{s.name}**] Sticker not found.")
            continue
        except discord.HTTPException as e:
            links.append(f"<:error:1480600746629136448> [**{s.name}**] Error fetching sticker ({e}).")
            continue

        url = getattr(full_sticker, "url", None) or getattr(full_sticker, "asset_url", None)
        if url:
            links.append(f"<:link:1456686996381499433>[**{full_sticker.name}**]({url})")
        else:
            view = StickerInfoButton()
            msg_text = "<:info:1480601139664785499> Discord's default stickers are not compatible with Emojimage"
            if is_interaction:
                try:
                    await source.response.send_message(msg_text, view=view, ephemeral=True)
                except Exception:
                    await source.followup.send(msg_text, view=view, ephemeral=True)
            else:
                await source.channel.send(msg_text, view=view)
            return

    if not links:
        msg = "<:error:1480600746629136448> No valid emojis or stickers found."
        if is_interaction:
            await source.response.send_message(msg, ephemeral=True)
        else:
            await source.channel.send(msg)
        return

    message_content = "\n".join(links)
    if is_interaction:
        try:
            await source.response.defer()
        except Exception:
            pass
        await source.followup.send(message_content)
    else:
        await source.channel.send(message_content)

# --- Slash commands --------------------------------------------------------------------------------
@bot.tree.command(name="ping", description="Check bot latency")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def ping(interaction: discord.Interaction):
    if not check_and_set_cooldown(interaction.user.id):
        return await interaction.response.send_message(
            "<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.",
            ephemeral=True
        )
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓Pong! **{latency_ms}ms.**")

@bot.tree.command(name="about", description="About Emojimage")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def about_cmd(interaction: discord.Interaction):
    if not check_and_set_cooldown(interaction.user.id):
        return await interaction.response.send_message("<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.", ephemeral=True)
    about_text = (
        "**Emojimage** — extract original emoji & sticker images.\n\n"
        "• Convert custom Discord emojis to direct CDN links\n"
        "• Convert Unicode emojis to Twemoji links\n"
        "• Export server stickers (where possible). Default Canvas stickers are unsupported\n\n"
        "Privacy: Emojimage **does not store** images or message content persistently. Images are only used to compose links sent back to you."
    )
    await interaction.response.send_message(about_text, ephemeral=True)

@bot.tree.command(name="source", description="Get the bot source repository")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def source_cmd(interaction: discord.Interaction):
    if not check_and_set_cooldown(interaction.user.id):
        return await interaction.response.send_message("<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.", ephemeral=True)
    await interaction.response.send_message("<:github:1456700755313561793> [GitHub](https://github.com/SureK4sperl/emojimage-bot)", ephemeral=True)

@bot.tree.command(name="help", description="Show help message")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def help_cmd(interaction: discord.Interaction):
    if not check_and_set_cooldown(interaction.user.id):
        return await interaction.response.send_message("<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.", ephemeral=True)
    help_text = (
        "## ❓Emojimage - Help\n"
        "`/e2img` - *Extract images out of emojis*.\n"
        "`/s2img` - *Extract images out of stickers*.\n"
        "`/cleardms` - *Deletes my recent messages in your current DM*.\n"
        "`/ping` - *Check bot latency*.\n"
        "`/invite` - *Add bot to your server or your apps*.\n"
        "`/about` - *About Emojimage*.\n"
        "`/source` - *Source code repository*.\n"
        "`/help` - *Show this message*.\n\n"
        "Just DM me emojis or stickers and I will reply with their original image."
    )
    await interaction.response.send_message(help_text, ephemeral=True)

@bot.tree.command(name="invite", description="Get invite link")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def invite_cmd(interaction: discord.Interaction):
    if not check_and_set_cooldown(interaction.user.id):
        return await interaction.response.send_message("<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.", ephemeral=True)

    url = "[Invite Bot](https://discord.com/oauth2/authorize?client_id=1456291804994470064)"
    await interaction.response.send_message(url, ephemeral=True)

@bot.tree.command(name="e2img", description="Convert custom emojis or stickers into clickable links")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(emoji_input="Paste the custom emojis here")
async def e2img(interaction: discord.Interaction, emoji_input: str):
    if not check_and_set_cooldown(interaction.user.id):
        return await interaction.response.send_message("<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.", ephemeral=True)
    await process_input(interaction, emoji_input, stickers=[])

@bot.tree.command(name="s2img", description="Send a sticker and get its link")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def s2img(interaction: discord.Interaction):
    user_id = interaction.user.id
    if not check_and_set_cooldown(user_id):
        return await interaction.response.send_message("<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.", ephemeral=True)

    bot.waiting_for_sticker.add(user_id)
    try:
        await interaction.response.send_message("<:timer:1456691289008509011> Please send your sticker within 15 seconds.", ephemeral=True)

        def check(m: discord.Message):
            return (
                m.author.id == user_id
                and m.channel.id == interaction.channel.id
                and getattr(m, "stickers", None)
                and len(m.stickers) > 0
            )

        try:
            msg: discord.Message = await bot.wait_for("message", timeout=15.0, check=check)
            await process_input(msg, msg.content, stickers=msg.stickers)
        except asyncio.TimeoutError:
            await interaction.followup.send("<:error:1480600746629136448> 15 seconds have passed, no Sticker received. Try again.", ephemeral=True)
    finally:
        bot.waiting_for_sticker.discard(user_id)

@bot.tree.command(name="cleardms", description="Deletes my recent messages in this channel")
@app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True) 
@app_commands.allowed_installs(guilds=True, users=True) 
async def cleardms(interaction: discord.Interaction):
    user_id = interaction.user.id

    if interaction.guild is not None:
        return await interaction.response.send_message(
            "<:error:1480600746629136448> This command cannot be used inside a server.",
            ephemeral=True
        )

    if not check_and_set_cooldown(user_id, cooldown_seconds=20.0, bucket="cleardms"):
        return await interaction.response.send_message(
            "<:timer:1456691289008509011> Cooldown: Please wait 20s before using this command again.", 
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    try:
        # Step 1: Collect the messages
        bot_messages = []
        async for msg in interaction.channel.history(limit=200):
            if msg.author.id == bot.user.id:
                bot_messages.append(msg)

        total_messages = len(bot_messages)
        if total_messages == 0:
            return await interaction.followup.send(
                "<:info:1480601139664785499> No recent messages found to delete <3", 
                ephemeral=True
            )

        # Step 2: Start the loop and update the progress bar
        await interaction.followup.send(f"<:timer:1456691289008509011> Deleting Messages... (0%)", ephemeral=True)
        
        for i, msg in enumerate(bot_messages, start=1):
            try:
                await msg.delete()
            except discord.NotFound:
                pass

            if i % 3 == 0 or i == total_messages:
                percent = int((i / total_messages) * 100)
                if i == total_messages:
                    await interaction.edit_original_response(content="All messages deleted <3")
                else:
                    await interaction.edit_original_response(content=f"<:timer:1456691289008509011> Deleting Messages... ({percent}%)")
            
            await asyncio.sleep(1.5)

    except discord.Forbidden:
        error_msg = (
            "<:error:1480600746629136448> **Discord blocked this action.**\n"
            "To protect user privacy, Discord does not allow User Apps to read chat history in Group DMs or DMs with friends. "
            "I can only bulk-delete messages inside a direct, 1-on-1 DM with me!"
        )
        await interaction.followup.send(error_msg, ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"<:error:1480600746629136448> An error occurred: {e}", ephemeral=True)

# --- Context Menus (Right-click Message -> Apps) ---------------------------------------

@bot.tree.context_menu(name="Emojimage")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def emojimage_context(interaction: discord.Interaction, message: discord.Message):
    if not check_and_set_cooldown(interaction.user.id):
        return await interaction.response.send_message(
            "<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.",
            ephemeral=True
        )

    stickers = message.stickers if getattr(message, "stickers", None) else []
    content = message.content or ""
    await process_input(interaction, content, stickers)

# --- Secret Admin Sync Command -------------------------------------------------------
@bot.command()
@commands.is_owner() 
async def sync(ctx):
    await ctx.send("Syncing commands... Please wait.")
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Success! Synced {len(synced)} command(s) globally. Restart your Discord app now.")
    except Exception as e:
        await ctx.send(f"Failed to sync: {e}")

# --- Message listener (DMs only) -----------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)

    if message.author.bot:
        return

    user_id = message.author.id
    if user_id in bot.waiting_for_sticker:
        return

    if not isinstance(message.channel, discord.DMChannel):
        return

    if message.content.startswith("!"):
        return

    content = message.content or ""
    has_custom = bool(re.search(EMOJI_REGEX, content))
    has_unicode = bool(extract_unicode_emojis(content))
    has_sticker = bool(getattr(message, "stickers", None) and len(message.stickers) > 0)

    if not (has_custom or has_unicode or has_sticker):
        return

    if not check_and_set_cooldown(user_id):
        await message.channel.send("<:timer:1456691289008509011> Cooldown: Please wait 5s between actions.")
        return

    stickers = message.stickers if message.stickers else []
    await process_input(message, content, stickers)

# --- Run -----------------------------------------------------------------------------------------
if __name__ == "__main__":
    bot.run("YOUR_TOKEN_HERE")
