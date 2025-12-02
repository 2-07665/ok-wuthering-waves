from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import requests

ROOT = Path(__file__).resolve().parent
MAILGUN_CONFIG = ROOT / "credentials" / "mailgun-api.txt"
MAILGUN_TEMPLATE_DAILY = ROOT / "templates" / "mailgun_daily.html"
MAILGUN_TEMPLATE_STAMINA = ROOT / "templates" / "mailgun_stamina.html"


def load_mailgun_config(path: Path = MAILGUN_CONFIG) -> tuple[str, str, str]:
    with path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    api_key, domain, recipient = lines[:3]
    return api_key, domain, recipient


def render_local_template(variables: Mapping[str, Any], template_path: Path) -> str:
    """Render the local HTML template by replacing {{placeholders}} with escaped values."""
    raw = template_path.read_text(encoding="utf-8")
    return _replace_placeholders(raw, variables)


def _replace_placeholders(template: str, variables: Mapping[str, Any]) -> str:
    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        val = variables.get(key, "")
        return html.escape("" if val is None else str(val))

    return re.sub(r"{{\s*([\w\-]+)\s*}}", replacer, template)


def send_email(
    subject: str,
    body: str,
    *,
    variables: Mapping[str, Any] | None = None,
    template_path: Path | None = None,
    config_path: Path = MAILGUN_CONFIG,
) -> requests.Response:
    """
    Send an email through Mailgun using only the local HTML template as the HTML part.
    """
    api_key, domain, recipient = load_mailgun_config(config_path)
    variables = variables or {}
    tpl = template_path or MAILGUN_TEMPLATE_DAILY
    html_body = render_local_template(variables, tpl) if variables else tpl.read_text(encoding="utf-8")

    data = {
        "from": f"日常任务助手 <postmaster@{domain}>",
        "to": recipient,
        "subject": subject,
        "text": body,
    }
    if html_body:
        data["html"] = html_body

    response = requests.post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth=("api", api_key),
        data=data,
        timeout=15,
    )
    return response


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")

    print("Sending DAILY test...")
    resp_daily = send_email(
        f"{today} 测试邮件 (daily)",
        "Daily test email.",
        variables={
            "title": "日常任务 · 成功",
        "status_label": "成功",
        "status_color": "#22c55e",
        "run_mode_name": "日常任务",
            "started_at": "2025-11-29 08:00:00",
            "ended_at": "2025-11-29 08:25:30",
            "duration": "25m 30s",
            "stamina_start": "210",
            "backup_start": "120",
            "stamina_used": "180",
            "stamina_left": "30",
            "backup_stamina": "0",
            "daily_points": "120",
            "daily_complete_label": "是",
            "decision": "按表格执行日常任务",
        "tacet_name": "无光之森",
        "tacet_set1": "沉日劫明",
        "tacet_set2": "轻云出月",
            "error": "",
            "notes_display": "none",
            "decision_display": "none",
            "error_display": "none",
        },
        template_path=MAILGUN_TEMPLATE_DAILY,
    )
    print(f"Daily Status: {resp_daily.status_code}")
    try:
        print(f"Daily Response: {resp_daily.json()}")
    except Exception:
        print(f"Daily Response text: {resp_daily.text}")

    print("Sending STAMINA test...")
    resp_stamina = send_email(
        f"{today} 测试邮件 (stamina)",
        "Stamina test email.",
        variables={
            "title": "体力任务 · 成功",
            "status_label": "成功",
            "status_color": "#22c55e",
            "run_mode_name": "体力任务",
            "started_at": "2025-11-29 20:00:00",
            "ended_at": "2025-11-29 20:05:54",
            "duration": "5m 54s",
            "stamina_start": "240",
            "backup_start": "360",
            "stamina_used": "60",
            "stamina_left": "180",
            "backup_stamina": "300",
        "projected_daily_stamina": "210",
        "decision": "测试写入体力",
        "tacet_name": "无光之森",
        "tacet_set1": "沉日劫明",
        "tacet_set2": "轻云出月",
        "run_stamina": "是",
        "error": "",
        "notes_display": "block",
        "decision_display": "block",
        "error_display": "none",
        },
        template_path=MAILGUN_TEMPLATE_STAMINA,
    )
    print(f"Stamina Status: {resp_stamina.status_code}")
    try:
        print(f"Stamina Response: {resp_stamina.json()}")
    except Exception:
        print(f"Stamina Response text: {resp_stamina.text}")
