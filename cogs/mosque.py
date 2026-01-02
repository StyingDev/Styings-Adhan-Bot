import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import math
import asyncio
from typing import Dict, List, Optional

EMBED_COLOR = 0x757e8a

GEOCODING_API_URL = 'https://nominatim.openstreetmap.org/search'
OVERPASS_API_URL = 'http://overpass-api.de/api/interpreter'
USER_AGENT = 'Adhan-Bot/1.0'


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


class MosqueCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_searches: Dict[str, Dict] = {}
        self.PAGE_SIZE = 12

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} is online")

    def create_mosque_embed(self, query: str, radius_km: float, mosques_page: List[Dict], 
                           page: int, total_pages: int, total_mosques: int) -> discord.Embed:
        """Create an embed for a page of mosque results."""
        title = f"Mosques Near {query}"
        description = f"-# Found **{total_mosques}** mosques within **{radius_km}km** radius"
        
        embed = discord.Embed(title=title, description=description, color=EMBED_COLOR)
        
        # Add pagination info
        embed.add_field(name="Page", value=f"**{page}/{total_pages}**", inline=True)
        embed.add_field(name="Results per page", value=f"**{self.PAGE_SIZE}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        start_idx = (page - 1) * self.PAGE_SIZE

        for idx, m in enumerate(mosques_page, start=start_idx + 1):
            name = m['name']
            dist = m['distance_km']
            addr = (m['address'] or '').strip()
            lat = m['lat']
            lon = m['lon']
            osm_link = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"

            denom = m.get('denomination', '') or ''
            denom_text = f" ({denom})" if denom else ""

            field_name = f"{idx}. {name}{denom_text}"
            value_lines = [f"> {dist:.2f} km", f"-# [OpenStreetMap]({osm_link})"]
            if addr:
                addr_short = addr if len(addr) <= 120 else addr[:117] + "..."
                value_lines.append(addr_short)

            embed.add_field(name=field_name, value="\n > ".join(value_lines), inline=True)
        
        controls = []
        if page > 1:
            controls.append("Previous")
        if page < total_pages:
            controls.append("Next")

        embed.set_footer(text="🕌 Data: OpenStreetMap")
        
        return embed

    async def send_paginated_results(self, interaction: discord.Interaction, query: str, radius_km: float, 
                                   all_mosques: List[Dict], total_mosques: int, original_message: Optional[discord.Message] = None):
        """Send paginated results with navigation. If `original_message` is provided, edit it instead of sending a new followup."""
        total_pages = (len(all_mosques) + self.PAGE_SIZE - 1) // self.PAGE_SIZE
        
        # Store search data for this user
        user_id = str(interaction.user.id)
        self.user_searches[user_id] = {
            'query': query,
            'radius_km': radius_km,
            'all_mosques': all_mosques,
            'total_mosques': total_mosques,
            'current_page': 1,
            'total_pages': total_pages,
            'message_id': None
        }
        
        # Get first page
        start_idx = 0
        end_idx = min(self.PAGE_SIZE, len(all_mosques))
        page_mosques = all_mosques[start_idx:end_idx]
        
        embed = self.create_mosque_embed(query, radius_km, page_mosques, 1, total_pages, total_mosques)
        
        # Send or edit message with navigation buttons
        view = PaginationView(user_id, self)
        
        view.previous_button.disabled = True
        view.next_button.disabled = (total_pages <= 1)

        if original_message is not None:
            try:
                await original_message.edit(content=None, embed=embed, view=view)
                message = original_message
            except Exception:
                message = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            message = await interaction.followup.send(embed=embed, view=view, wait=True)
        
        # Store message ID
        self.user_searches[user_id]['message_id'] = message.id

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='mosque', description='Find mosques near a provided location (location is required).')
    @app_commands.describe(radius_km='Search radius in kilometers (max 50)', location='Location to search (required)')
    async def mosque(self, interaction: discord.Interaction, location: str, radius_km: float = 5.0):
        """Find nearest mosques using OpenStreetMap Overpass API with pagination. The `location` parameter is required."""
        await interaction.response.defer()

        # Validate radius
        radius_km = max(0.1, min(50.0, float(radius_km)))

        # Resolve starting coordinates (location is required)
        query = location.strip() if location and location.strip() else None
        if not query:
            await interaction.followup.send("Please provide a valid `location` to search.", ephemeral=True)
            return

        try:
            coords = await self.get_coordinates(query)
            if not coords:
                await interaction.followup.send(f"Could not geocode '{query}'. Try a different location.", ephemeral=True)
                return
            user_lat, user_lon = coords
        except Exception as e:
            await interaction.followup.send(f"Error resolving location: {e}", ephemeral=True)
            return

        # Query Overpass for mosques within radius
        radius_m = int(radius_km * 1000)
        overpass_query = f"""
[out:json][timeout:45];
(
  node["amenity"="place_of_worship"]["religion"="muslim"](around:{radius_m},{user_lat},{user_lon});
  node["building"="mosque"](around:{radius_m},{user_lat},{user_lon});
  node["amenity"="mosque"](around:{radius_m},{user_lat},{user_lon});
  way["amenity"="place_of_worship"]["religion"="muslim"](around:{radius_m},{user_lat},{user_lon});
  way["building"="mosque"](around:{radius_m},{user_lat},{user_lon});
  way["amenity"="mosque"](around:{radius_m},{user_lat},{user_lon});
);
(
  ._;
  >;
);
out center;
"""

        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
        
        processing_msg = await interaction.followup.send(f"Searching for mosques within {radius_km}km of **{query}**... This may take a moment.", ephemeral=False, wait=True)
        
        async def query_overpass_fallback():
            last_exc = None
            async with aiohttp.ClientSession() as session:
                endpoints = [
                    'https://overpass.kumi.systems/api/interpreter',
                    'https://lz4.overpass-api.de/api/interpreter',
                    'https://overpass.openstreetmap.fr/api/interpreter',
                    OVERPASS_API_URL
                ]
                
                for endpoint in endpoints:
                    for attempt in range(3):
                        try:
                            async with session.post(endpoint, data=overpass_query, headers=headers, timeout=90) as resp:
                                if resp.status == 200:
                                    return await resp.json()
                                if resp.status in (429, 502, 503, 504):
                                    last_exc = Exception(f"Overpass returned status {resp.status}")
                                else:
                                    text = await resp.text()
                                    raise Exception(f"Overpass returned status {resp.status}: {text[:200]}")
                        except asyncio.TimeoutError:
                            last_exc = Exception(f"Timeout querying {endpoint}")
                        except aiohttp.ClientError as exc:
                            last_exc = exc
                        await asyncio.sleep(2 ** attempt)
            raise last_exc or Exception("Overpass query failed for all endpoints")

        try:
            res = await query_overpass_fallback()
        except Exception as e:
            try:
                await processing_msg.edit(content=f"Error querying OpenStreetMap Overpass API: {e}. Try again later or reduce the radius.", embed=None, view=None)
            except Exception:
                await interaction.followup.send(f"Error querying OpenStreetMap Overpass API: {e}. Try again later or reduce the radius.", ephemeral=True)
            return

        elements = res.get('elements', [])
        
        if not elements:
            try:
                await processing_msg.edit(content=f"No mosques found within {radius_km} km of {query}.", embed=None, view=None)
            except Exception:
                await interaction.followup.send(f"No mosques found within {radius_km} km of {query}.", ephemeral=False)
            return

        # Process and deduplicate mosques
        mosques = []
        seen_coords = set()
        
        for el in elements:
            tags = el.get('tags', {})
            name = tags.get('name', 'Unnamed Mosque')
            
            # Get coordinates
            lat = None
            lon = None
            
            if el.get('type') == 'node' and 'lat' in el and 'lon' in el:
                lat = el['lat']
                lon = el['lon']
            elif el.get('center'):
                lat = el['center'].get('lat')
                lon = el['center'].get('lon')
            elif 'lat' in el and 'lon' in el:
                lat = el.get('lat')
                lon = el.get('lon')
            
            if lat is None or lon is None:
                continue
            
            coord_key = f"{round(lat, 6)},{round(lon, 6)}"
            if coord_key in seen_coords:
                continue
            seen_coords.add(coord_key)
            
            dist = haversine(user_lat, user_lon, lat, lon)
            
            # Build address
            addr_parts = []
            for k in ('addr:street', 'addr:housenumber', 'addr:city', 'addr:postcode', 'addr:country'):
                if tags.get(k):
                    addr_parts.append(tags.get(k))
            address = ", ".join(addr_parts) if addr_parts else tags.get('addr:full') or tags.get('description') or ''
            
            denomination = tags.get('denomination', '')
            
            mosques.append({
                'name': name,
                'lat': lat,
                'lon': lon,
                'distance_km': dist,
                'address': address,
                'denomination': denomination
            })
        
        mosques.sort(key=lambda x: x['distance_km'])
                
        await self.send_paginated_results(interaction, query, radius_km, mosques, len(elements), original_message=processing_msg)

    async def update_page(self, user_id: str, channel: discord.TextChannel, page: int):
        """Update the embed for a specific page."""
        if user_id not in self.user_searches:
            return False
        
        data = self.user_searches[user_id]
        
        if page < 1 or page > data['total_pages']:
            return False
        
        data['current_page'] = page
        
        start_idx = (page - 1) * self.PAGE_SIZE
        end_idx = min(start_idx + self.PAGE_SIZE, len(data['all_mosques']))
        page_mosques = data['all_mosques'][start_idx:end_idx]
        
        embed = self.create_mosque_embed(
            data['query'],
            data['radius_km'],
            page_mosques,
            page,
            data['total_pages'],
            data['total_mosques']
        )
        
        try:
            message = await channel.fetch_message(data['message_id'])
            view = PaginationView(user_id, self)
            view.previous_button.disabled = (page <= 1)
            view.next_button.disabled = (page >= data['total_pages'])
            await message.edit(embed=embed, view=view)
            return True
        except discord.NotFound:
            del self.user_searches[user_id]
            return False
        except Exception as e:
            print(f"Error updating page: {e}")
            return False

    async def cleanup_search(self, user_id: str):
        """Clean up search data for a user."""
        if user_id in self.user_searches:
            del self.user_searches[user_id]

    async def get_coordinates(self, query: str):
        params = {'q': query, 'format': 'json', 'limit': 1}
        headers = {'User-Agent': USER_AGENT}
        async with aiohttp.ClientSession() as session:
            async with session.get(GEOCODING_API_URL, params=params, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data and len(data) > 0:
                    return float(data[0]['lat']), float(data[0]['lon'])
                return None


class PaginationView(discord.ui.View):
    """View for pagination controls."""
    def __init__(self, user_id: str, cog: MosqueCog):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.cog = cog
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return str(interaction.user.id) == self.user_id
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.cog.user_searches.get(self.user_id)
        if not data:
            await interaction.response.send_message("This search session has expired.", ephemeral=True)
            return
        
        if data['current_page'] > 1:
            success = await self.cog.update_page(self.user_id, interaction.channel, data['current_page'] - 1)
            if success:
                await interaction.response.defer()
            else:
                await interaction.response.send_message("Failed to update page.", ephemeral=True)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.cog.user_searches.get(self.user_id)
        if not data:
            await interaction.response.send_message("This search session has expired.", ephemeral=True)
            return
        
        if data['current_page'] < data['total_pages']:
            success = await self.cog.update_page(self.user_id, interaction.channel, data['current_page'] + 1)
            if success:
                await interaction.response.defer()
            else:
                await interaction.response.send_message("Failed to update page.", ephemeral=True)
        else:
            await interaction.response.defer()
    
    
    async def on_timeout(self):
        await self.cog.cleanup_search(self.user_id)
        
        for child in self.children:
            child.disabled = True
        
        try:
            await self.message.edit(view=self)
        except:
            pass


async def setup(bot):
    await bot.add_cog(MosqueCog(bot))