import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import pytz
import datetime
import asyncio

# API URL
ALADHAN_API_URL = 'http://api.aladhan.com/v1/timingsByCity'

# Embed color
EMBED_COLOR = 0x757e8a

class NotificationsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_notifications.start()
        self.notification_tasks = {}
        self.loop_notifications = {}  # Store users with active notification loops
        self.bot.loop.create_task(self.restore_notification_loops())  # Restore loops on startup

    def cog_unload(self):
        self.check_notifications.cancel()
        for task in self.notification_tasks.values():
            task.cancel()
        # Cancel all loop notifications
        for user_id, task in self.loop_notifications.items():
            task.cancel()

    @tasks.loop(minutes=1)
    async def check_notifications(self):
        # This is a placeholder for any background notification checking
        pass

    @check_notifications.before_loop
    async def before_check_notifications(self):
        await self.bot.wait_until_ready()

    async def schedule_notification(self, user, next_time, next_prayer, user_timezone):
        # Convert next_time to datetime object
        current_date = datetime.datetime.now(user_timezone).date()
        notify_time = datetime.datetime.strptime(next_time, '%H:%M').time()
        
        # Create datetime with user's timezone
        notify_datetime = datetime.datetime.combine(current_date, notify_time).replace(tzinfo=user_timezone)
        
        # Get current time in user's timezone
        current_time = datetime.datetime.now(user_timezone)
        
        # Calculate the delay until the notification time
        delay_seconds = (notify_datetime - current_time).total_seconds()
        
        # If the delay is negative, it means the prayer time is for the next day
        if delay_seconds < 0:
            tomorrow = current_date + datetime.timedelta(days=1)
            notify_datetime = datetime.datetime.combine(tomorrow, notify_time).replace(tzinfo=user_timezone)
            delay_seconds = (notify_datetime - current_time).total_seconds()
        
        # Wait until it's time to send the notification
        await asyncio.sleep(delay_seconds)
        
        # Send DM notification (only once) with the time included
        next_time_12hr = datetime.datetime.strptime(next_time, '%H:%M').strftime('%I:%M %p')
        await user.send(f"It's time for {next_prayer} in {self.bot.user_settings[str(user.id)]['city']}! at {next_time_12hr}")


    async def notification_loop(self, user, user_timezone):
        """Continuously notify user of upcoming prayers"""
        user_id = str(user.id)
        
        try:
            while user_id in self.loop_notifications:
                # 1. Fetch fresh prayer times
                params = {
                    'city': self.bot.user_settings[user_id]["city"],
                    'country': self.bot.user_settings[user_id]["country"],
                    'method': self.bot.user_settings[user_id]["calculation_method"],
                    'timezone': self.bot.user_settings[user_id]["timezone"],
                    'school': self.bot.user_settings[user_id]["asr_method"],
                    'tune': '0,0,0,0,0,0,0,0,0'
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(ALADHAN_API_URL, params=params) as response:
                        data = await response.json()
                        timings = data.get('data', {}).get('timings', {})
                
                # 2. Prepare only the 5 daily prayers with datetime objects
                current_time = datetime.datetime.now(user_timezone)
                prayer_times = {}
                
                for prayer in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
                    if prayer in timings:
                        # Parse the time string from API correctly
                        prayer_time = datetime.datetime.strptime(timings[prayer], '%H:%M').time()
                        prayer_datetime = datetime.datetime.combine(current_time.date(), prayer_time)
                        prayer_datetime = prayer_datetime.replace(tzinfo=user_timezone)
                        
                        # If prayer time has passed today, schedule for tomorrow
                        if prayer_datetime <= current_time:
                            prayer_datetime += datetime.timedelta(days=1)
                        
                        prayer_times[prayer] = prayer_datetime

                if not prayer_times:
                    # No valid prayer times found, wait for 5 minutes before retrying
                    await asyncio.sleep(300)
                    continue

                # 3. Find the next prayer (closest future time)
                next_prayer = min(prayer_times.items(), key=lambda x: x[1])
                next_prayer_name, next_prayer_time = next_prayer
                
                # 4. Calculate delay (always positive since we handled past prayers above)
                delay_seconds = (next_prayer_time - current_time).total_seconds()
                
                # 5. Add a small buffer to prevent early notifications
                delay_seconds = max(0, delay_seconds)
                
                # 6. Sleep until next prayer
                await asyncio.sleep(delay_seconds)
                
                # 7. Send notification only if the loop is still active
                if user_id in self.loop_notifications:
                    # Format the time in 12-hour format for the message
                    prayer_time_12hr = next_prayer_time.strftime('%I:%M %p')
                    await user.send(f"It's time for {next_prayer_name} in {self.bot.user_settings[user_id]['city']}! at {prayer_time_12hr}")
                    # Add a small delay after sending to prevent spam
                    await asyncio.sleep(1)
                    
                    # Log the notification for debugging
                    print(f"Sent {next_prayer_name} notification to {user.name} at {datetime.datetime.now(user_timezone).strftime('%H:%M:%S')}")

        except asyncio.CancelledError:
            # Task was cancelled, clean up
            if user_id in self.loop_notifications:
                del self.loop_notifications[user_id]
            
            # Update user settings
            if user_id in self.bot.user_settings:
                self.bot.user_settings[user_id]["notify_loop_active"] = False
                await self.bot.save_settings()

        except Exception as e:
            print(f"Error in notification loop for user {user_id}: {e}")
            try:
                await user.send(f"There was an error with your prayer notification loop. Please use `/notifyloop` to restart it.")
            except:
                pass
            if user_id in self.loop_notifications:
                del self.loop_notifications[user_id]
            if user_id in self.bot.user_settings:
                self.bot.user_settings[user_id]["notify_loop_active"] = False
                await self.bot.save_settings()


    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='notify', description='Reminds you to pray two minutes before for Fajr, Dhuhr, Asr, Magrib and Isha.')
    async def notify(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # Defer the response to give more time for API calls
        await interaction.response.defer(ephemeral=True)

        if user_id in self.bot.user_settings and self.bot.user_settings[user_id]["timezone"]:
            params = {
                'city': self.bot.user_settings[user_id]["city"],
                'country': self.bot.user_settings[user_id]["country"],
                'method': self.bot.user_settings[user_id]["calculation_method"],
                'timezone': self.bot.user_settings[user_id]["timezone"],
                'school': self.bot.user_settings[user_id]["asr_method"]
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(ALADHAN_API_URL, params=params) as response:
                    data = await response.json()
                    timings = data.get('data', {}).get('timings', {})

                    # Convert timings to the user's local time
                    user_timezone = pytz.timezone(self.bot.user_settings[user_id]["timezone"])
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

                    embed = discord.Embed(title="Notification Scheduled", description=f"Next upcoming salah for {self.bot.user_settings[user_id]['city']} is {next_prayer} at {next_time_12hr}. You will be pinged again in DM when it's time.", color=EMBED_COLOR)
                    await interaction.user.send(embed=embed)

                    # Inform the user that a DM has been sent
                    try:
                        await interaction.followup.send("You will be notified when it is the time for salah in your direct messages.", ephemeral=True)
                    except discord.HTTPException as e:
                        if e.status == 429:  # Handle rate limiting
                            retry_after = int(e.response.headers.get('Retry-After', 1))
                            await asyncio.sleep(retry_after)
                            await interaction.followup.send("You will be notified when it is the time for salah in your direct messages.", ephemeral=True)

                    # Schedule the DM notification
                    task = self.bot.loop.create_task(self.schedule_notification(interaction.user, next_time, next_prayer, user_timezone))
                    self.notification_tasks[user_id] = task
        else:
            await interaction.followup.send("Please set up your region using /setup first.", ephemeral=True)
    
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='notifyloop', description='Set a notification chain for all upcoming salahs.')
    async def notifyloop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # Defer the response to give more time for API calls
        await interaction.response.defer(ephemeral=True)
        
        # Check if user already has an active notification loop
        if user_id in self.loop_notifications and not self.loop_notifications[user_id].done():
            await interaction.followup.send("You already have an active prayer notification loop. Use `/notifyloopstop` to stop it first.", ephemeral=True)
            return
            
        # Check if user has set up their region
        if user_id in self.bot.user_settings and self.bot.user_settings[user_id]["timezone"]:
            # Get user timezone
            user_timezone = pytz.timezone(self.bot.user_settings[user_id]["timezone"])
            
            # Start notification loop
            loop_task = self.bot.loop.create_task(self.notification_loop(interaction.user, user_timezone))
            self.loop_notifications[user_id] = loop_task
            
            # Update user settings to mark notification loop as active
            self.bot.user_settings[user_id]["notify_loop_active"] = True
            await self.bot.save_settings()
            
            # Send confirmation
            embed = discord.Embed(
                title="Notification Loop Activated", 
                description=f"You will now receive notifications for all upcoming salahs in {self.bot.user_settings[user_id]['city']}. Use `/notifyloopstop` to stop notifications.", 
                color=EMBED_COLOR
            )
            await interaction.user.send(embed=embed)
            
            # Inform the user that a DM has been sent
            await interaction.followup.send("Prayer notification loop activated. You will be notified for all upcoming salahs in your direct messages.", ephemeral=True)
        else:
            await interaction.followup.send("Please set up your region using `/setup` first.", ephemeral=True)
    
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='notifyloopstop', description='Stop the notification chain for upcoming salahs.')
    async def notifyloopstop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        if user_id in self.loop_notifications and not self.loop_notifications[user_id].done():
            # Cancel the notification loop task
            self.loop_notifications[user_id].cancel()
            
            # Update user settings to mark notification loop as inactive
            if user_id in self.bot.user_settings:
                self.bot.user_settings[user_id]["notify_loop_active"] = False
                await self.bot.save_settings()
            
            # Send confirmation
            await interaction.response.send_message("Prayer notification loop has been stopped.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have an active prayer notification loop.", ephemeral=True)

    async def restore_notification_loops(self):
        """Restore notification loops for users who had them active before restart"""
        await self.bot.wait_until_ready()
        
        for user_id, settings in self.bot.user_settings.items():
            # Check if the user had an active notification loop
            if settings.get("notify_loop_active", False):
                try:
                    # Get the user object
                    user = await self.bot.fetch_user(int(user_id))
                    if user and settings.get("timezone"):
                        # Get user timezone
                        user_timezone = pytz.timezone(settings["timezone"])
                        
                        # Start notification loop
                        loop_task = self.bot.loop.create_task(self.notification_loop(user, user_timezone))
                        self.loop_notifications[user_id] = loop_task
                        
                        # Inform user that their notification loop has been restored
                        try:
                            embed = discord.Embed(
                                title="Notification Loop Restored", 
                                description=f"Your prayer notification loop has been restored after bot restart.\n\n Apologies if there was any missed prayer notification during this downtime. We don't have a reliable hosting provider to ensure 100% uptime.\n There are also times API is ratelimited you will not be responded.\n\nWe apologize for any inconvenience caused.", 
                                color=EMBED_COLOR
                            )
                            await user.send(embed=embed)
                        except:
                            # Unable to send DM, but continue with the loop
                            pass
                except Exception as e:
                    print(f"Error restoring notification loop for user {user_id}: {e}")


async def setup(bot):
    await bot.add_cog(NotificationsCog(bot))
