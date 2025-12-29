from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import requests

from custom.env_vars import env, required_env
from custom.format_utils import safe_str, bool_label, success_label
from custom.gsheet_manager import RunResult, SheetRunConfig
from custom.time_utils import (
    format_duration,
    format_date,
    format_timestamp,
    minutes_until_next_daily,
    now,
    predict_future_stamina,
)

MAILGUN_API_KEY_ENV = "MAILGUN_API_KEY"
MAILGUN_DOMAIN_ENV = "MAILGUN_DOMAIN"
MAILGUN_RECIPIENT_ENV = "MAILGUN_RECIPIENT"
MAILGUN_TEMPLATE_DAILY_ENV = "MAILGUN_TEMPLATE_DAILY"
MAILGUN_TEMPLATE_STAMINA_ENV = "MAILGUN_TEMPLATE_STAMINA"

STATUS_STYLES: dict[str, tuple[str, str]] = {
    "success": ("成功", "#22c55e"),
    "failure": ("失败", "#ef4444"),
    "skipped": ("跳过", "#9ca3af"),
    "needs review": ("需复查", "#f59e0b"),
    "running": ("运行中", "#3b82f6"),
}


def load_mailgun_config() -> tuple[str, str, str]:
    api_key = required_env(MAILGUN_API_KEY_ENV)
    domain = required_env(MAILGUN_DOMAIN_ENV)
    recipient = required_env(MAILGUN_RECIPIENT_ENV)
    return api_key, domain, recipient


def _mailgun_sender(domain: str) -> str:
    return f"OK-WW任务助手 <postmaster@{domain}>"


def _status_info(status: str) -> tuple[str, str]:
    normalized = status.strip().lower()
    label, color = STATUS_STYLES.get(normalized, (status, "#3b82f6"))
    return label, color


def _display_block(value: str) -> str:
    return "block" if value else "none"


def _display_row(value: str) -> str:
    return "table-row" if value else "none"


def send_mailgun_template(
    subject: str,
    template: str,
    variables: Mapping[str, Any],
    *,
    recipient: str | None = None,
    text: str | None = None,
) -> requests.Response:
    api_key, domain, default_recipient = load_mailgun_config()
    payload: dict[str, Any] = {
        "from": _mailgun_sender(domain),
        "to": recipient or default_recipient,
        "subject": subject,
        "template": template,
        "h:X-Mailgun-Variables": json.dumps(variables, ensure_ascii=False),
    }
    if text:
        payload["text"] = text

    response = requests.post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth=("api", api_key),
        data=payload,
        timeout=15,
    )
    return response


def build_daily_template_variables(result: RunResult, sheet_config: SheetRunConfig) -> dict[str, Any]:
    end_time = result.ended_at or now()
    duration_seconds = max(0, int((end_time - result.started_at).total_seconds()))
    duration = format_duration(duration_seconds)
    status_label, status_color = _status_info(result.status)

    if result.stamina_left is not None:
        next_daily_stamina, next_daily_backup = predict_future_stamina(
            result.stamina_left,
            result.backup_stamina_left,
            minutes_until_next_daily(end_time),
        )
    else:
        next_daily_stamina, next_daily_backup = "", ""

    decision = safe_str(result.decision)
    error = safe_str(result.error)
    notes_visible = bool(decision or error)

    daily_complete_label = ""
    if result.daily_points is not None:
        daily_complete_label = "是" if result.daily_points >= 100 else "否"

    sign_in_label = success_label(result.sign_in_success)

    return {
        "title": f"日常任务 · {status_label}",
        "status_color": status_color,
        "started_at": format_timestamp(result.started_at),
        "ended_at": format_timestamp(end_time),
        "duration": duration,
        "stamina_start": safe_str(result.stamina_start),
        "backup_start": safe_str(result.backup_stamina_start),
        "stamina_left": safe_str(result.stamina_left),
        "backup_stamina": safe_str(result.backup_stamina_left),
        "next_daily_stamina": safe_str(next_daily_stamina),
        "next_daily_backup_stamina": safe_str(next_daily_backup),
        "stamina_used": safe_str(result.stamina_used),
        "daily_points": safe_str(result.daily_points),
        "daily_complete_label": daily_complete_label,
        "sign_in_label": sign_in_label,
        "run_daily": bool_label(sheet_config.run_daily),
        "run_nightmare": bool_label(sheet_config.run_nightmare),
        "tacet_name": safe_str(sheet_config.tacet_name),
        "tacet_set1": safe_str(sheet_config.tacet_set1),
        "tacet_set2": safe_str(sheet_config.tacet_set2),
        "notes_display": _display_block("x" if notes_visible else ""),
        "decision_display": _display_row(decision),
        "error_display": _display_row(error),
        "decision": decision,
        "error": error,
    }


def build_stamina_template_variables(result: RunResult, sheet_config: SheetRunConfig) -> dict[str, Any]:
    end_time = result.ended_at or now()
    duration_seconds = max(0, int((end_time - result.started_at).total_seconds()))
    duration = format_duration(duration_seconds)
    status_label, status_color = _status_info(result.status)

    if result.stamina_left is not None:
        next_daily_stamina, next_daily_backup = predict_future_stamina(
            result.stamina_left,
            result.backup_stamina_left,
            minutes_until_next_daily(end_time),
        )
    else:
        next_daily_stamina, next_daily_backup = "", ""

    decision = safe_str(result.decision)
    error = safe_str(result.error)
    notes_visible = bool(decision or error)

    return {
        "title": f"体力任务 · {status_label}",
        "status_color": status_color,
        "started_at": format_timestamp(result.started_at),
        "ended_at": format_timestamp(end_time),
        "duration": duration,
        "stamina_start": safe_str(result.stamina_start),
        "backup_start": safe_str(result.backup_stamina_start),
        "stamina_left": safe_str(result.stamina_left),
        "backup_stamina": safe_str(result.backup_stamina_left),
        "next_daily_stamina": safe_str(next_daily_stamina),
        "next_daily_backup_stamina": safe_str(next_daily_backup),
        "stamina_used": safe_str(result.stamina_used),
        "run_stamina": bool_label(sheet_config.run_stamina),
        "tacet_name": safe_str(sheet_config.tacet_name),
        "tacet_set1": safe_str(sheet_config.tacet_set1),
        "tacet_set2": safe_str(sheet_config.tacet_set2),
        "notes_display": _display_block("x" if notes_visible else ""),
        "decision_display": _display_row(decision),
        "error_display": _display_row(error),
        "decision": decision,
        "error": error,
    }


def _daily_subject(result: RunResult) -> str:
    status_label, _ = _status_info(result.status)
    end_time = result.ended_at or now()
    return f"{format_date(end_time)} 鸣潮日常任务 · {status_label}"


def _daily_text_summary(variables: Mapping[str, Any]) -> str:
    lines = [
        safe_str(variables.get("title", "日常任务报告")),
        f"开始: {safe_str(variables.get('started_at'))}",
        f"结束: {safe_str(variables.get('ended_at'))}",
        f"时长: {safe_str(variables.get('duration'))}",
        f"体力: {safe_str(variables.get('stamina_start'))} -> {safe_str(variables.get('stamina_left'))}",
        f"日常积分: {safe_str(variables.get('daily_points'))}",
        f"库街区签到: {safe_str(variables.get('sign_in_label'))}",
    ]
    decision = safe_str(variables.get("decision"))
    error = safe_str(variables.get("error"))
    if decision:
        lines.append(f"提示: {decision}")
    if error:
        lines.append(f"错误: {error}")
    return "\n".join(line for line in lines if line.strip())


def _stamina_subject(result: RunResult) -> str:
    status_label, _ = _status_info(result.status)
    end_time = result.ended_at or now()
    return f"{format_date(end_time)} 鸣潮体力任务 · {status_label}"


def _stamina_text_summary(variables: Mapping[str, Any]) -> str:
    lines = [
        safe_str(variables.get("title", "体力任务报告")),
        f"开始: {safe_str(variables.get('started_at'))}",
        f"结束: {safe_str(variables.get('ended_at'))}",
        f"时长: {safe_str(variables.get('duration'))}",
        f"体力: {safe_str(variables.get('stamina_start'))} -> {safe_str(variables.get('stamina_left'))}",
        f"体力消耗: {safe_str(variables.get('stamina_used'))}",
    ]
    decision = safe_str(variables.get("decision"))
    error = safe_str(variables.get("error"))
    if decision:
        lines.append(f"提示: {decision}")
    if error:
        lines.append(f"错误: {error}")
    return "\n".join(line for line in lines if line.strip())


def send_daily_run_report(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    template_name: str | None = None,
    subject: str | None = None,
    recipient: str | None = None,
) -> requests.Response:
    template = template_name or env(MAILGUN_TEMPLATE_DAILY_ENV)
    if not template:
        raise RuntimeError("Mailgun daily template missing; set MAILGUN_TEMPLATE_DAILY in environment.")

    variables = build_daily_template_variables(result, sheet_config)
    return send_mailgun_template(
        subject or _daily_subject(result),
        template,
        variables,
        recipient=recipient,
        text=_daily_text_summary(variables),
    )


def send_stamina_run_report(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    template_name: str | None = None,
    subject: str | None = None,
    recipient: str | None = None,
) -> requests.Response:
    template = template_name or env(MAILGUN_TEMPLATE_STAMINA_ENV)
    if not template:
        raise RuntimeError("Mailgun stamina template missing; set MAILGUN_TEMPLATE_STAMINA in environment.")

    variables = build_stamina_template_variables(result, sheet_config)
    return send_mailgun_template(
        subject or _stamina_subject(result),
        template,
        variables,
        recipient=recipient,
        text=_stamina_text_summary(variables),
    )


if __name__ == "__main__":
    pass
