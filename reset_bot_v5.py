import os
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True  # Needed for prefix commands

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

VALID_AMMO = {"M995", "BS", "AP", "SS198"}

# Store latest reset per server: {guild_id: {ammo: reset_data}}
# reset_data: {reset_dt, ammo, user_id, username, timestamp, elapsed, safe_end, reset_end}
latest_resets = {}


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
            f"XX:{safe_end.strftime('%M')}."
        )
    else:
        msg = (
            f"The reset window for {ammo} is active.\n"
            f"Started at XX:{safe_end.strftime('%M')} and ends at XX:{reset_end.strftime('%M')}."
        )

    # Store this reset data for the server
    guild_id = interaction.guild_id
    if guild_id:
        if guild_id not in latest_resets:
            latest_resets[guild_id] = {}
        latest_resets[guild_id][ammo] = {
            "reset_dt": reset_dt,
            "ammo": ammo,
            "user_id": interaction.user.id,
            "username": interaction.user.display_name,
            "timestamp": datetime.now(),
            "elapsed": elapsed,
            "safe_end": safe_end,
            "reset_end": reset_end
        }

    await interaction.response.send_message(msg)


@bot.command(name="reset")
async def reset_command(ctx, *args):
    """Command to view or set the latest reset."""
    guild_id = ctx.guild.id
    
    # If no args provided, show latest reset
    if not args:
        if guild_id not in latest_resets or not latest_resets[guild_id]:
            await ctx.send("No reset data tracked yet. Use `/lastreset` first or set one with `!reset minutes:XX current_hour:true/false ammo:XXXX`")
            return
        
        # Show all tracked ammo types
        messages = []
        for tracked_ammo, data in latest_resets[guild_id].items():
            time_ago = (datetime.now() - data["timestamp"]).total_seconds() / 60
            time_ago_str = f"{int(time_ago)} min ago" if time_ago < 60 else f"{int(time_ago/60)} hour(s) ago"
            
            reset_minutes = data['reset_dt'].strftime('%M')
            
            if data["elapsed"] < 40:
                minutes_until_window = int(40 - data["elapsed"])
                status = f"→ Next window starts at XX:{data['safe_end'].strftime('%M')} (in ~{minutes_until_window} minutes)"
            else:
                status = f"→ Window active until XX:{data['reset_end'].strftime('%M')}"
            
            messages.append(
                f"**{tracked_ammo}**\n"
                f"Last reset: XX:{reset_minutes} (submitted by {data['username']} {time_ago_str})\n"
                f"{status}"
            )
        
        await ctx.send("\n\n".join(messages))
        return
    
    # Parse arguments: minutes:XX current_hour:true/false ammo:XXXX
    minutes = None
    current_hour = None
    ammo = None
    
    for arg in args:
        if arg.startswith("minutes:"):
            try:
                minutes = int(arg.split(":")[1])
            except (ValueError, IndexError):
                await ctx.send("Invalid minutes format. Use `minutes:XX` where XX is 00-59.")
                return
        elif arg.startswith("current_hour:"):
            hour_val = arg.split(":")[1].lower()
            if hour_val == "true":
                current_hour = True
            elif hour_val == "false":
                current_hour = False
            else:
                await ctx.send("Invalid current_hour format. Use `current_hour:true` or `current_hour:false`.")
                return
        elif arg.startswith("ammo:"):
            ammo = arg.split(":")[1].upper().strip()
    
    # Validate all required args are present
    if minutes is None or current_hour is None or ammo is None:
        await ctx.send("To set a reset, use: `!reset minutes:XX current_hour:true/false ammo:XXXX`\nExample: `!reset minutes:05 current_hour:true ammo:M995`")
        return
    
    if ammo not in VALID_AMMO:
        await ctx.send(f"Invalid ammo. Use: M995, BS, AP, SS198")
        return
    
    if minutes < 0 or minutes > 59:
        await ctx.send("Invalid minutes. Use 00-59.")
        return
    
    # Construct and validate reset time
    reset_dt = construct_reset_time(minutes, current_hour)
    elapsed, cycle_start, safe_end, reset_end = compute_reset_info(reset_dt)
    
    if elapsed is None:
        await ctx.send("This reset time is too old. Provide one from the last 80 minutes.")
        return
    
    # Store the reset
    if guild_id not in latest_resets:
        latest_resets[guild_id] = {}
    latest_resets[guild_id][ammo] = {
        "reset_dt": reset_dt,
        "ammo": ammo,
        "user_id": ctx.author.id,
        "username": ctx.author.display_name,
        "timestamp": datetime.now(),
        "elapsed": elapsed,
        "safe_end": safe_end,
        "reset_end": reset_end
    }
    
    if elapsed < 40:
        msg = f"Reset updated: **{ammo}** at XX:{reset_dt.strftime('%M')}\nNext window starts at XX:{safe_end.strftime('%M')} (set by {ctx.author.display_name})"
    else:
        msg = f"Reset updated: **{ammo}** at XX:{reset_dt.strftime('%M')}\nWindow active until XX:{reset_end.strftime('%M')} (set by {ctx.author.display_name})"
    
    await ctx.send(msg)




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
