import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import pytz
import datetime
import asyncio

ALADHAN_API_URL = 'http://api.aladhan.com/v1/timings'
EMBED_COLOR = 0x757e8a


def timings_url_and_params(settings, date_str):
    """Aladhan coordinate-endpoint URL and query params (aiohttp needs strings)."""
    return f"{ALADHAN_API_URL}/{date_str}", {
        'latitude': str(settings["latitude"]),
        'longitude': str(settings["longitude"]),
        'method': settings["calculation_method"],
        'school': settings["asr_method"],
        'timezonestring': settings["timezone"],
        'tune': '0,0,0,0,0,0,0,0,0',
    }

class NotificationsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.notification_tasks = {}
        self.loop_notifications = {}
        self.bot.loop.create_task(self.restore_notification_loops())

    def cog_unload(self):
        for task in self.notification_tasks.values():
            task.cancel()
        for user_id, task in self.loop_notifications.items():
            task.cancel()


    async def schedule_notification(self, user, next_time, next_prayer, user_timezone):
        current_date = datetime.datetime.now(user_timezone).date()
        notify_time = datetime.datetime.strptime(next_time, '%H:%M').time()

        notify_datetime = datetime.datetime.combine(current_date, notify_time).replace(tzinfo=user_timezone)

        current_time = datetime.datetime.now(user_timezone)

        delay_seconds = (notify_datetime - current_time).total_seconds()

        # A negative delay means the prayer time is for the next day
        if delay_seconds < 0:
            tomorrow = current_date + datetime.timedelta(days=1)
            notify_datetime = datetime.datetime.combine(tomorrow, notify_time).replace(tzinfo=user_timezone)
            delay_seconds = (notify_datetime - current_time).total_seconds()

        await asyncio.sleep(delay_seconds)

        await asyncio.sleep(120)

        settings = await self.bot.db.get_user(user.id)
        next_time_12hr = datetime.datetime.strptime(next_time, '%H:%M').strftime('%I:%M %p')
        await user.send(f"It's time for {next_prayer} in {settings['city']}! at {next_time_12hr}")


    async def notification_loop(self, user, user_timezone):
        """Continuously notify user of upcoming prayers"""
        user_id = str(user.id)

        try:
            while user_id in self.loop_notifications:
                settings = await self.bot.db.get_user(user_id)
                if not settings or settings["latitude"] is None:
                    break
                url, params = timings_url_and_params(settings, datetime.datetime.now(user_timezone).strftime('%d-%m-%Y'))

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as response:
                        data = await response.json()
                        timings = data.get('data', {}).get('timings', {})

                current_time = datetime.datetime.now(user_timezone)
                prayer_times = {}

                for prayer in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
                    if prayer in timings:
                        prayer_time = datetime.datetime.strptime(timings[prayer], '%H:%M').time()
                        prayer_datetime = datetime.datetime.combine(current_time.date(), prayer_time)
                        # API already returns times in the user's local timezone,
                        # so attach the tzinfo without converting
                        prayer_datetime = user_timezone.localize(prayer_datetime)

                        if prayer_datetime <= current_time:
                            prayer_datetime += datetime.timedelta(days=1)

                        prayer_times[prayer] = prayer_datetime

                if not prayer_times:
                    await asyncio.sleep(300)
                    continue

                next_prayer = min(prayer_times.items(), key=lambda x: x[1])
                next_prayer_name, next_prayer_time = next_prayer

                current_time = datetime.datetime.now(user_timezone)
                delay_seconds = (next_prayer_time - current_time).total_seconds()

                delay_seconds = max(0, delay_seconds)

                await asyncio.sleep(delay_seconds)

                # asyncio.sleep can wake early; wait out any remaining time
                current_time = datetime.datetime.now(user_timezone)
                time_diff = (next_prayer_time - current_time).total_seconds()

                if time_diff > 30:
                    print(f"Woke up {time_diff} seconds early, waiting additional time")
                    await asyncio.sleep(time_diff)

                if user_id in self.loop_notifications:

                    prayer_time_12hr = next_prayer_time.strftime('%I:%M %p')
                    await user.send(f"It's time for {next_prayer_name} in {settings['city']}! at {prayer_time_12hr}")
                    # Small delay after sending to prevent spam
                    await asyncio.sleep(1)

                    print(f"Sent {next_prayer_name} notification to {user.name} at {datetime.datetime.now(user_timezone).strftime('%H:%M:%S')}")

        except asyncio.CancelledError:
            if user_id in self.loop_notifications:
                del self.loop_notifications[user_id]


        except Exception as e:
            print(f"Error in notification loop for user {user_id}: {e}")
            try:
                await user.send("There was an error with your prayer notification loop. If notications are stoped in future try doing /notifyloop again.")
            except:
                pass

            # Wait and try again instead of ending the loop
            await asyncio.sleep(600)

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='notify', description='Reminds you when it is time for Fajr, Dhuhr, Asr, Maghrib and Isha.')
    async def notify(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        await interaction.response.defer(ephemeral=True)

        settings = await self.bot.db.get_user(user_id)
        if settings and settings["timezone"]:
            if settings["latitude"] is None:
                await interaction.followup.send("Your saved location needs a refresh, please run /setup again.", ephemeral=True)
                return
            url, params = timings_url_and_params(settings, datetime.datetime.now().strftime('%d-%m-%Y'))

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    timings = data.get('data', {}).get('timings', {})

                    user_timezone = pytz.timezone(settings["timezone"])
                    current_time = datetime.datetime.now(user_timezone)

                    prayer_times = {}

                    for prayer in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
                        if prayer in timings:
                            prayer_time = datetime.datetime.strptime(timings[prayer], '%H:%M').time()
                            prayer_datetime = datetime.datetime.combine(current_time.date(), prayer_time)
                            # API already returns times in the user's local timezone,
                            # so attach the tzinfo without converting
                            prayer_datetime = user_timezone.localize(prayer_datetime)

                            if prayer_datetime <= current_time:
                                prayer_datetime += datetime.timedelta(days=1)

                            prayer_times[prayer] = prayer_datetime

                    if not prayer_times:
                        embed = discord.Embed(title="Notification", description=f"Notification is only available for Fajr, Dhuhr, Asr, Maghrib and Isha. Please check your settings or try again later.", color=EMBED_COLOR)
                        await interaction.followup.send(embed=embed)
                        return

                    next_prayer = min(prayer_times.items(), key=lambda x: x[1])
                    next_prayer_name, next_prayer_time = next_prayer

                    next_time_12hr = next_prayer_time.strftime('%I:%M %p')

                    embed = discord.Embed(title="Notification Scheduled", description=f"Next upcoming salah for {settings['city']} is {next_prayer_name} at {next_time_12hr}. You will be pinged again in DM when it's time.", color=EMBED_COLOR)
                    await interaction.user.send(embed=embed)

                    try:
                        await interaction.followup.send("You will be notified when it is the time for salah in your direct messages.", ephemeral=True)
                    except discord.HTTPException as e:
                        if e.status == 429:
                            retry_after = int(e.response.headers.get('Retry-After', 1))
                            await asyncio.sleep(retry_after)
                            await interaction.followup.send("You will be notified when it is the time for salah in your direct messages.", ephemeral=True)

                    task = self.bot.loop.create_task(self.schedule_notification_datetime(interaction.user, next_prayer_time, next_prayer_name, user_timezone))
                    self.notification_tasks[user_id] = task
        else:
            await interaction.followup.send("Please set up your region using /setup first.", ephemeral=True)

    async def schedule_notification_datetime(self, user, notify_datetime, next_prayer, user_timezone):
        """Schedule notification using a datetime object instead of a time string"""
        try:
            current_time = datetime.datetime.now(user_timezone)

            delay_seconds = (notify_datetime - current_time).total_seconds()

            delay_seconds = max(0, delay_seconds)

            await asyncio.sleep(delay_seconds)


            settings = await self.bot.db.get_user(user.id)
            prayer_time_12hr = notify_datetime.strftime('%I:%M %p')
            await user.send(f"It's time for {next_prayer} in {settings['city']}! at {prayer_time_12hr}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in schedule_notification_datetime for user {user.id}: {e}")
            try:
                await user.send("There was an error with your prayer notification. Please try using /notify again.")
            except:
                pass


    def start_loop_for(self, user, settings):
        """Start the per-salah DM loop for a user unless one is already running.

        Shared by /notifyloop and the opt-in prompt at the end of /setup.
        """
        user_id = str(user.id)
        existing = self.loop_notifications.get(user_id)
        if existing and not existing.done():
            return
        user_timezone = pytz.timezone(settings["timezone"])
        self.loop_notifications[user_id] = self.bot.loop.create_task(self.notification_loop(user, user_timezone))

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='notifyloop', description='Set a notification chain for all upcoming salahs.')
    async def notifyloop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        await interaction.response.defer(ephemeral=True)

        if user_id in self.loop_notifications and not self.loop_notifications[user_id].done():
            await interaction.followup.send("You already have an active prayer notification loop. Use `/notifyloopstop` to stop it first.", ephemeral=True)
            return

        settings = await self.bot.db.get_user(user_id)
        if settings and settings["timezone"]:
            if settings["latitude"] is None:
                await interaction.followup.send("Your saved location needs a refresh, please run /setup again.", ephemeral=True)
                return
            self.start_loop_for(interaction.user, settings)

            await self.bot.db.update_user(user_id, notify_loop_active=True)

            embed = discord.Embed(
                title="Notification Loop Activated",
                description=f"You will now receive notifications for all upcoming salahs in {settings['city']}. Use `/notifyloopstop` to stop notifications.",
                color=EMBED_COLOR
            )
            await interaction.user.send(embed=embed)

            await interaction.followup.send("Prayer notification loop activated. You will be notified for all upcoming salahs in your direct messages.", ephemeral=True)
        else:
            await interaction.followup.send("Please set up your region using `/setup` first.", ephemeral=True)

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='notifyloopstop', description='Stop the notification chain for upcoming salahs.')
    async def notifyloopstop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        if user_id in self.loop_notifications and not self.loop_notifications[user_id].done():
            self.loop_notifications[user_id].cancel()

            await self.bot.db.update_user(user_id, notify_loop_active=False)

            await interaction.response.send_message("Prayer notification loop has been stopped.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have an active prayer notification loop.", ephemeral=True)

    async def restore_notification_loops(self):
        """Restore notification loops for users who had them active before restart"""
        await self.bot.wait_until_ready()

        for settings in await self.bot.db.get_notify_loop_users():
            user_id = settings["user_id"]
            try:
                user = await self.bot.fetch_user(int(user_id))
                if user and settings.get("timezone"):
                    user_timezone = pytz.timezone(settings["timezone"])

                    loop_task = self.bot.loop.create_task(self.notification_loop(user, user_timezone))
                    self.loop_notifications[user_id] = loop_task
            except Exception as e:
                print(f"Error restoring notification loop for user {user_id}: {e}")


async def setup(bot):
    await bot.add_cog(NotificationsCog(bot))
