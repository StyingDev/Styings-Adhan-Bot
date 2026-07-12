import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import pytz
import datetime

ALADHAN_API_URL = 'http://api.aladhan.com/v1/timings'
EMBED_COLOR = 0x757e8a
RESETUP_MESSAGE = "Your saved location needs a refresh — please run /setup again."


def timings_params(settings):
    """Aladhan query params from stored coordinates (aiohttp needs strings)."""
    return {
        'latitude': str(settings["latitude"]),
        'longitude': str(settings["longitude"]),
        'method': settings["calculation_method"],
        'school': settings["asr_method"],
        'timezonestring': settings["timezone"],
    }

class TimingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} is online")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='upcoming', description='View your next upcoming prayer time.')
    async def upcoming(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        settings = await self.bot.db.get_user(user_id)
        if settings and settings["timezone"]:
            if settings["latitude"] is None:
                await interaction.response.send_message(RESETUP_MESSAGE, ephemeral=True)
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(ALADHAN_API_URL, params=timings_params(settings)) as response:
                    data = await response.json()
                    timings = data['data']['timings']

                    user_timezone = pytz.timezone(settings["timezone"])
                    utc = pytz.utc
                    current_time = datetime.datetime.now(utc).astimezone(user_timezone)

                    formatted_timings = {prayer: time for prayer, time in timings.items() if prayer in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]}

                    if not formatted_timings:
                        embed = discord.Embed(title="Upcoming Salah", description=f"No upcoming salah times found for {settings['city']}.", color=EMBED_COLOR)
                        await interaction.response.send_message(embed=embed)
                        return

                    next_prayer = min(formatted_timings, key=lambda x: formatted_timings[x] if current_time.strftime('%H:%M') < formatted_timings[x] else '23:59')
                    next_time = formatted_timings[next_prayer]

                    next_time_12hr = datetime.datetime.strptime(next_time, '%H:%M').strftime('%I:%M %p')

                    embed = discord.Embed(title="Next Upcoming Salah", description=f"Next upcoming salah for {settings['city']} is {next_prayer} at {next_time_12hr}.", color=EMBED_COLOR)
                    embed.set_footer(text=f"🕌 Timings for {settings['city']}")
                    await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("Please set up your region using /setup first.")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='timings', description='Lists all Prayer timings in your region')
    async def timings(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        settings = await self.bot.db.get_user(user_id)
        if settings and settings["timezone"]:
            if settings["latitude"] is None:
                await interaction.response.send_message(RESETUP_MESSAGE, ephemeral=True)
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(ALADHAN_API_URL, params=timings_params(settings)) as response:
                    data = await response.json()
                    timings = data['data']['timings']

                    user_timezone = pytz.timezone(settings["timezone"])
                    utc = pytz.utc
                    current_time = datetime.datetime.now(utc).astimezone(user_timezone)

                    formatted_timings = {prayer: time for prayer, time in timings.items()}

                    if not formatted_timings:
                        embed = discord.Embed(title="Adhan Timings", description=f"All prayer times for {settings['city']} have passed for today.", color=EMBED_COLOR)
                        await interaction.response.send_message(embed=embed)
                        return

                    prayer_order = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
                    timings_to_display = {prayer: formatted_timings[prayer] for prayer in prayer_order if prayer in formatted_timings}

                    timings_12hr = {prayer: datetime.datetime.strptime(time, '%H:%M').strftime('%I:%M %p') for prayer, time in timings_to_display.items()}

                    description = "\n".join([f"**{prayer}:** {time}" for prayer, time in timings_12hr.items()])
                    embed = discord.Embed(title="Adhan Timings", description=description, color=EMBED_COLOR)
                    embed.set_footer(text=f"🌙 Timings for {settings['city']}")

                    await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("Please set up your region using /setup first.")


async def setup(bot):
    await bot.add_cog(TimingsCog(bot))