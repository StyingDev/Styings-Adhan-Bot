import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, Optional

EMBED_COLOR = 0x757e8a
PATREON_URL = 'https://www.patreon.com/cw/Someonesomeonesomeone'

COMMAND_CATEGORIES = [
    ("I)", "Getting Started", [
        ("setup", "Save your region and preferences",
         "Interactive setup: your city and country (with location confirmation), Asr timing method, calculation method, and optional per-salah DM notifications."),
        ("settings", "View, edit or delete your data",
         "See your saved settings, change your region, Asr or calculation method with dropdowns, or delete all your data."),
    ]),
    ("II)", "Prayer Times", [
        ("upcoming", "Your next salah",
         "Shows the next upcoming salah and its time for your region."),
        ("timings", "All of today's timings",
         "All five prayer times for today in your region."),
    ]),
    ("III)", "Notifications", [
        ("notify", "One-off reminder",
         "Sends you a DM when the next salah time arrives, one time only."),
        ("notifyloop", "DM at every salah",
         "Ongoing DM at every salah time. Keeps working even after the bot restarts."),
        ("notifyloopstop", "Stop the reminders",
         "Stops the ongoing salah notifications."),
    ]),
    ("IV)", "Tools", [
        ("qibla", "Direction to the Kaaba",
         "Qibla direction from your saved location, in degrees and compass direction."),
        ("mosque", "Find nearby mosques",
         "Nearby mosques sorted by distance, with map links. Defaults to your saved region, or pass any location and a search radius (max 50 km)."),
        ("calendar", "Islamic (Hijri) calendar",
         "Browse the Hijri calendar month by month. Major dates are highlighted; press Learn more for what each day means and what to do."),
    ]),
    ("V)", "Support", [
        ("support", "Support the bot",
         f"Adhan Bot is free, if it benefits you, consider [supporting its development]({PATREON_URL})."),
    ]),
]


def build_overview_embed(bot: commands.Bot, mentions: Dict[str, str]) -> discord.Embed:
    embed = discord.Embed(
        title="Adhan Bot Help",
        description=(
            "Prayer times, salah reminders, qibla, mosque finder and the Hijri calendar within in Discord.\n\n"
            f"**Quick start**\n"
            f"1. {mentions.get('setup', '/setup')} - save your city and preferences\n"
            f"2. {mentions.get('timings', '/timings')} - see today's prayer times\n"
            f"3. {mentions.get('notifyloop', '/notifyloop')} - get a DM at every salah\n\n"
            "Pick a category below for details on every command."
        ),
        color=EMBED_COLOR,
    )
    for emoji, category, entries in COMMAND_CATEGORIES:
        value = "\n".join(f"{mentions.get(name, f'/{name}')} · {blurb}" for name, blurb, _ in entries)
        embed.add_field(name=f"{emoji} {category}", value=value, inline=False)
    embed.add_field(
        name="(❁´◡`❁) You should very much support!!!1",
        value=f"Consider supporting its development on [Patreon]({PATREON_URL}).",
        inline=False,
    )
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="Use the menu below to view another category and more details on all commands. Data: AlAdhan & OpenStreetMap")
    return embed


def build_category_embed(category_index: int, mentions: Dict[str, str]) -> discord.Embed:
    emoji, category, entries = COMMAND_CATEGORIES[category_index]
    embed = discord.Embed(title=f"{emoji} {category}", color=EMBED_COLOR)
    for name, _, details in entries:
        embed.add_field(name=mentions.get(name, f"/{name}"), value=details, inline=False)
    embed.set_footer(text="Use the menu below to view another category")
    return embed


class HelpCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Overview", value="overview", default=True)]
        options += [
            discord.SelectOption(label=f"{prefix} {category}", value=str(i))
            for i, (prefix, category, _) in enumerate(COMMAND_CATEGORIES)
        ]
        super().__init__(placeholder="Browse commands by category", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view
        choice = self.values[0]
        if choice == "overview":
            embed = build_overview_embed(view.bot, view.mentions)
        else:
            embed = build_category_embed(int(choice), view.mentions)
        for option in self.options:
            option.default = option.value == choice
        await interaction.response.edit_message(embed=embed, view=view)


class HelpView(discord.ui.View):
    def __init__(self, bot, user_id: str, mentions: Dict[str, str]):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.mentions = mentions
        self.message: Optional[discord.Message] = None
        self.add_item(HelpCategorySelect())
        self.add_item(discord.ui.Button(label="Support me on Patreon", style=discord.ButtonStyle.link, url=PATREON_URL, emoji="💖"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Run /help yourself to browse the categories.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._mentions: Optional[Dict[str, str]] = None

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{__name__} is online")

    async def command_mentions(self) -> Dict[str, str]:
        """Clickable </command:id> mentions, fetched once after sync."""
        if self._mentions is None:
            try:
                synced = await self.bot.tree.fetch_commands()
                self._mentions = {command.name: command.mention for command in synced}
            except Exception as e:
                print(f"Could not fetch command mentions: {e}")
                return {}
        return self._mentions

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='help', description='Execute for help.')
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer()
        mentions = await self.command_mentions()
        view = HelpView(self.bot, str(interaction.user.id), mentions)
        view.message = await interaction.edit_original_response(embed=build_overview_embed(self.bot, mentions), view=view)

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name='support', description='Support the development of the Adhan Bot.')
    async def support(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Support me on Patreon",
            description=(
                "Adhan Bot is free to use and built in my spare time.\n\n"
                f"💖 **[Become a patron]({PATREON_URL})** if you'd like to support its continued development and future improvements.\n\n"
                "If you aren't able to support right now, please share this bot with more people and I will be grateful!"
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text="JazakAllah khair for using the bot")
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Support on Patreon", style=discord.ButtonStyle.link, url=PATREON_URL, emoji="💖"))
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
