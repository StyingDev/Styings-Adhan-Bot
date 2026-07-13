import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import pytz
import datetime
from typing import Dict, List, Optional

ALADHAN_API_URL = 'http://api.aladhan.com/v1/timings'
ALADHAN_CALENDAR_URL = 'http://api.aladhan.com/v1/calendar'
EMBED_COLOR = 0x757e8a
RESETUP_MESSAGE = "Your saved location needs a refresh, please run /setup again."
PRAYERS = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]

ANSI_RESET = '\x1b[0m'


def ansi(text: str, code: str) -> str:
    """Discord ansi-codeblock color; zero visible width, so alignment holds."""
    return f"\x1b[{code}m{text}{ANSI_RESET}"


def timings_params(settings):
    """Aladhan query params from stored coordinates (aiohttp needs strings)."""
    return {
        'latitude': str(settings["latitude"]),
        'longitude': str(settings["longitude"]),
        'method': settings["calculation_method"],
        'school': settings["asr_method"],
        'timezonestring': settings["timezone"],
    }


def clean_time(value: str) -> str:
    """Calendar-endpoint times carry a timezone suffix: '03:53 (+06)' -> '03:53'."""
    return value.split(' ')[0]


def to_12h(value: str) -> str:
    return datetime.datetime.strptime(clean_time(value), '%H:%M').strftime('%I:%M %p')


def next_prayer_datetime(timings, user_timezone):
    """The next of the five prayers as a timezone-aware datetime.

    Prayers already past today roll over to tomorrow, so after Isha this
    correctly points at tomorrow's Fajr instead of a time in the past.
    """
    current_time = datetime.datetime.now(user_timezone)
    prayer_times = {}
    for prayer in PRAYERS:
        if prayer in timings:
            prayer_time = datetime.datetime.strptime(clean_time(timings[prayer]), '%H:%M').time()
            prayer_datetime = user_timezone.localize(datetime.datetime.combine(current_time.date(), prayer_time))
            if prayer_datetime <= current_time:
                prayer_datetime += datetime.timedelta(days=1)
            prayer_times[prayer] = prayer_datetime
    if not prayer_times:
        return None, None
    return min(prayer_times.items(), key=lambda x: x[1])


def add_months(date: datetime.date, delta: int) -> datetime.date:
    month_index = date.month - 1 + delta
    return datetime.date(date.year + month_index // 12, month_index % 12 + 1, 1)


def week_start(date: datetime.date) -> datetime.date:
    """Sunday of the week containing the date, matching the /calendar grid."""
    return date - datetime.timedelta(days=(date.weekday() + 1) % 7)


class TimingsModeSelect(discord.ui.Select):
    def __init__(self, current: str):
        options = [
            discord.SelectOption(label="Daily view", value="daily", default=current == "daily"),
            discord.SelectOption(label="Weekly view", value="weekly", default=current == "weekly"),
            discord.SelectOption(label="Monthly view", value="monthly", default=current == "monthly"),
        ]
        super().__init__(placeholder="Switch view", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: TimingsView = self.view
        view.mode = self.values[0]
        for option in self.options:
            option.default = option.value == view.mode
        await view.render(interaction)


class TimingsView(discord.ui.View):
    """Browsable prayer timings: daily / weekly / monthly, with arrows whose
    step size follows the active view. Month responses are cached per view."""

    def __init__(self, cog, user_id: str, settings: Dict, anchor: datetime.date):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.settings = settings
        self.anchor = anchor
        self.mode = "daily"
        self.month_cache: Dict[tuple, List[Dict]] = {}
        self.message: Optional[discord.Message] = None
        self.add_item(TimingsModeSelect(self.mode))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Run /timings yourself to browse it.", ephemeral=True)
            return False
        return True

    def today(self) -> datetime.date:
        return datetime.datetime.now(pytz.timezone(self.settings["timezone"])).date()

    async def month_data(self, year: int, month: int) -> List[Dict]:
        key = (year, month)
        if key not in self.month_cache:
            self.month_cache[key] = await self.cog.fetch_month(self.settings, year, month)
        return self.month_cache[key]

    async def entry_for(self, date: datetime.date) -> Optional[Dict]:
        for entry in await self.month_data(date.year, date.month):
            if int(entry['date']['gregorian']['day']) == date.day:
                return entry
        return None

    TABLE_HEADER = "          Fajr  Dhuhr Asr   Magh  Isha"

    def table_line(self, entry: Dict, date: datetime.date, label: str) -> str:
        is_today = date == self.today()
        marker = '►' if is_today else ' '
        times = ' '.join(clean_time(entry['timings'][p]) for p in PRAYERS)
        line = f"{marker} {label}  {times}"
        if is_today:
            return ansi(line, '1;37;45')       # white on magenta
        if date.weekday() == 4:
            return ansi(line, '0;32')          # green: Jumu'ah
        return line

    async def build_embed(self) -> discord.Embed:
        city = self.settings['city']
        today = self.today()

        if self.mode == "daily":
            entry = await self.entry_for(self.anchor)
            title = self.anchor.strftime('%A, %d %B %Y')
            if self.anchor == today:
                title += "  (Today)"
            lines = [f"**{prayer}:** {to_12h(entry['timings'][prayer])}" for prayer in PRAYERS]
            embed = discord.Embed(title=f"Adhan Timings ➔ {title}", description="\n".join(lines), color=EMBED_COLOR)

        elif self.mode == "weekly":
            start = week_start(self.anchor)
            lines = [ansi(self.TABLE_HEADER, '0;36')]
            for offset in range(7):
                date = start + datetime.timedelta(days=offset)
                entry = await self.entry_for(date)
                lines.append(self.table_line(entry, date, date.strftime('%a %d')))
            end = start + datetime.timedelta(days=6)
            embed = discord.Embed(
                title=f"Adhan Timings ➔ Week of {start.strftime('%d %b')} – {end.strftime('%d %b %Y')}",
                description="```ansi\n" + "\n".join(lines) + "\n```",
                color=EMBED_COLOR,
            )

        else:  # monthly
            data = await self.month_data(self.anchor.year, self.anchor.month)
            lines = [ansi(self.TABLE_HEADER, '0;36')]
            for entry in data:
                date = datetime.datetime.strptime(entry['date']['gregorian']['date'], '%d-%m-%Y').date()
                lines.append(self.table_line(entry, date, date.strftime('%d %a')))
            embed = discord.Embed(
                title=f"Adhan Timings ➔ {self.anchor.strftime('%B %Y')}",
                description="```ansi\n" + "\n".join(lines) + "\n```",
                color=EMBED_COLOR,
            )

        embed.set_footer(text=f"🌙 Timings for {city} {'daily.' if self.mode == 'daily' else 'weekly.' if self.mode == 'weekly' else 'monthly.'}")
        return embed

    async def render(self, interaction: discord.Interaction):
        try:
            embed = await self.build_embed()
        except Exception as e:
            await interaction.response.send_message(f"Couldn't load timings: {e}. Try again later.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=embed, view=self)

    def shift(self, direction: int):
        if self.mode == "daily":
            self.anchor += datetime.timedelta(days=direction)
        elif self.mode == "weekly":
            self.anchor += datetime.timedelta(days=7 * direction)
        else:
            self.anchor = add_months(self.anchor, direction)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.shift(-1)
        await self.render(interaction)

    @discord.ui.button(label="Today", style=discord.ButtonStyle.primary, row=0)
    async def jump_today(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.anchor = self.today()
        await self.render(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.shift(1)
        await self.render(interaction)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class TimingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} is online")

    async def fetch_month(self, settings, year: int, month: int) -> List[Dict]:
        async with self.session.get(f"{ALADHAN_CALENDAR_URL}/{year}/{month}", params=timings_params(settings)) as response:
            data = await response.json()
            if response.status != 200 or data.get('code') != 200:
                raise Exception("prayer time service unavailable")
            return data['data']

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

            async with self.session.get(ALADHAN_API_URL, params=timings_params(settings)) as response:
                data = await response.json()
                if response.status != 200 or data.get('code') != 200:
                    await interaction.response.send_message("The prayer time service is unavailable right now. Please try again later.", ephemeral=True)
                    return
                timings = data['data']['timings']

                user_timezone = pytz.timezone(settings["timezone"])
                next_prayer, next_datetime = next_prayer_datetime(timings, user_timezone)

                if not next_prayer:
                    embed = discord.Embed(title="Upcoming Salah", description=f"No upcoming salah times found for {settings['city']}.", color=EMBED_COLOR)
                    await interaction.response.send_message(embed=embed)
                    return

                next_time_12hr = next_datetime.strftime('%I:%M %p')
                tomorrow = " tomorrow" if next_datetime.date() != datetime.datetime.now(user_timezone).date() else ""

                embed = discord.Embed(title="Next Upcoming Salah", description=f"Next upcoming salah for {settings['city']} is {next_prayer} at {next_time_12hr}{tomorrow}.", color=EMBED_COLOR)
                embed.set_footer(text=f"🕌 Timings for {settings['city']}")
                await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("Please set up your region using /setup first.")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='timings', description='Browse prayer timings: daily, weekly or monthly view.')
    async def timings(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        settings = await self.bot.db.get_user(user_id)
        if not settings or not settings["timezone"]:
            await interaction.response.send_message("Please set up your region using /setup first.")
            return
        if settings["latitude"] is None:
            await interaction.response.send_message(RESETUP_MESSAGE, ephemeral=True)
            return

        await interaction.response.defer()

        anchor = datetime.datetime.now(pytz.timezone(settings["timezone"])).date()
        view = TimingsView(self, user_id, settings, anchor)
        try:
            embed = await view.build_embed()
        except Exception as e:
            await interaction.edit_original_response(content=f"Couldn't load timings: {e}. Try again later.")
            return
        view.message = await interaction.edit_original_response(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(TimingsCog(bot))
