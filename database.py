import json
import os

import aiosqlite

DB_FILE = 'user_settings.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id            INTEGER PRIMARY KEY,
    country            TEXT NOT NULL,
    city               TEXT NOT NULL,
    timezone           TEXT NOT NULL DEFAULT 'UTC',
    asr_method         TEXT NOT NULL DEFAULT '1' CHECK (asr_method IN ('0', '1')),
    calculation_method TEXT NOT NULL DEFAULT '2',
    notify_loop_active INTEGER NOT NULL DEFAULT 0 CHECK (notify_loop_active IN (0, 1)),
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

UPDATABLE_COLUMNS = {
    'country', 'city', 'timezone',
    'asr_method', 'calculation_method', 'notify_loop_active',
}


def _row_to_settings(row):
    """Convert a DB row to the settings dict shape the cogs expect."""
    if row is None:
        return None
    settings = dict(row)
    settings['user_id'] = str(settings['user_id'])
    settings['notify_loop_active'] = bool(settings['notify_loop_active'])
    return settings


class Database:
    def __init__(self, path=DB_FILE):
        self.path = path
        self._db = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def get_user(self, user_id):
        """Return the user's settings dict, or None if they haven't run /setup."""
        async with self._db.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (int(user_id),)
        ) as cursor:
            return _row_to_settings(await cursor.fetchone())

    async def upsert_user(self, user_id, *, country, city, timezone,
                          asr_method, calculation_method):
        """Create or fully replace a user's region settings (used by /setup).

        Re-running /setup resets notify_loop_active, matching the old
        behaviour where the whole settings dict was overwritten.
        """
        await self._db.execute(
            """
            INSERT INTO user_settings
                (user_id, country, city, timezone, asr_method, calculation_method)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                country            = excluded.country,
                city               = excluded.city,
                timezone           = excluded.timezone,
                asr_method         = excluded.asr_method,
                calculation_method = excluded.calculation_method,
                notify_loop_active = 0,
                updated_at         = datetime('now')
            """,
            (int(user_id), country, city, timezone, asr_method, calculation_method),
        )
        await self._db.commit()

    async def update_user(self, user_id, **fields):
        """Update individual columns for an existing user."""
        invalid = set(fields) - UPDATABLE_COLUMNS
        if invalid:
            raise ValueError(f"Cannot update columns: {', '.join(sorted(invalid))}")
        if 'notify_loop_active' in fields:
            fields['notify_loop_active'] = int(bool(fields['notify_loop_active']))
        assignments = ', '.join(f"{column} = ?" for column in fields)
        await self._db.execute(
            f"UPDATE user_settings SET {assignments}, updated_at = datetime('now') "
            "WHERE user_id = ?",
            (*fields.values(), int(user_id)),
        )
        await self._db.commit()

    async def get_notify_loop_users(self):
        """Return settings for every user with an active notification loop."""
        async with self._db.execute(
            "SELECT * FROM user_settings WHERE notify_loop_active = 1"
        ) as cursor:
            return [_row_to_settings(row) for row in await cursor.fetchall()]

    async def migrate_from_json(self, json_path):
        """One-time import of the legacy user_settings.json file.

        Existing DB rows win over JSON entries, so re-running is safe.
        The JSON file is renamed to <name>.migrated afterwards.
        """
        if not os.path.exists(json_path):
            return

        with open(json_path, 'r') as f:
            legacy = json.load(f)

        imported = 0
        for user_id, settings in legacy.items():
            try:
                await self._db.execute(
                    """
                    INSERT OR IGNORE INTO user_settings
                        (user_id, country, city, timezone, asr_method,
                         calculation_method, notify_loop_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(user_id),
                        settings["country"],
                        settings["city"],
                        settings.get("timezone") or "UTC",
                        settings.get("asr_method", '1'),
                        settings.get("calculation_method", '2'),
                        int(bool(settings.get("notify_loop_active", False))),
                    ),
                )
                imported += 1
            except (KeyError, ValueError) as e:
                print(f"Skipping malformed legacy entry for user {user_id}: {e}")
        await self._db.commit()

        backup_path = json_path + '.migrated'
        os.replace(json_path, backup_path)
        print(f"Migrated {imported} user(s) from {json_path} (backup: {backup_path})")
