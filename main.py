import discord
from discord.ext import commands
import os
import asyncio
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Settings file path
SETTINGS_FILE = 'user_settings.json'

# Initialize bot with intents
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix='A!', intents=intents)

# Load user settings from JSON file
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump({}, f)

with open(SETTINGS_FILE, 'r') as f:
    user_settings = json.load(f)

# Make user_settings available to all cogs
bot.user_settings = user_settings

# Save settings function that can be called from cogs
async def save_settings():
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(bot.user_settings, f)

# Make save_settings available to all cogs
bot.save_settings = save_settings

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="🌲linktr.ee/Stying"))
    await bot.tree.sync()
    print(f'We have logged in as {bot.user.name}')

# Load all cogs
async def load():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"Loaded cog: {filename[:-3]}")

# Main function to start the bot
async def main():
    async with bot:
        await load()
        await bot.start(TOKEN)

# Run the bot
if __name__ == "__main__":
    asyncio.run(main())