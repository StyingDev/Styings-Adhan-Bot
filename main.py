import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import aiohttp
import pytz
import datetime
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
intents.message_content = True

SETTINGS_FILE = 'user_settings.json'
ALADHAN_API_URL = 'http://api.aladhan.com/v1/timingsByCity'

bot = commands.Bot(command_prefix='A!', intents=intents)

# Predefined list of timezones
timezones = [
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Australia/Sydney",
    "Asia/Dhaka",
    "Asia/Kolkata",
    "Asia/Dubai",
    "Africa/Cairo",
    "Europe/Paris",
    "America/Toronto",
    "America/Mexico_City",
    "Asia/Shanghai",
]

# Default Asr Calculation Method 
DEFAULT_ASR_METHOD = '1'
DEFAULT_CALC_METHOD = '2'

# Calculation Methods
calculation_methods = {
    '1': 'University of Islamic Sciences, Karachi (Recommended)',
    '2': 'Islamic Society of North America (ISNA)',
    '3': 'Muslim World League (MWL)',
    '4': 'Umm Al-Qura University, Makkah',
    '5': 'Egyptian General Authority of Survey',
    '7': 'Institute of Geophysics, University of Tehran',
    '8': 'Gulf Region',
    '9': 'Kuwait',
    '10': 'Qatar',
    '11': 'Majlis Ugama Islam Singapura, Singapore',
    '12': 'Union Organization islamic de France',
    '13': 'Diyanet İşleri Başkanlığı, Turkey',
    '14': 'Spiritual Administration of Muslims of Russia',
}

# Load user settings from JSON file
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump({}, f)

with open(SETTINGS_FILE, 'r') as f:
    user_settings = json.load(f)

# Embed color
EMBED_COLOR = 0x757e8a

class TimeZoneSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=tz, value=tz) for tz in timezones]
        super().__init__(
            placeholder="Select a timezone",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user_settings[user_id]["timezone"] = self.values[0]
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(user_settings, f)
        
        await interaction.response.edit_message(
            content="Timezone set. Now, please select your Asr timing method:",
            view=AsrMethodView()
        )


class AsrMethodSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Hanafi juristic (Recommended)", value='1'),
            discord.SelectOption(label="Standard (Shafi'i, Maliki, and Hanbali)", value='0')
        ]
        super().__init__(
            placeholder="Select an Asr timing method",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user_settings[user_id]["asr_method"] = self.values[0]
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(user_settings, f)
        
        await interaction.response.edit_message(
            content="Asr timing method set. Now, please select your calculation method:",
            view=CalculationMethodView()
        )


class CalculationMethodSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, value=key) for key, name in calculation_methods.items()]
        super().__init__(
            placeholder="Select a calculation method",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user_settings[user_id]["calculation_method"] = self.values[0]
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(user_settings, f)
        
        await interaction.response.edit_message(
            content="Setup complete! Your settings have been saved.",
            view=None,
        )


class AsrMethodView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(AsrMethodSelect())


class CalculationMethodView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(CalculationMethodSelect())


class SetupModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Setup Your Region")

        self.country = discord.ui.TextInput(label="Country", placeholder="Enter your country", required=True)
        self.city = discord.ui.TextInput(label="City", placeholder="Enter your city", required=True)
        
        self.add_item(self.country)
        self.add_item(self.city)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user_settings[user_id] = {
            "country": self.country.value,
            "city": self.city.value,
            "timezone": None,
            "asr_method": DEFAULT_ASR_METHOD,
            "calculation_method": DEFAULT_CALC_METHOD
        }
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(user_settings, f)

        await interaction.response.send_message(
            "Please select your timezone.",
            view=TimeZoneView(),
            ephemeral=True
        )


class TimeZoneView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(TimeZoneSelect())

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="🌲linktr.ee/Stying"))
    await bot.tree.sync()
    print(f'We have logged in as {bot.user.name}')
    check_notifications.start()

bot.remove_command("help")

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@bot.tree.command(name='help', description='Execute for help.')
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Adhan Bot Help", description="Here are the available commands for the Adhan Bot:", color=EMBED_COLOR)

    embed.add_field(name="/setup", value="Set up your region settings (country, city, timezone and salah time calculations).", inline=False)
    embed.add_field(name="/region", value="View your current region settings.", inline=False)
    embed.add_field(name="/upcoming", value="Get the upcoming salah time for your region.", inline=False)
    embed.add_field(name="/timings", value="Get all the salah timings for your region.", inline=False)
    embed.add_field(name="/notify", value="Schedule a DM notification for the next salah time.", inline=False)

    await interaction.response.send_message(embed=embed)


@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@bot.tree.command(name='setup', description='Setup your region, timezone, and Asr timing method.')
async def setup(interaction: discord.Interaction):
    await interaction.response.send_modal(SetupModal())
    

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@bot.tree.command(name='region', description='View your current set region and timezone.')
async def region(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id in user_settings:
        country = user_settings[user_id]["country"]
        city = user_settings[user_id]["city"]
        timezone = user_settings[user_id]["timezone"]
        asr_method = "Hanafi juristic (Recommended)" if user_settings[user_id]["asr_method"] == '1' else "Standard (Shafi'i, Maliki, and Hanbali)"
        calc_method = calculation_methods[user_settings[user_id]["calculation_method"]]
        embed = discord.Embed(title="Current Region Settings", description=f"Country: {country}\nCity: {city}\nTimezone: {timezone}\nAsr Method: {asr_method}\nCalculation Method: {calc_method}", color=EMBED_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("Please set up your region using /setup first.")

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@bot.tree.command(name='upcoming', description='View your next upcoming prayer time.')
async def upcoming(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if user_id in user_settings and user_settings[user_id]["timezone"]:
        params = {
            'city': user_settings[user_id]["city"],
            'country': user_settings[user_id]["country"],
            'method': user_settings[user_id]["calculation_method"],
            'timezone': user_settings[user_id]["timezone"],
            'school': user_settings[user_id]["asr_method"]
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(ALADHAN_API_URL, params=params) as response:
                data = await response.json()
                timings = data['data']['timings']

                # Convert timings to the user's local time
                user_timezone = pytz.timezone(user_settings[user_id]["timezone"])
                utc = pytz.utc
                current_time = datetime.datetime.now(utc).astimezone(user_timezone)

                formatted_timings = {prayer: time for prayer, time in timings.items() if prayer in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]}

                if not formatted_timings:
                    embed = discord.Embed(title="Upcoming Salah", description=f"No upcoming salah times found for {user_settings[user_id]['city']}.", color=EMBED_COLOR)
                    await interaction.response.send_message(embed=embed)
                    return

                next_prayer = min(formatted_timings, key=lambda x: formatted_timings[x] if current_time.strftime('%H:%M') < formatted_timings[x] else '23:59')
                next_time = formatted_timings[next_prayer]

                # Convert next_time to 12-hour format
                next_time_12hr = datetime.datetime.strptime(next_time, '%H:%M').strftime('%I:%M %p')

                embed = discord.Embed(title="Next Upcoming Salah", description=f"Next upcoming salah for {user_settings[user_id]['city']} is {next_prayer} at {next_time_12hr}.", color=EMBED_COLOR)
                embed.set_footer(text=f"🕌 Timings for {user_settings[user_id]['city']}")
                await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Please set up your region using /setup first.")

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@bot.tree.command(name='timings', description='Lists all Prayer timings in your region')
async def timings(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if user_id in user_settings and user_settings[user_id]["timezone"]:
        params = {
            'city': user_settings[user_id]["city"],
            'country': user_settings[user_id]["country"],
            'method': user_settings[user_id]["calculation_method"],
            'timezone': user_settings[user_id]["timezone"],
            'school': user_settings[user_id]["asr_method"]
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(ALADHAN_API_URL, params=params) as response:
                data = await response.json()
                timings = data['data']['timings']

                # Convert timings to the user's local time
                user_timezone = pytz.timezone(user_settings[user_id]["timezone"])
                utc = pytz.utc
                current_time = datetime.datetime.now(utc).astimezone(user_timezone)

                formatted_timings = {prayer: time for prayer, time in timings.items()}

                if not formatted_timings:
                    embed = discord.Embed(title="Adhan Timings", description=f"All prayer times for {user_settings[user_id]['city']} have passed for today.", color=EMBED_COLOR)
                    await interaction.response.send_message(embed=embed)
                    return

                prayer_order = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
                timings_to_display = {prayer: formatted_timings[prayer] for prayer in prayer_order if prayer in formatted_timings}

                # Convert timings to 12-hour format
                timings_12hr = {prayer: datetime.datetime.strptime(time, '%H:%M').strftime('%I:%M %p') for prayer, time in timings_to_display.items()}

                description = "\n".join([f"**{prayer}:** {time}" for prayer, time in timings_12hr.items()])
                embed = discord.Embed(title="Adhan Timings", description=description, color=EMBED_COLOR)
                embed.set_footer(text=f"🌙 Timings for {user_settings[user_id]['city']}")

                await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Please set up your region using /setup first.")

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@bot.tree.command(name='notify', description='Reminds you to pray two minutes before for Fajr, Dhuhr, Asr, Magrib and Isha.')
async def notify(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # Defer the response to give more time for API calls
    await interaction.response.defer(ephemeral=True)

    if user_id in user_settings and user_settings[user_id]["timezone"]:
        params = {
            'city': user_settings[user_id]["city"],
            'country': user_settings[user_id]["country"],
            'method': user_settings[user_id]["calculation_method"],
            'timezone': user_settings[user_id]["timezone"],
            'school': user_settings[user_id]["asr_method"]
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(ALADHAN_API_URL, params=params) as response:
                data = await response.json()
                timings = data.get('data', {}).get('timings', {})

                # Convert timings to the user's local time
                user_timezone = pytz.timezone(user_settings[user_id]["timezone"])
                current_time = datetime.datetime.now(user_timezone)

                formatted_timings = {prayer: time for prayer, time in timings.items() if prayer in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]}

                if not formatted_timings:
                    embed = discord.Embed(title="Notification", description=f"Notification is only available for Fajr, Dhuhr, Asr, Magrib and Isha. Please check your settings or try again later.", color=EMBED_COLOR)
                    await interaction.followup.send(embed=embed)
                    return

                next_prayer = min(formatted_timings, key=lambda x: formatted_timings[x] if current_time.strftime('%H:%M') < formatted_timings[x] else '23:59')
                next_time = formatted_timings[next_prayer]

                # Convert next_time to 12-hour format
                next_time_12hr = datetime.datetime.strptime(next_time, '%H:%M').strftime('%I:%M %p')

                embed = discord.Embed(title="Notification Scheduled", description=f"Next upcoming salah for {user_settings[user_id]['city']} is {next_prayer} at {next_time_12hr}. You will be pinged again in DM when it's time.", color=EMBED_COLOR)
                await interaction.user.send(embed=embed)

                # Inform the user that a DM has been sent
                await interaction.followup.send("You will be notified when it is the time for salah in your direct messages.", ephemeral=True)

                # Schedule the DM notification
                bot.loop.create_task(schedule_notification(interaction.user, next_time, next_prayer, user_timezone))
    else:
        await interaction.followup.send("Please set up your region using /setup first.", ephemeral=True)


async def schedule_notification(user, next_time, next_prayer, user_timezone):
    # Convert next_time to datetime object
    current_date = datetime.date.today()
    notify_time = datetime.datetime.strptime(next_time, '%H:%M').time()
    notify_datetime = datetime.datetime.combine(current_date, notify_time, user_timezone)

    # Calculate the delay until the notification time
    delay_seconds = (notify_datetime - datetime.datetime.now(user_timezone)).total_seconds()

    # If the delay is negative, it means the prayer time is for the next day
    if delay_seconds < 0:
        delay_seconds += 86400  # Add 24 hours in seconds

    # Wait until it's time to send the notification
    await asyncio.sleep(delay_seconds)

    # Send DM notification
    await user.send(f"It's time for {next_prayer} in {user_settings[str(user.id)]['city']}!")

@tasks.loop(minutes=1)
async def check_notifications():
    current_time = datetime.datetime.now(pytz.utc).strftime('%H:%M')
    for user_id, settings in user_settings.items():
        if "notifications" in settings and settings["notifications"]:
            user = await bot.fetch_user(int(user_id))
            for prayer, notify_time in settings["notifications"].items():
                if current_time == notify_time:
                    await user.send(f"It's time for {prayer} in {settings['city']}!")


bot.run(TOKEN)
