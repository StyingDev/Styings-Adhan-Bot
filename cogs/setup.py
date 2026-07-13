import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

DEFAULT_ASR_METHOD = '1'
DEFAULT_CALC_METHOD = '2'

geolocator = Nominatim(user_agent="discord_prayer_bot")
tf = TimezoneFinder()


async def geocode_location(city: str, country: str):
    """Resolve free-text city/country to canonical names, timezone and coordinates.

    Returns None when the location can't be found - callers must not save
    anything in that case. Runs in a thread because geopy is blocking.
    """
    location = await asyncio.to_thread(
        geolocator.geocode, f"{city}, {country}",
        addressdetails=True, language='en',
    )
    if not location:
        return None
    address = location.raw.get('address', {})
    return {
        'city': address.get('city') or address.get('town') or address.get('village')
                or address.get('municipality') or address.get('county') or city,
        'country': address.get('country') or country,
        'timezone': tf.timezone_at(lng=location.longitude, lat=location.latitude) or "UTC",
        'latitude': location.latitude,
        'longitude': location.longitude,
    }

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

EMBED_COLOR = 0x757e8a


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
        await self.view.bot.db.update_user(user_id, asr_method=self.values[0])

        await interaction.response.edit_message(
            content="Asr timing method set. Now, please select your calculation method:",
            view=CalculationMethodView(self.view.bot)
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
        await self.view.bot.db.update_user(user_id, calculation_method=self.values[0])

        await interaction.response.edit_message(
            content="Calculation method set. One last thing, do you want a DM at every salah time?",
            view=NotifyPromptView(self.view.bot),
        )


class NotifyPromptView(discord.ui.View):
    """Final step of /setup: opt in to the per-salah notification loop."""

    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @discord.ui.button(label="Yes, notify me", style=discord.ButtonStyle.success)
    async def enable(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        settings = await self.bot.db.get_user(user_id)
        notifications = self.bot.get_cog("NotificationsCog")

        if settings and notifications:
            notifications.start_loop_for(interaction.user, settings)
            await self.bot.db.update_user(user_id, notify_loop_active=True)
            await interaction.response.edit_message(
                content=f"Setup complete! You'll receive a DM at every salah time for {settings['city']}. Use /notifyloopstop anytime to turn this off.",
                view=None,
            )
        else:
            await interaction.response.edit_message(
                content="Setup complete! Notifications couldn't be enabled automatically — use /notifyloop to turn them on.",
                view=None,
            )

    @discord.ui.button(label="No thanks", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        notifications = self.bot.get_cog("NotificationsCog")
        if notifications:
            existing = notifications.loop_notifications.get(str(interaction.user.id))
            if existing and not existing.done():
                existing.cancel()
        await interaction.response.edit_message(
            content="Setup complete! Your settings have been saved. You can enable per-salah DMs anytime with /notifyloop.",
            view=None,
        )


class AsrMethodView(discord.ui.View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.add_item(AsrMethodSelect())


class CalculationMethodView(discord.ui.View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.add_item(CalculationMethodSelect())


class ConfirmRegionView(discord.ui.View):
    """Shows the geocoder's canonical result and only saves on confirmation."""

    def __init__(self, bot, pending: dict, in_setup: bool, settings_view=None):
        super().__init__(timeout=180)
        self.bot = bot
        self.pending = pending
        self.in_setup = in_setup
        self.settings_view = settings_view

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = self.pending
        if self.in_setup:
            await self.bot.db.upsert_user(
                interaction.user.id,
                country=p['country'],
                city=p['city'],
                timezone=p['timezone'],
                latitude=p['latitude'],
                longitude=p['longitude'],
                asr_method=DEFAULT_ASR_METHOD,
                calculation_method=DEFAULT_CALC_METHOD,
            )
            await interaction.response.edit_message(
                content=f"Region saved as **{p['city']}, {p['country']}**. Now, please select your Asr timing method:",
                view=AsrMethodView(self.bot),
            )
        else:
            await self.bot.db.update_user(
                interaction.user.id,
                country=p['country'],
                city=p['city'],
                timezone=p['timezone'],
                latitude=p['latitude'],
                longitude=p['longitude'],
            )
            await interaction.response.edit_message(
                content=f"Region updated to **{p['city']}, {p['country']}**.",
                view=None,
            )
            if self.settings_view and self.settings_view.message:
                settings = await self.bot.db.get_user(interaction.user.id)
                view = SettingsView(self.bot, settings)
                view.message = self.settings_view.message
                try:
                    await self.settings_view.message.edit(embed=build_settings_embed(settings), view=view)
                except discord.HTTPException:
                    pass

    @discord.ui.button(label="Try Again", style=discord.ButtonStyle.secondary)
    async def try_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.in_setup:
            await interaction.response.send_modal(SetupModal(self.bot))
        else:
            settings = await self.bot.db.get_user(interaction.user.id)
            await interaction.response.send_modal(RegionEditModal(self.bot, self.settings_view, settings))


class SetupModal(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Setup Your Region")
        self.bot = bot
        self.country = discord.ui.TextInput(label="Country", placeholder="Ex: Turkey", required=True)
        self.city = discord.ui.TextInput(label="City", placeholder="Ex: Istanbul", required=True)

        self.add_item(self.country)
        self.add_item(self.city)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            result = await geocode_location(self.city.value, self.country.value)
        except Exception as e:
            print(f"Error geocoding location: {e}")
            result = None

        if not result:
            await interaction.followup.send(
                f"Couldn't find **{self.city.value}, {self.country.value}** - nothing was saved. Please run /setup again and double-check the spelling.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Did you mean: **{result['city']}, {result['country']}**?\nDetected timezone: **{result['timezone']}**\n-# This is important for /notify commands.",
            view=ConfirmRegionView(self.bot, result, in_setup=True),
            ephemeral=True,
        )


def asr_method_label(value: str) -> str:
    return "Hanafi juristic (Recommended)" if value == '1' else "Standard (Shafi'i, Maliki, and Hanbali)"


def build_settings_embed(settings) -> discord.Embed:
    embed = discord.Embed(
        title="Your Settings",
        description=(
            f"Country: {settings['country']}\n"
            f"City: {settings['city']}\n"
            f"Timezone: {settings['timezone']}\n"
            f"Asr Method: {asr_method_label(settings['asr_method'])}\n"
            f"Calculation Method: {calculation_methods.get(settings['calculation_method'], 'Unknown')}"
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="⚙️ Edit any setting below")
    return embed


class SettingsAsrSelect(discord.ui.Select):
    def __init__(self, current: str):
        options = [
            discord.SelectOption(label="Hanafi juristic (Recommended)", value='1', default=current == '1'),
            discord.SelectOption(label="Standard (Shafi'i, Maliki, and Hanbali)", value='0', default=current == '0'),
        ]
        super().__init__(placeholder="Change Asr timing method", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await self.view.bot.db.update_user(interaction.user.id, asr_method=self.values[0])
        await self.view.refresh(interaction)


class SettingsCalcSelect(discord.ui.Select):
    def __init__(self, current: str):
        options = [
            discord.SelectOption(label=name, value=key, default=key == current)
            for key, name in calculation_methods.items()
        ]
        super().__init__(placeholder="Change calculation method", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        await self.view.bot.db.update_user(interaction.user.id, calculation_method=self.values[0])
        await self.view.refresh(interaction)


class RegionEditModal(discord.ui.Modal):
    def __init__(self, bot, settings_view, settings):
        super().__init__(title="Edit Your Region")
        self.bot = bot
        self.settings_view = settings_view
        self.country = discord.ui.TextInput(label="Country", default=settings['country'], required=True)
        self.city = discord.ui.TextInput(label="City", default=settings['city'], required=True)
        self.add_item(self.country)
        self.add_item(self.city)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            result = await geocode_location(self.city.value, self.country.value)
        except Exception as e:
            print(f"Error geocoding location: {e}")
            result = None

        if not result:
            await interaction.followup.send(
                f"Couldn't find **{self.city.value}, {self.country.value}** - settings unchanged. Try again with different spelling.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Did you mean: **{result['city']}, {result['country']}**?\nDetected timezone: **{result['timezone']}**",
            view=ConfirmRegionView(self.bot, result, in_setup=False, settings_view=self.settings_view),
            ephemeral=True,
        )


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, bot, settings_view):
        super().__init__(timeout=60)
        self.bot = bot
        self.settings_view = settings_view

    @discord.ui.button(label="Yes, delete everything", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.db.delete_user(interaction.user.id)
        await interaction.response.edit_message(
            content="Your data has been deleted. Notifications will stop shortly. Use /setup anytime to start again.",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await self.bot.db.get_user(interaction.user.id)
        view = SettingsView(self.bot, settings)
        view.message = self.settings_view.message
        await interaction.response.edit_message(content=None, embed=build_settings_embed(settings), view=view)


class SettingsView(discord.ui.View):
    def __init__(self, bot, settings):
        super().__init__(timeout=300)
        self.bot = bot
        self.message = None
        self.add_item(SettingsAsrSelect(settings['asr_method']))
        self.add_item(SettingsCalcSelect(settings['calculation_method']))

    async def refresh(self, interaction: discord.Interaction):
        """Re-render the panel with fresh settings and dropdown defaults."""
        settings = await self.bot.db.get_user(interaction.user.id)
        view = SettingsView(self.bot, settings)
        view.message = self.message
        embed = build_settings_embed(settings)
        if interaction.response.is_done():
            if self.message:
                await self.message.edit(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Edit Region", style=discord.ButtonStyle.primary, row=2)
    async def edit_region(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await self.bot.db.get_user(interaction.user.id)
        await interaction.response.send_modal(RegionEditModal(self.bot, self, settings))

    @discord.ui.button(label="Delete My Data", style=discord.ButtonStyle.danger, row=2)
    async def delete_data(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="**Are you sure?** This deletes your region, preferences, and stops all prayer notifications.",
            embed=None,
            view=ConfirmDeleteView(self.bot, self),
        )

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} is online")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='setup', description='Setup your region, timezone, and Asr timing method.')
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SetupModal(self.bot))

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='settings', description='View and edit your region, timezone, Asr method, and calculation method.')
    async def settings(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_user(interaction.user.id)
        if settings:
            view = SettingsView(self.bot, settings)
            await interaction.response.send_message(embed=build_settings_embed(settings), view=view, ephemeral=True)
            view.message = await interaction.original_response()
        else:
            await interaction.response.send_message("Please set up your region using /setup first.")


async def setup(bot):
    await bot.add_cog(SetupCog(bot))