import discord
from discord.ext import commands
import json
import os
import aiohttp
import pytz
import datetime
import asyncio

intents = discord.Intents.all()
intents.message_content = True

TOKEN = 'Your_token_here'
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

# Load user settings from JSON file
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump({}, f)

with open(SETTINGS_FILE, 'r') as f:
    user_settings = json.load(f)


# Rest of your code remains unchanged

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
        embed = discord.Embed(title="Timezone Set", description=f"Your timezone has been set to {self.values[0]}", color=EMBED_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TimeZoneView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(TimeZoneSelect())


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="🌲linktr.ee/Stying"))
    await bot.tree.sync()
    print(f'We have logged in as {bot.user.name}')


bot.remove_command("help")

@bot.hybrid_command(name='help', help='Execute for help.')
async def help(ctx):
    embed = discord.Embed(title="Adhan Bot Help", description="Here are the available commands for the Adhan Bot:", color=EMBED_COLOR)

    embed.add_field(name="/setup", value="Set up your region settings (country, city, and timezone).", inline=False)
    embed.add_field(name="/region", value="View your current region settings.", inline=False)
    embed.add_field(name="/upcoming", value="Get the upcoming salah time for your region.", inline=False)
    embed.add_field(name="/timings", value="Get all the salah timings for your region.", inline=False)
    embed.add_field(name="/notify", value="Schedule a DM notification for the next salah time.", inline=False)

    await ctx.send(embed=embed)


@bot.hybrid_command(name='setup', help='Setup your region and timezone.')
async def setup(ctx):
    await ctx.send("Please enter your country:")
    country_msg = await bot.wait_for('message', check=lambda m: m.author == ctx.author)

    await ctx.send("Please enter your city:")
    city_msg = await bot.wait_for('message', check=lambda m: m.author == ctx.author)

    await ctx.send("Please select your timezone:", view=TimeZoneView())

    user_id = str(ctx.author.id)
    user_settings[user_id] = {
        "country": country_msg.content,
        "city": city_msg.content,
        "timezone": None
    }
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(user_settings, f)


@bot.hybrid_command(name='region', help='View your current set region and timezone.')
async def region(ctx):
    user_id = str(ctx.author.id)
    if user_id in user_settings:
        country = user_settings[user_id]["country"]
        city = user_settings[user_id]["city"]
        timezone = user_settings[user_id]["timezone"]
        embed = discord.Embed(title="Current Region Settings", description=f"Country: {country}\nCity: {city}\nTimezone: {timezone}", color=EMBED_COLOR)
        await ctx.send(embed=embed)
    else:
        await ctx.send("Please set up your region using A!setup first.")


@bot.hybrid_command(name='upcoming', help='View your upcoming prayer time.')
async def upcoming(ctx):
    user_id = str(ctx.author.id)

    if user_id in user_settings and user_settings[user_id]["timezone"]:
        params = {
            'city': user_settings[user_id]["city"],
            'country': user_settings[user_id]["country"],
            'method': '2',
            'timezone': user_settings[user_id]["timezone"]
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
                    embed = discord.Embed(title="Upcoming Salah", description=f"All prayer times for {user_settings[user_id]['city']} have passed for today.", color=EMBED_COLOR)
                    await ctx.send(embed=embed)
                    return

                next_prayer = min(formatted_timings, key=lambda x: formatted_timings[x] if current_time.strftime('%H:%M') < formatted_timings[x] else '23:59')
                next_time = formatted_timings[next_prayer]

                # Convert next_time to 12-hour format
                next_time_12hr = datetime.datetime.strptime(next_time, '%H:%M').strftime('%I:%M %p')

                embed = discord.Embed(title="Next Upcoming Salah", description=f"Next upcoming salah for {user_settings[user_id]['city']} is {next_prayer} at {next_time_12hr}.", color=EMBED_COLOR)
                await ctx.send(embed=embed)
    else:
        await ctx.send("Please set up your region using A!setup first.")


@bot.hybrid_command(name='timings', help='Lists all Prayer timings in your region')
async def timings(ctx):
    user_id = str(ctx.author.id)

    if user_id in user_settings and user_settings[user_id]["timezone"]:
        params = {
            'city': user_settings[user_id]["city"],
            'country': user_settings[user_id]["country"],
            'method': '2',
            'timezone': user_settings[user_id]["timezone"]
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
                    await ctx.send(embed=embed)
                    return

                prayer_order = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
                timings_to_display = {prayer: formatted_timings[prayer] for prayer in prayer_order if prayer in formatted_timings}

                # Convert timings to 12-hour format
                timings_12hr = {prayer: datetime.datetime.strptime(time, '%H:%M').strftime('%I:%M %p') for prayer, time in timings_to_display.items()}

                description = "\n".join([f"{prayer}: {time}" for prayer, time in timings_12hr.items()])
                embed = discord.Embed(title="Adhan Timings", description=description, color=EMBED_COLOR)
                await ctx.send(embed=embed)
    else:
        await ctx.send("Please set up your region using A!setup first.")


@bot.hybrid_command(name='notify', help='Reminds you to pray for your upcoming salah.')
async def notify(ctx):
    user_id = str(ctx.author.id)

    if user_id in user_settings and user_settings[user_id]["timezone"]:
        params = {
            'city': user_settings[user_id]["city"],
            'country': user_settings[user_id]["country"],
            'method': '2',
            'timezone': user_settings[user_id]["timezone"]
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
                    embed = discord.Embed(title="Notification", description=f"All prayer times for {user_settings[user_id]['city']} have passed for today.", color=EMBED_COLOR)
                    await ctx.author.send(embed=embed)
                    return

                next_prayer = min(formatted_timings, key=lambda x: formatted_timings[x] if current_time.strftime('%H:%M') < formatted_timings[x] else '23:59')
                next_time = formatted_timings[next_prayer]

                # Convert next_time to 12-hour format
                next_time_12hr = datetime.datetime.strptime(next_time, '%H:%M').strftime('%I:%M %p')

                embed = discord.Embed(title="Notification Scheduled", description=f"Next upcoming salah for {user_settings[user_id]['city']} is {next_prayer} at {next_time_12hr}. You will be pinged again in DM when it's time.", color=EMBED_COLOR)
                await ctx.author.send(embed=embed)
                
                # Inform the user that a DM has been sent
                await ctx.send("You have been sent a DM with further details.")

                # Schedule the DM notification
                await schedule_notification(ctx.author, next_time, next_prayer)
    else:
        await ctx.author.send("Please set up your region using A!setup first.")


async def schedule_notification(user, next_time, next_prayer):
    # Convert next_time to datetime object
    current_date = datetime.date.today()
    notify_time = datetime.datetime.strptime(next_time, '%H:%M')
    notify_datetime = datetime.datetime.combine(current_date, notify_time.time())

    # Wait until it's time to send the notification
    await asyncio.sleep((notify_datetime - datetime.datetime.now()).seconds)

    # Send DM notification
    await user.send(f"It's time for {next_prayer} in {user_settings[str(user.id)]['city']}!")


bot.run(TOKEN)
