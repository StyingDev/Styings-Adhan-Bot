# Stying's Adhan Bot 🕌⏳

Stying's Adhan Bot is a Discord bot designed to provide prayer timings and reminders based on user preferences.
[Invite the Bot!](https://discord.com/oauth2/authorize?client_id=1229836097702596679&permissions=277025441856&scope=bot)

### (Timings Vary/May depend on time set based on)

## Credits

- **Stying** - Creator & Developer
  - Contact me through my Discord: @Stying
  - [Linktree](https://linktr.ee/stying)

## Features

- Setup: Configure your country, city, timezone, Asr timing method, and calculation method.
- Upcoming Salah: View the next upcoming prayer time for your configured region.
- Prayer Timings: Display all prayer timings (Fajr, Dhuhr, Asr, Maghrib, Isha) for your region.
- Notification: Schedule DM notifications for upcoming prayer times.
- Help Command: List available commands and their usage.

## Commands

### Help
- `/help`: Display help information about commands.

### Setup
- `/setup`: Set your country, city, timezone and Asr Method.

### Region Information
- `/region`: Display your current region settings alongside timezone and Asr method.
- `/qibla`: Shows the direction to face qibla from users location.

### Prayer Timings
- `/upcoming`: Display the next upcoming salah timing.
- `/timings`: Display all the salah timings for the day.

### Notifications
- `/notify`: Set a notification for the next upcoming salah.
- `/notifyloop`: Set a notification chain for the next upcoming salahs. 
- `/notifyloopstop`: stop chain for the next upcoming salahs.

## Requirements

- Python 3.8+
- discord.py
- aiohttp
- pytz

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/StyingDev/Styings-Adhan-Bot.git

2. Navigate to the project directory:
    ```bash
    cd Styings-Adhan-Bot
    ```

3. Install the required packages:

    ```bash
    pip install -r requirements.txt

4. Create a '.env' file in the project directory and add your Discord Bot Token:

    ```bash
    TOKEN=your_discord_bot_token_here
    ```
5. Run the bot:
   
    ```bash
    python main.py

## Contributing

Contributions are welcome! Feel free to open issues or pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
