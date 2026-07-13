import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
import pytz
from typing import Dict, List, Optional

ALADHAN_G_TO_H_URL = 'http://api.aladhan.com/v1/gToH'
ALADHAN_H_TO_G_CALENDAR_URL = 'http://api.aladhan.com/v1/hToGCalendar'
EMBED_COLOR = 0x757e8a

HIJRI_MONTHS = [
    "Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani", "Jumada al-Awwal", "Jumada al-Thani",
    "Rajab", "Sha'ban", "Ramadan", "Shawwal", "Dhul Qa'dah", "Dhul Hijjah",
]

ANSI_RESET = '[0m'


def ansi(text: str, code: str) -> str:
    """Wrap text in a Discord ansi-codeblock color (zero visible width,
    so grid alignment is unaffected)."""
    return f"[{code}m{text}{ANSI_RESET}"


SPECIAL_DAY_INFO = [
    (('ashura',),
     "The 10th of Muharram, the day Allah saved Musa (AS) and the Children of Israel from Pharaoh. The Prophet ﷺ fasted this day and encouraged fasting it.",
     "Fast this day, ideally paired with the 9th (Tasu'a). Fasting Ashura is narrated to expiate the sins of the previous year."),
    (('mawlid',),
     "The birth of the Prophet Muhammad ﷺ. Observance varies between communities.",
     "Many mark it with increased salawat upon the Prophet ﷺ, studying his life, and charity."),
    (('lailat-ul-miraj',),
     "Commemorates the Prophet's ﷺ night journey to Jerusalem and ascension through the heavens, when the five daily prayers were ordained.",
     "No specific worship is prescribed; many use the night for extra prayer, dhikr and du'a."),
    (('lailat-ul-bara',),
     "The night of mid-Sha'ban, regarded in many traditions as a night of mercy and seeking forgiveness.",
     "Some spend part of the night in worship and fast the 15th; practices vary between communities."),
    (('lailat-ul-ragha',),
     "The first Thursday night of Rajab, marked in some traditions.",
     "Practices vary; some devote the night to voluntary worship."),
    (('1st day of ramadan',),
     "The blessed month of obligatory fasting begins.",
     "Fast from dawn to sunset, pray tarawih at night, and increase Quran recitation and charity."),
    (('lailat-ul-qadr',),
     "The Night of Decree, better than a thousand months (Quran 97), sought on the odd nights of Ramadan's last ten.",
     "Spend the night in prayer and du'a: \"Allahumma innaka 'afuwwun tuhibbul-'afwa fa'fu 'anni.\""),
    (('eid-ul-fitr',),
     "The festival concluding Ramadan. Fasting is not permitted on this day.",
     "Pay Zakat al-Fitr before the Eid prayer, attend the prayer, and celebrate with family and community. Consider following it with six voluntary fasts during Shawwal."),
    (('eid-ul-adha',),
     "The festival of sacrifice, commemorating Ibrahim (AS). Fasting is not permitted on this day.",
     "Attend the Eid prayer, recite the takbir, and offer a sacrifice (udhiyah) if able."),
    (('arafa',),
     "The Day of Arafah, when pilgrims stand at the plain of Arafat, described as the best of days.",
     "For non-pilgrims, fasting this day is narrated to expiate two years of sins. Increase du'a."),
    (('hajj',),
     "The days of Hajj, when pilgrims perform the rites of pilgrimage in Makkah.",
     "For non-pilgrims, the first ten days of Dhul Hijjah are beloved days for fasting, dhikr and good deeds."),
    (('beginning of the holy months',),
     "Rajab begins, one of the four sacred months in which good deeds carry extra weight.",
     "Voluntary fasting and increased good deeds are encouraged during the sacred months."),
]

# Universal dates AlAdhan's feed doesn't mark, keyed by (hijri month, day)
LOCAL_SPECIAL_DAYS = {
    (1, 1): ("Islamic New Year",
             "The Hijri year begins with Muharram, one of the four sacred months.",
             "Voluntary fasting in Muharram is encouraged; it is narrated as the best month for fasting after Ramadan."),
    (12, 1): ("First Ten Days of Dhul Hijjah",
              "The first ten days of Dhul Hijjah, narrated as the days in which good deeds are most beloved to Allah.",
              "Increase fasting (for non-pilgrims), dhikr, charity and good deeds throughout the ten days."),
}


def special_day_info(holiday: str):
    lowered = holiday.lower()
    for keywords, about, acts in SPECIAL_DAY_INFO:
        if any(keyword in lowered for keyword in keywords):
            return about, acts
    return None


def month_events(days: List[Dict]):
    """Recognized events for a month, grouped by name so multi-day events
    (Hajj, the odd nights of Ramadan) make one entry each.

    Only curated matches and locally added universal dates are included;
    the feed's many order-specific commemorations are left out.
    """
    month_number = days[0]['hijri']['month']['number']
    grouped: Dict[str, tuple] = {}
    order = []
    for entry in days:
        day = int(entry['hijri']['day'])
        candidates = []
        if (month_number, day) in LOCAL_SPECIAL_DAYS:
            candidates.append(LOCAL_SPECIAL_DAYS[(month_number, day)])
        for holiday in entry['hijri'].get('holidays', []):
            info = special_day_info(holiday)
            if info:
                candidates.append((holiday, info[0], info[1]))
        for name, about, acts in candidates:
            if name not in grouped:
                grouped[name] = (about, acts, [])
                order.append(name)
            grouped[name][2].append(entry)
    return [(name, *grouped[name]) for name in order]


def format_day_span(entries: List[Dict]) -> str:
    """Hijri days as a compact span: [8..13] -> '8–13', odd nights -> '21, 23, …'."""
    day_numbers = [int(e['hijri']['day']) for e in entries]
    parts = []
    start = prev = day_numbers[0]
    for day in day_numbers[1:]:
        if day == prev + 1:
            prev = day
            continue
        parts.append(f"{start}–{prev}" if prev > start else str(start))
        start = prev = day
    parts.append(f"{start}–{prev}" if prev > start else str(start))
    return ", ".join(parts)


def parse_gregorian(entry: Dict) -> datetime.date:
    return datetime.datetime.strptime(entry['gregorian']['date'], '%d-%m-%Y').date()


def local_today(timezone_name: str) -> datetime.date:
    """Today in the user's saved timezone, so the marker matches their date."""
    try:
        return datetime.datetime.now(pytz.timezone(timezone_name)).date()
    except pytz.UnknownTimeZoneError:
        return datetime.datetime.now(datetime.timezone.utc).date()


def build_calendar_embed(days: List[Dict], today: datetime.date) -> discord.Embed:
    hijri_first = days[0]['hijri']
    month_name = hijri_first['month']['en']
    hijri_year = hijri_first['year']

    events = month_events(days)
    event_days = {int(e['hijri']['day']) for _, _, _, entries in events for e in entries}

    weeks = []
    week = ['   '] * 7
    week_has_days = False
    today_field = None
    for entry in days:
        gdate = parse_gregorian(entry)
        weekday = (gdate.weekday() + 1) % 7    # Sunday = 0
        day = int(entry['hijri']['day'])
        is_today = gdate == today

        cell = f"{day:2}"
        if is_today:
            cell = ansi(cell, '1;37;45')       # white on magenta
        elif day in event_days:
            cell = ansi(cell, '1;31')          # red: important date
        elif weekday == 5:
            cell = ansi(cell, '0;32')          # green: Jumu'ah
        week[weekday] = cell + ' '
        week_has_days = True
        if is_today:
            today_field = f"{day} {month_name} {hijri_year} AH ➔ {gdate.strftime('%A, %d %B %Y')}"
        if weekday == 6:
            weeks.append(''.join(week).rstrip())
            week = ['   '] * 7
            week_has_days = False
    if week_has_days:
        weeks.append(''.join(week).rstrip())

    grid = '\n'.join(weeks)
    title_line = ansi(f"{month_name} {hijri_year} AH", '1;33')
    header_line = ansi("Su Mo Tu We Th Fr Sa", '0;36')

    embed = discord.Embed(
        title="Islamic Calendar",
        description=f"```ansi\n{title_line}\n\n{header_line}\n{grid}\n```",
        color=EMBED_COLOR,
    )

    start = parse_gregorian(days[0])
    end = parse_gregorian(days[-1])
    embed.add_field(name="Gregorian", value=f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}", inline=False)

    if today_field:
        embed.add_field(name="Today", value=today_field, inline=False)

    if events:
        lines = []
        for name, _, _, entries in events:
            if len(entries) == 1:
                gregorian = parse_gregorian(entries[0]).strftime('%d %b')
            else:
                gregorian = f"{parse_gregorian(entries[0]).strftime('%d %b')} – {parse_gregorian(entries[-1]).strftime('%d %b')}"
            lines.append(f"{format_day_span(entries)} {month_name} ➔ {name} ({gregorian})")
        value = '\n'.join(lines)
        if len(value) > 1024:
            value = value[:1010].rsplit('\n', 1)[0] + '\n…'
        embed.add_field(name="Important Dates", value=value, inline=False)

    embed.set_footer(text=f"Today: {today.strftime('%A, %d %B %Y')} | Data: AlAdhan")
    return embed


def build_events_embed(days: List[Dict]) -> discord.Embed:
    hijri_first = days[0]['hijri']
    month_name = hijri_first['month']['en']
    hijri_year = hijri_first['year']

    embed = discord.Embed(title=f"Special Days in {month_name} {hijri_year} AH", color=EMBED_COLOR)

    events = month_events(days)
    if not events:
        embed.description = "No major dates this month."
        return embed

    MAX_FIELDS = 12
    for name, about, acts, entries in events[:MAX_FIELDS]:
        if len(entries) == 1:
            gregorian = parse_gregorian(entries[0]).strftime('%d %b %Y')
        else:
            gregorian = f"{parse_gregorian(entries[0]).strftime('%d %b')} – {parse_gregorian(entries[-1]).strftime('%d %b %Y')}"
        field_name = f"{format_day_span(entries)} {month_name} ➔ {name}"
        value = f"{about}\n**What to do:** {acts}\n*{gregorian}*"
        embed.add_field(name=field_name[:256], value=value[:1024], inline=False)

    if len(events) > MAX_FIELDS:
        embed.add_field(name='​', value=f"…and {len(events) - MAX_FIELDS} more", inline=False)

    embed.set_footer(text="Practices vary by tradition, consult your local scholars")
    return embed


class HijriMonthSelect(discord.ui.Select):
    def __init__(self, current_month: int):
        options = [
            discord.SelectOption(label=name, value=str(i + 1), default=(i + 1) == current_month)
            for i, name in enumerate(HIJRI_MONTHS)
        ]
        super().__init__(placeholder="Islamic month", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_month(interaction, int(self.values[0]), self.view.year)


class HijriYearSelect(discord.ui.Select):
    def __init__(self, current_year: int):
        options = [
            discord.SelectOption(label=f"{year} AH", value=str(year), default=year == current_year)
            for year in range(current_year - 5, current_year + 6)
        ]
        super().__init__(placeholder="Islamic year", min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_month(interaction, self.view.month, int(self.values[0]))


class CalendarView(discord.ui.View):
    """Navigates by Hijri month; each update rebuilds the view so the
    dropdowns always show the displayed month/year as selected."""

    def __init__(self, cog, user_id: str, month: int, year: int, timezone_name: str, days: List[Dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.month = month
        self.year = year
        self.timezone_name = timezone_name
        self.days = days
        self.message: Optional[discord.Message] = None
        self.add_item(HijriMonthSelect(month))
        self.add_item(HijriYearSelect(year))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Run /calendar yourself to browse it.", ephemeral=True)
            return False
        return True

    async def show_month(self, interaction: discord.Interaction, month: int, year: int):
        try:
            days = await self.cog.fetch_hijri_month(month, year)
        except Exception as e:
            await interaction.response.send_message(f"Couldn't load that month: {e}", ephemeral=True)
            return
        view = CalendarView(self.cog, self.user_id, month, year, self.timezone_name, days)
        view.message = self.message
        await interaction.response.edit_message(embed=build_calendar_embed(days, local_today(self.timezone_name)), view=view)

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=0)
    async def previous_month(self, interaction: discord.Interaction, button: discord.ui.Button):
        month, year = (12, self.year - 1) if self.month == 1 else (self.month - 1, self.year)
        await self.show_month(interaction, month, year)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary, row=0)
    async def next_month(self, interaction: discord.Interaction, button: discord.ui.Button):
        month, year = (1, self.year + 1) if self.month == 12 else (self.month + 1, self.year)
        await self.show_month(interaction, month, year)

    @discord.ui.button(label="Learn more", style=discord.ButtonStyle.secondary, row=0)
    async def events_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_events_embed(self.days), ephemeral=True)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class CalendarCog(commands.Cog):
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

    async def fetch_json(self, url: str):
        async with self.session.get(url) as resp:
            data = await resp.json()
            if resp.status != 200 or data.get('code') != 200:
                raise Exception(f"AlAdhan returned status {data.get('code', resp.status)}")
            return data['data']

    async def current_hijri_month(self, today: datetime.date):
        data = await self.fetch_json(f"{ALADHAN_G_TO_H_URL}/{today.strftime('%d-%m-%Y')}")
        return data['hijri']['month']['number'], int(data['hijri']['year'])

    async def fetch_hijri_month(self, month: int, year: int) -> List[Dict]:
        return await self.fetch_json(f"{ALADHAN_H_TO_G_CALENDAR_URL}/{month}/{year}")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='calendar', description='Browse the Islamic (Hijri) calendar with important dates.')
    async def calendar(self, interaction: discord.Interaction):
        await interaction.response.defer()

        settings = await self.bot.db.get_user(interaction.user.id)
        timezone_name = settings['timezone'] if settings else 'UTC'
        today = local_today(timezone_name)

        try:
            month, year = await self.current_hijri_month(today)
            days = await self.fetch_hijri_month(month, year)
        except Exception as e:
            await interaction.edit_original_response(content=f"Couldn't load the calendar: {e}. Try again later.")
            return
        view = CalendarView(self, str(interaction.user.id), month, year, timezone_name, days)
        view.message = await interaction.edit_original_response(embed=build_calendar_embed(days, today), view=view)


async def setup(bot):
    await bot.add_cog(CalendarCog(bot))
