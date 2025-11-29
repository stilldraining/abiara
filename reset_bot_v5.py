import os
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

VALID_AMMO = {"M995", "BS", "AP", "SS198"}


def parse_time_string(time_str):
    try:
        return datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        return None


def compute_reset_info(reset_time):
    now = datetime.now()
    reset_dt = now.replace(
        hour=reset_time.hour,
        minute=reset_time.minute,
        second=0,
        microsecond=0,
    )

    if reset_dt > now:
        reset_dt -= timedelta(days=1)

    elapsed = (now - reset_dt).total_seconds() / 60

    if elapsed < 0 or elapsed >= 80:
        return None, None, None, None

    cycle_start = reset_dt
    safe_end = cycle_start + timedelta(minutes=40)
    reset_end = cycle_start + timedelta(minutes=80)

    return elapsed, cycle_start, safe_end, reset_end


@tree.command(
    name="lastreset",
    description="Check ammo price reset window using time and ammo type"
)
@app_commands.describe(
    time="Time of the last reset in HH:MM format",
    ammo="Ammo type (M995, BS, AP, SS198)"
)
async def lastreset(interaction: discord.Interaction, time: str, ammo: str):

    ammo = ammo.upper().strip()
    if ammo not in VALID_AMMO:
        await interaction.response.send_message(
            f"Invalid ammo. Use: M995, BS, AP, SS198",
            ephemeral=True
        )
        return

    t = parse_time_string(time)
    if not t:
        await interaction.response.send_message(
            "Invalid time. Use HH:MM format.",
            ephemeral=True
        )
        return

    elapsed, cycle_start, safe_end, reset_end = compute_reset_info(t)

    if elapsed is None:
        await interaction.response.send_message(
            "This reset time is too old. Provide one from the last 80 minutes.",
            ephemeral=True
        )
        return

    if elapsed < 40:
        msg = (
            f"The next price reset window for {ammo} starts at "
            f"{safe_end.strftime('%H:%M')}."
        )
    else:
        msg = (
            f"The reset window for {ammo} is active.\n"
            f"Started at {safe_end.strftime('%H:%M')} and ends at {reset_end.strftime('%H:%M')}."
        )

    await interaction.response.send_message(msg)


@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
    print(f"Bot is in {len(bot.guilds)} guild(s)")
    
    # Wait a moment for Discord to fully register the connection
    await asyncio.sleep(2)
    
    try:
        # Use global sync - works for all guilds, more reliable
        synced = await tree.sync()
        print(f"Synced {len(synced)} command(s) globally.")
        for cmd in synced:
            print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"Slash sync error: {e}")
        import traceback
        traceback.print_exc()


bot.run(TOKEN)
