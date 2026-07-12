import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import math
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

EMBED_COLOR = 0x757e8a

GEOCODING_API_URL = 'https://nominatim.openstreetmap.org/search'
# Ordered by measured reliability: kumi hangs until timeout and .fr is
# whitelist-only, so they are last-resort fallbacks
OVERPASS_ENDPOINTS = [
    'https://lz4.overpass-api.de/api/interpreter',
    'http://overpass-api.de/api/interpreter',
    'https://overpass.openstreetmap.fr/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]
USER_AGENT = 'Adhan-Bot/1.0'
PAGE_SIZE = 10
OVERPASS_TIMEOUT = 30

MAX_RESULTS = 300
CACHE_TTL = 6 * 3600
CACHE_MAX_ENTRIES = 128


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def format_distance(km: float) -> str:
    if km < 1:
        return f"{km * 1000:.0f} m"
    return f"{km:.2f} km"


class PaginationView(discord.ui.View):
    """Self-contained paginator: holds the result list and current page,
    so concurrent searches by the same user can't clobber each other."""

    def __init__(self, user_id: str, query: str, radius_km: float, mosques: List[Dict], note: str = ''):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.query = query
        self.radius_km = radius_km
        self.mosques = mosques
        self.note = note
        self.page = 1
        self.total_pages = (len(mosques) + PAGE_SIZE - 1) // PAGE_SIZE
        self.message: Optional[discord.Message] = None
        self._update_buttons()

    def _update_buttons(self):
        self.previous_button.disabled = (self.page <= 1)
        self.next_button.disabled = (self.page >= self.total_pages)
        self.page_indicator.label = f"Page {self.page}/{self.total_pages}"

    def build_embed(self) -> discord.Embed:
        start_idx = (self.page - 1) * PAGE_SIZE
        lines = [f"Found **{len(self.mosques)}** mosques within **{self.radius_km:g}km** radius"]
        if self.note:
            lines.append(f"*{self.note}*")
        lines.append("")

        for idx, m in enumerate(self.mosques[start_idx:start_idx + PAGE_SIZE], start=start_idx + 1):
            lat, lon = m['lat'], m['lon']
            if m['name'] != 'Unnamed Mosque':
                # Search by name near the coordinates so Google resolves the
                # actual place card instead of dropping a bare pin
                google_maps_link = f"https://www.google.com/maps/search/{quote(m['name'], safe='')}/@{lat},{lon},18z"
            else:
                google_maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            osm_link = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
            # Brackets in a name would break the markdown link label
            name = m['name'].replace('[', '(').replace(']', ')')

            entry = f"**{idx}. [{name}]({google_maps_link})** ➔ {format_distance(m['distance_km'])} · [OSM]({osm_link})"
            if m['address']:
                entry += f"\n{m['address'][:100]}"
            lines.append(entry)

        embed = discord.Embed(
            title=f"Mosques Near {self.query}",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"Data: OpenStreetMap | Mosque names link to Google Maps")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Only the person who ran the search can change pages.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(1, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # Always disabled; exists only to show the page count

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.total_pages, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class MosqueCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        # (lat, lon, radius) -> (expires_at, (mosques, effective_radius))
        self.search_cache: Dict[Tuple, Tuple] = {}
        self.preferred_endpoint = OVERPASS_ENDPOINTS[0]

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={'User-Agent': USER_AGENT})

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} is online")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='mosque', description='Find mosques near a location (defaults to your /setup region).')
    @app_commands.describe(location='Location to search (defaults to your saved region)', radius_km='Search radius in kilometers (max 50)')
    async def mosque(self, interaction: discord.Interaction, location: Optional[str] = None, radius_km: float = 5.0):
        await interaction.response.defer()

        radius_km = max(0.1, min(50.0, float(radius_km)))

        coords = None
        query = location.strip() if location and location.strip() else None
        if not query:
            settings = await self.bot.db.get_user(interaction.user.id)
            if settings:
                query = f"{settings['city']}, {settings['country']}"
                if settings['latitude'] is not None:
                    coords = (settings['latitude'], settings['longitude'])
            else:
                await interaction.edit_original_response(content="Please provide a `location`, or save your region with `/setup` first.")
                return

        # Saved regions come with stored coordinates; only explicit locations
        # (or pre-coordinate rows) need geocoding
        if coords is None:
            try:
                coords = await self.get_coordinates(query)
            except Exception as e:
                await interaction.edit_original_response(content=f"Error resolving location: {e}")
                return
            if not coords:
                await interaction.edit_original_response(content=f"Could not geocode '{query}'. Try a different location.")
                return
        user_lat, user_lon = coords

        await interaction.edit_original_response(content=f"Searching for mosques within {radius_km:g}km of **{query}**... This may take a moment.")

        cache_key = (round(user_lat, 3), round(user_lon, 3), round(radius_km, 1))
        cached = self.cache_get(cache_key)
        if cached:
            mosques, effective_radius = cached
        else:
            try:
                effective_radius = await self.fit_radius(user_lat, user_lon, radius_km)
                res = await self.query_overpass(self.build_overpass_query(user_lat, user_lon, effective_radius, f"out center {MAX_RESULTS};"))
            except Exception as e:
                await interaction.edit_original_response(content=f"Error querying OpenStreetMap Overpass API: {e}. Try again later or reduce the radius.")
                return

            mosques = self.parse_mosques(res.get('elements', []), user_lat, user_lon)
            self.cache_put(cache_key, (mosques, effective_radius))

        if not mosques:
            await interaction.edit_original_response(content=f"No mosques found within {radius_km:g} km of {query}.")
            return

        note = ''
        if effective_radius < radius_km:
            note = f"Radius reduced from {radius_km:g}km, this area has a very high mosque density"

        view = PaginationView(str(interaction.user.id), query, effective_radius, mosques, note)
        view.message = await interaction.edit_original_response(content=None, embed=view.build_embed(), view=view)

    @staticmethod
    def build_overpass_query(lat: float, lon: float, radius_km: float, out_statement: str) -> str:
        radius_m = int(radius_km * 1000)
        return f"""
[out:json][timeout:{OVERPASS_TIMEOUT}];
(
  nwr["amenity"="place_of_worship"]["religion"="muslim"](around:{radius_m},{lat},{lon});
  nwr["building"="mosque"](around:{radius_m},{lat},{lon});
  nwr["amenity"="mosque"](around:{radius_m},{lat},{lon});
);
{out_statement}
"""

    async def fit_radius(self, lat: float, lon: float, radius_km: float) -> float:
        """Shrink the radius in one shot if the area is too dense.

        "out count" is much cheaper than fetching elements, and a single count
        keeps us at 2 Overpass round trips total - rapid consecutive queries
        trip the mirrors' rate limits. The fetch cap catches any undershoot.
        """
        try:
            res = await self.query_overpass(self.build_overpass_query(lat, lon, radius_km, "out count;"))
            count = int(res['elements'][0]['tags']['total'])
        except Exception:
            return radius_km
        if count > MAX_RESULTS:
            radius_km = max(0.5, radius_km * math.sqrt(MAX_RESULTS / count) * 0.8)
        return round(radius_km, 1)

    def cache_get(self, key):
        entry = self.search_cache.get(key)
        if entry and entry[0] > time.time():
            return entry[1]
        self.search_cache.pop(key, None)
        return None

    def cache_put(self, key, value):
        if len(self.search_cache) >= CACHE_MAX_ENTRIES:
            now = time.time()
            expired = [k for k, v in self.search_cache.items() if v[0] <= now]
            for k in expired:
                del self.search_cache[k]
            while len(self.search_cache) >= CACHE_MAX_ENTRIES:
                self.search_cache.pop(next(iter(self.search_cache)))
        self.search_cache[key] = (time.time() + CACHE_TTL, value)

    async def query_overpass(self, overpass_query: str):
        """Try each Overpass mirror once; any failure moves on to the next.

        Mirrors differ in rate limits and access policies (e.g. some 403
        non-whitelisted clients), so no status is treated as fatal.
        """
        last_exc = None
        timeout = aiohttp.ClientTimeout(total=OVERPASS_TIMEOUT + 5)

        endpoints = [self.preferred_endpoint] + [e for e in OVERPASS_ENDPOINTS if e != self.preferred_endpoint]

        for endpoint in endpoints:
            try:
                async with self.session.post(endpoint, data=overpass_query, timeout=timeout) as resp:
                    if resp.status == 200:
                        self.preferred_endpoint = endpoint
                        return await resp.json()
                    text = await resp.text()
                    last_exc = Exception(f"Overpass returned status {resp.status}: {text[:200]}")
            except asyncio.TimeoutError:
                last_exc = Exception(f"Timeout querying {endpoint}")
            except aiohttp.ClientError as exc:
                last_exc = exc
            print(f"Overpass mirror failed ({endpoint}): {last_exc}")
        raise last_exc or Exception("Overpass query failed for all endpoints")

    @staticmethod
    def parse_mosques(elements: List[Dict], user_lat: float, user_lon: float) -> List[Dict]:
        """Turn raw Overpass elements into a deduplicated, distance-sorted list."""
        mosques = []
        seen_coords = set()

        for el in elements:
            tags = el.get('tags', {})
            if not tags:
                continue

            center = el.get('center', el)
            lat = center.get('lat')
            lon = center.get('lon')
            if lat is None or lon is None:
                continue

            # ~11m grid: merges the same mosque mapped as both a node and a building
            coord_key = (round(lat, 4), round(lon, 4))
            if coord_key in seen_coords:
                continue
            seen_coords.add(coord_key)

            addr_parts = [tags[k] for k in ('addr:street', 'addr:housenumber', 'addr:city', 'addr:postcode', 'addr:country') if tags.get(k)]
            address = ", ".join(addr_parts) if addr_parts else tags.get('addr:full') or tags.get('description') or ''

            mosques.append({
                'name': tags.get('name') or tags.get('name:en') or 'Unnamed Mosque',
                'lat': lat,
                'lon': lon,
                'distance_km': haversine(user_lat, user_lon, lat, lon),
                'address': address,
            })

        mosques.sort(key=lambda x: x['distance_km'])
        return mosques

    async def get_coordinates(self, query: str):
        params = {'q': query, 'format': 'json', 'limit': 1}
        async with self.session.get(GEOCODING_API_URL, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if data and len(data) > 0:
                return float(data[0]['lat']), float(data[0]['lon'])
            return None


async def setup(bot):
    await bot.add_cog(MosqueCog(bot))
