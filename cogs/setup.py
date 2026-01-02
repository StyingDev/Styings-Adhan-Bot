import discord
from discord.ext import commands
from discord import app_commands
import json
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

# Default values
DEFAULT_ASR_METHOD = '1'
DEFAULT_CALC_METHOD = '2'

geolocator = Nominatim(user_agent="discord_prayer_bot")
tf = TimezoneFinder()

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

# Embed color
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
        self.view.bot.user_settings[user_id]["asr_method"] = self.values[0]
        await self.view.bot.save_settings()
        
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
        self.view.bot.user_settings[user_id]["calculation_method"] = self.values[0]
        await self.view.bot.save_settings()
        
        await interaction.response.edit_message(
            content="Setup complete! Your settings have been saved.",
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
        
        user_id = str(interaction.user.id)
        location_query = f"{self.city.value}, {self.country.value}"
        
        try:
            
            location = geolocator.geocode(location_query)
            
            if location:
                
                timezone_str = tf.timezone_at(lng=location.longitude, lat=location.latitude)
            else:
                timezone_str = "UTC"  # Fallback
                
        except Exception as e:
            print(f"Error detecting timezone: {e}")
            timezone_str = "UTC"

        self.bot.user_settings[user_id] = {
            "country": self.country.value,
            "city": self.city.value,
            "timezone": timezone_str,
            "asr_method": DEFAULT_ASR_METHOD,
            "calculation_method": DEFAULT_CALC_METHOD
        }
        await self.bot.save_settings()

        await interaction.followup.send(
            f"Detected Timezone: **{timezone_str}**\n-# if this timezone is **incorrect** do /setup again with proper location names.\n-# This is important for /notify commands.\n\nNow, please select your Asr timing method:",
            view=AsrMethodView(self.bot),
            ephemeral=True
        )


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
    @app_commands.command(name='region', description='View your current set region and timezone.')
    async def region(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id in self.bot.user_settings:
            country = self.bot.user_settings[user_id]["country"]
            city = self.bot.user_settings[user_id]["city"]
            timezone = self.bot.user_settings[user_id]["timezone"]
            asr_method = "Hanafi juristic (Recommended)" if self.bot.user_settings[user_id]["asr_method"] == '1' else "Standard (Shafi'i, Maliki, and Hanbali)"
            calc_method = calculation_methods[self.bot.user_settings[user_id]["calculation_method"]]
            embed = discord.Embed(title="Current Region Settings", description=f"Country: {country}\nCity: {city}\nTimezone: {timezone}\nAsr Method: {asr_method}\nCalculation Method: {calc_method}", color=EMBED_COLOR)
            embed.set_footer(text="⚙️ To change your preferences do /setup")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Please set up your region using /setup first.")


async def setup(bot):
    await bot.add_cog(SetupCog(bot))