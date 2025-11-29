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


def construct_reset_time(minutes: int, current_hour: bool):
    """Construct reset datetime from minutes and current/previous hour flag."""
    now = datetime.now()
    
    if current_hour:
        reset_hour = now.hour
        reset_dt = now.replace(hour=reset_hour, minute=minutes, second=0, microsecond=0)
    else:
        # Previous hour - handle day rollover
        reset_dt = now - timedelta(hours=1)
        reset_dt = reset_dt.replace(minute=minutes, second=0, microsecond=0)
    
    return reset_dt


def compute_reset_info(reset_dt):
    """Calculate reset window information from reset datetime."""
    now = datetime.now()
    elapsed = (now - reset_dt).total_seconds() / 60

    if elapsed < 0 or elapsed >= 80:
        return None, None, None, None

    cycle_start = reset_dt
    safe_end = cycle_start + timedelta(minutes=40)
    reset_end = cycle_start + timedelta(minutes=80)

    return elapsed, cycle_start, safe_end, reset_end


@tree.command(
    name="lastreset",
    description="Check ammo price reset window using minutes and ammo type"
)
@app_commands.describe(
    minutes="Minutes of the last reset (00-59)",
    current_hour="True if reset happened in current hour, False if previous hour",
    ammo="Ammo type (M995, BS, AP, SS198)"
)
async def lastreset(interaction: discord.Interaction, minutes: int, current_hour: bool, ammo: str):

    ammo = ammo.upper().strip()
    if ammo not in VALID_AMMO:
        await interaction.response.send_message(
            f"Invalid ammo. Use: M995, BS, AP, SS198",
            ephemeral=True
        )
        return

    # Validate minutes
    if minutes < 0 or minutes > 59:
        await interaction.response.send_message(
            "Invalid minutes. Use 00-59.",
            ephemeral=True
        )
        return

    # Construct reset time from minutes and current/previous hour
    reset_dt = construct_reset_time(minutes, current_hour)
    elapsed, cycle_start, safe_end, reset_end = compute_reset_info(reset_dt)

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
