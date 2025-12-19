from pathlib import Path
from custom.env_vars import env

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAILGUN_TEMPLATE_DAILY = PROJECT_ROOT / "custom" / "email_templates" / "mailgun_daily.html"
MAILGUN_TEMPLATE_STAMINA = PROJECT_ROOT / "custom" / "email_templates" / "mailgun_stamina.html"


def _load_mailgun_config() -> tuple[str, str, str]:
    api_key = env("MAILGUN_API_KEY")
    domain = env("MAILGUN_DOMAIN")
    recipient = env("MAILGUN_RECIPIENT")
    if api_key and domain and recipient:
        return api_key, domain, recipient
    raise RuntimeError("Mailgun config missing; set MAILGUN_API_KEY/MAILGUN_DOMAIN/MAILGUN_RECIPIENT in environment.")


def send_email_with_online_templates():
    api_key, domain, recipient = _load_mailgun_config()
    data = {
        "from": f"日常任务助手 <postmaster@{domain}>",
        "to": recipient,
        "subject": "Test",
        "text": "This is a test email",
        "template": "daily_task",
        "h:X-Mailgun-Variables": 
            '{"title": "测试标题", "start_at": "2025-12-09 15:30:04", "ended_at": "2025-12-09 15:34:47", "duration": "4m 42s", "":}'
    }
    return requests.post(
		f"https://api.mailgun.net/v3/{domain}/messages",
		auth=("api", api_key),
		data=data)

if __name__ == "__main__":
    send_email_with_online_templates()