# Stying's Adhan Bot 🕌⏳

Stying's Adhan Bot is a Discord bot designed to provide prayer timings and reminders based on user preferences.

[Invite the Bot!](https://discord.com/oauth2/authorize?client_id=1229836097702596679&permissions=277025441856&scope=bot)

<img width="352" height="104" alt="{B489152D-B021-4724-8B30-732BAD68934E}" src="https://github.com/user-attachments/assets/f98bc161-6e67-4faa-9a62-f531ec855bbe" />


## I) Small Disclaimer

Disclaimer for Stying’s Adhan Bot
Stying’s Adhan Bot provides prayer timings and reminders based on available data and user settings. It do not guarantee 100% accuracy due to possible discrepancies in calculation methods, APIs, location data, or technical issues.

I do not take any liabilites for any missed prayers, inaccuracies, or consequences from using or being unable to use the bot.
Use the information at your own discretion and risk.



## II) Features

- Setup: Configure your country, city, timezone, Asr timing method, and calculation method.
- Upcoming Salah: View the next upcoming prayer time for your configured region.
- Prayer Timings: Display all prayer timings (Fajr, Dhuhr, Asr, Maghrib, Isha) for your region.
- Notification: Schedule DM notifications for upcoming prayer times.
- Qibla Direction: Get the direction to the Kaaba based on your location.
- Help Command: List available commands and their usage.

## III) Commands

| Command         | Description                                                                 |
|-----------------|-----------------------------------------------------------------------------|
| `/help`         | Display help information about commands.                                    |
| `/setup`        | Set your country, city, timezone, and Asr Method.                           |
| `/region`       | Display your current region settings, timezone, and Asr method.             |
| `/qibla`        | Shows the direction to face Qibla from your location.                       |
| `/mosque`       | Shows nearby mosques for your queried locations.                            |
| `/upcoming`     | Display the next upcoming salah timing.                                     |
| `/timings`      | Display all the salah timings for the day.                                  |
| `/notify`       | Set a notification for the next upcoming salah.                             |
| `/notifyloop`   | Set a notification chain for the next upcoming salahs.                      |
| `/notifyloopstop` | Stop the notification chain for the next upcoming salahs.                 |

## IV) Requirements

- Python 3.8+
- discord.py
- aiohttp
- pytz

## V) Setup

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

## VI) Contributing

Contributions are welcome! Feel free to open issues or pull requests.

## VII) License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
