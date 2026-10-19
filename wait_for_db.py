"""Block until the configured database accepts connections (used by entrypoint.sh)."""

import os
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection  # noqa: E402

MAX_RETRIES = 60


def main() -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            print("Database is available.")
            return
        except Exception as exc:  # noqa: BLE001 - any failure means "not ready yet"
            print(
                f"Database unavailable ({exc.__class__.__name__}). "
                f"Retrying ({attempt}/{MAX_RETRIES})..."
            )
            time.sleep(1)
    raise SystemExit("Database never became available.")


if __name__ == "__main__":
    main()
