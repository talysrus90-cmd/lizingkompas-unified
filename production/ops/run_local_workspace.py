"""Single-PC financial workspace launcher. Not production or a customer portal.

Only financial calculations without customer contacts may be entered here.
The server binds to loopback, stores an actual SQLite database under LOCALAPPDATA,
uses a local password and disables all public intake. No auto-start or port
forwarding. For commercial deployment use production Docker/PostgreSQL instead.
"""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys
import webbrowser
import socket
import urllib.request
import json
from threading import Timer

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "production" / "backend"
DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CompassBrokerWorkstation"
PORT = 8766

def main():
    parser = argparse.ArgumentParser(description="Compass local financial workspace")
    parser.add_argument("--layout", choices=("classic","focus","route"), default="route")
    parser.add_argument("--variants", action="store_true",
                        help="Separate shared database for A/B/C, preserving the old workspace")
    args = parser.parse_args()
    data = DATA.parent / "CompassBrokerVariants" if args.variants else DATA
    port = 8768 if args.variants else PORT
    url = f"http://127.0.0.1:{port}/admin/workspace/v/{args.layout}/"
    # Do not start a duplicate server or attach to an unknown service.
    with socket.socket() as probe:
        probe.settimeout(0.5)
        busy = probe.connect_ex(("127.0.0.1",port)) == 0
    if busy:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz",timeout=2) as response:
                health = json.load(response)
            if health.get("service") == "compass-backend-v1" and health.get("workspace_mode") == ("variants" if args.variants else "classic") and health.get("ok"):
                webbrowser.open(url)
                return
        except (OSError,ValueError):
            pass
        raise SystemExit(f"Port {port} is occupied by another or older service. No change made.")
    # Separate process only; never load an existing production environment.
    for key in list(os.environ):
        if key.startswith(("COMPASS_", "DJANGO_", "DATABASE_URL", "DB_")):
            os.environ.pop(key, None)
    data.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        DJANGO_SETTINGS_MODULE="compassapp.workstation_settings",
        DJANGO_SECRET_KEY=secrets.token_urlsafe(64),
        COMPASS_TEST_MODE="1",
        COMPASS_SSH_OPERATOR="1",
        COMPASS_LIVE_INTAKE="no",
        DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost",
        COMPASS_WORKSTATION_DB=str(data / "financial.sqlite3"),
        COMPASS_WORKSTATION_MODE="variants" if args.variants else "classic",
        PYTHONUTF8="1",
    )
    sys.path[:0] = [str(ROOT), str(BACKEND)]
    import django
    django.setup()
    from django.contrib.auth.models import User
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)
    if not User.objects.filter(is_superuser=True,is_active=True).exists():
        print("Создание локального оператора. Логин: operator")
        while True:
            pwd = getpass.getpass("Задайте пароль (от 14 символов): ")
            again = getpass.getpass("Повторите пароль: ")
            if pwd != again:
                print("Пароли не совпадают.")
                continue
            try:
                validate_password(pwd, User(username="operator"))
            except ValidationError as e:
                print("; ".join(e.messages))
                continue
            User.objects.create_superuser(username="operator",password=pwd)
            del pwd, again
            break
    call_command("collectstatic", interactive=False, verbosity=0)
    print("Рабочий финансовый кабинет:",url)
    print("Только на этом ПК. Не вводите персональные данные или договоры.")
    print("Для остановки нажмите Ctrl+C.")
    Timer(1.5, lambda: webbrowser.open(url)).start()
    call_command("runserver", f"127.0.0.1:{port}", use_reloader=False, use_threading=False)

if __name__ == "__main__":
    main()
