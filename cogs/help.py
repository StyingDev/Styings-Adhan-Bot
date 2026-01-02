import discord
from discord.ext import commands
from discord import app_commands

# Embed color
EMBED_COLOR = 0x757e8a

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} is online")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='help', description='Execute for help.')
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Adhan Bot Help", description="Here are the available commands for the Adhan Bot:", color=EMBED_COLOR)

        embed.add_field(name="/setup", value="Set up your region settings (country, city, timezone and salah time calculations).", inline=False)
        embed.add_field(name="/region", value="View your current region settings.", inline=False)
        embed.add_field(name="/upcoming", value="Get the upcoming salah time for your region.", inline=False)
        embed.add_field(name="/timings", value="Get all the salah timings for your region.", inline=False)
        embed.add_field(name="/notify", value="Schedule a DM notification for the next salah time.", inline=False)
        embed.add_field(name="/notifyloop", value="Set a notification chain for all upcoming salahs.", inline=False)
        embed.add_field(name="/notifyloopstop", value="Stop the notification chain for upcoming salahs.", inline=False)
        embed.add_field(name="/qibla", value="Get the Qibla direction from your location.", inline=False)
        embed.add_field(name="/mosque", value="Find mosques near a provided location.", inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))