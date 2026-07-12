import discord
from discord.ext import commands, tasks
import os
import asyncio
from dotenv import load_dotenv

from database import Database

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix='A!', intents=intents)

bot.db = Database()

PRESENCE_INTERVAL_SECONDS = 120

async def build_presences():
    stats = await bot.db.get_stats()
    member_count = sum(guild.member_count or 0 for guild in bot.guilds)
    presences = [
        discord.CustomActivity(name="Reminding the Ummah to pray"),
        discord.CustomActivity(name=f"Serving {stats['users']} believers in {len(bot.guilds)} servers"),
        discord.CustomActivity(name=f"{stats['active_loops']} prayer reminder loops running"),
        discord.CustomActivity(name=f"Ummah across {stats['countries']} countries & {stats['cities']} cities"),
        discord.CustomActivity(name=f"Watching over {member_count:,} members"),
        discord.CustomActivity(name="/setup to get prayer reminders"),
        discord.CustomActivity(name="Salah is better than sleep"),
        discord.Game(name="Bot Dev - tr.ee/sty"),
    ]
    if stats['top_city']:
        presences.insert(5, discord.CustomActivity(name=f"{stats['top_city'].title()} leads with {stats['top_city_users']} believers"))
    return presences

@tasks.loop(seconds=PRESENCE_INTERVAL_SECONDS)
async def rotate_presence():
    presences = await build_presences()
    activity = presences[rotate_presence.current_loop % len(presences)]
    try:
        await bot.change_presence(activity=activity)
    except Exception as e:
        print(f"Failed to update presence: {e}")

@rotate_presence.before_loop
async def before_rotate_presence():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    if not rotate_presence.is_running():
        rotate_presence.start()
    await bot.tree.sync()
    print(f'We have logged in as {bot.user.name}')

async def load():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"Loaded cog: {filename[:-3]}")

async def main():
    await bot.db.connect()
    try:
        async with bot:
            await load()
            await bot.start(TOKEN)
    finally:
        await bot.db.close()

if __name__ == "__main__":
    asyncio.run(main())
