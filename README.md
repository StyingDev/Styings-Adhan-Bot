# Stying's Adhan Bot 🕌⏳

Stying's Adhan Bot is a Discord bot designed to provide prayer timings and reminders based on user preferences.
[Invite the Bot!](https://discord.com/oauth2/authorize?client_id=1229836097702596679&permissions=277025441856&scope=bot)

### (Timings vary/May depend on time set based on)

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

### Prayer Timings
- `/upcoming`: Display the next upcoming salah timing.
- `/timings`: Display all the salah timings for the day.

### Notifications
- `/notify`: Set a notification for the next upcoming salah.

### Coming Soon(Maybe)
- `/setup`: have the ablity to switch between calculation method for timings and more. (Coming soon)
- `/notifyloop`: Set a notification chain for the next upcoming salahs. (Coming soon)
- `/notifyloopstop`: stop chain for the next upcoming salahs. (Coming soon)

## Requirements

- Python 3.8+
- discord.py
- aiohttp
- pytz

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/StyingDev/Styings-Adhan-Bot.git

2. Install the required packages:

    ```bash
    pip install -r requirements.txt

3. Add your token

4. Run the bot:
   
    ```bash
    python main.py

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
