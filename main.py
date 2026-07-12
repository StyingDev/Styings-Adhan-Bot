import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv

from database import Database

load_dotenv()
TOKEN = os.getenv("TOKEN")

# Legacy settings file, imported into SQLite on first run
LEGACY_SETTINGS_FILE = 'user_settings.json'

intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix='A!', intents=intents)

# Available to all cogs as self.bot.db
bot.db = Database()

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="🌲linktr.ee/Stying"))
    await bot.tree.sync()
    print(f'We have logged in as {bot.user.name}')

async def load():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"Loaded cog: {filename[:-3]}")

async def main():
    await bot.db.connect()
    await bot.db.migrate_from_json(LEGACY_SETTINGS_FILE)
    try:
        async with bot:
            await load()
            await bot.start(TOKEN)
    finally:
        await bot.db.close()

if __name__ == "__main__":
    asyncio.run(main())
