import discord
from discord.ext import commands
from discord import app_commands
import math
import aiohttp

# Embed color
EMBED_COLOR = 0x757e8a

# Coordinates of the Kaaba in Mecca
KAABA_LAT = 21.4225
KAABA_LONG = 39.8262

# API for geocoding (converting city/country to coordinates)
GEOCODING_API_URL = 'https://nominatim.openstreetmap.org/search'

class QiblaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} is online")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='qibla', description='Get the Qibla direction from your location')
    async def qibla(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # Defer the response to give more time for API calls
        await interaction.response.defer(ephemeral=True)
        
        if user_id in self.bot.user_settings and self.bot.user_settings[user_id]["city"] and self.bot.user_settings[user_id]["country"]:
            city = self.bot.user_settings[user_id]["city"]
            country = self.bot.user_settings[user_id]["country"]
            
            # Get coordinates for the user's location
            try:
                coordinates = await self.get_coordinates(city, country)
                if coordinates:
                    user_lat, user_long = coordinates
                    
                    # Calculate qibla direction
                    qibla_direction = self.calculate_qibla(user_lat, user_long)
                    
                    # Create compass direction
                    compass_direction = self.get_compass_direction(qibla_direction)
                    
                    # Create embed response
                    embed = discord.Embed(
                        title="Qibla Direction", 
                        description=f"From {city}, {country} to the Kaaba in Mecca:", 
                        color=EMBED_COLOR
                    )
                    embed.add_field(name="Direction", value=f"{qibla_direction:.1f}° ({compass_direction})", inline=False)
                    embed.add_field(name="How to use", value="Use a compass app on your phone and face this direction to pray towards the Kaaba.", inline=False)
                    embed.set_footer(text="🕋 Data provided by OpenStreetMap")
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"Could not find coordinates for {city}, {country}. Please check your region settings.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"Error calculating Qibla direction: {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send("Please set up your region using /setup first.", ephemeral=True)
    
    async def get_coordinates(self, city, country):
        """Get latitude and longitude for a city and country"""
        params = {
            'q': f"{city}, {country}",
            'format': 'json',
            'limit': 1
        }
        
        headers = {
            'User-Agent': 'Adhan-Bot/1.0'  # Required by Nominatim API
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(GEOCODING_API_URL, params=params, headers=headers) as response:
                data = await response.json()
                
                if data and len(data) > 0:
                    lat = float(data[0]['lat'])
                    lon = float(data[0]['lon'])
                    return lat, lon
                return None
    
    def calculate_qibla(self, lat, long):
        """Calculate Qibla direction in degrees from North"""
        # Convert to radians
        lat_rad = math.radians(lat)
        long_rad = math.radians(long)
        kaaba_lat_rad = math.radians(KAABA_LAT)
        kaaba_long_rad = math.radians(KAABA_LONG)
        
        # Calculate qibla direction
        y = math.sin(kaaba_long_rad - long_rad)
        x = math.cos(lat_rad) * math.tan(kaaba_lat_rad) - math.sin(lat_rad) * math.cos(kaaba_long_rad - long_rad)
        qibla = math.atan2(y, x)
        
        # Convert to degrees and normalize to 0-360
        qibla_deg = math.degrees(qibla)
        qibla_deg = (qibla_deg + 360) % 360
        
        return qibla_deg
    
    def get_compass_direction(self, degrees):
        """Convert degrees to compass direction"""
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
                      "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        
        index = round(degrees / 22.5) % 16
        return directions[index]


async def setup(bot):
    await bot.add_cog(QiblaCog(bot))