from __future__ import annotations

from datetime import datetime
from pathlib import Path

import requests


MAILGUN_CONFIG = Path(__file__).resolve().parent / "credentials" / "mailgun-api.txt"


def load_mailgun_config(path: Path = MAILGUN_CONFIG) -> tuple[str, str, str]:
    with path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    api_key, domain, recipient = lines[:3]
    return api_key, domain, recipient


def send_email(subject: str, body: str, *, config_path: Path = MAILGUN_CONFIG) -> requests.Response:
    api_key, domain, recipient = load_mailgun_config(config_path)
    return requests.post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth=("api", api_key),
        data={
            "from": f"日常任务助手 <postmaster@{domain}>",
            "to": recipient,
            "subject": subject,
            "text": body,
        },
        timeout=15,
    )


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    resp = send_email(f"{today} 测试邮件", "This is a test email.")
    print(f"Status: {resp.status_code}")
