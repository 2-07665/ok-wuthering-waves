import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from ok import Logger

from .env_vars import env, env_bool
from .format_utils import bool_label, safe_str, success_label
from .gsheet_manager import RunResult, SheetRunConfig
logger = Logger.get_logger(__name__)

NOTICE_CHANNEL_ENV = "NOTICE_CHANNEL"
NOTICE_ACCOUNT_ID_ENV = "NOTICE_ACCOUNT_ID"

MAILGUN_API_KEY_ENV = "MAILGUN_API_KEY"
MAILGUN_DOMAIN_ENV = "MAILGUN_DOMAIN"
MAILGUN_RECIPIENT_ENV = "MAILGUN_RECIPIENT"
MAILGUN_TEMPLATE_DAILY_ENV = "MAILGUN_TEMPLATE_DAILY"
MAILGUN_TEMPLATE_STAMINA_ENV = "MAILGUN_TEMPLATE_STAMINA"
MAILGUN_USE_TEMPLATE_ENV = "MAILGUN_USE_TEMPLATE"

WXPUSHER_SPT_ENV = "WXPUSHER_SPT"
WXPUSHER_SIMPLE_PUSH_URL = "https://wxpusher.zjiecode.com/api/send/message/simple-push"

STATUS_STYLES: dict[str, tuple[str, str]] = {
    "success": ("成功", "#22c55e"),
    "failure": ("失败", "#ef4444"),
    "skipped": ("跳过", "#9ca3af"),
    "needs review": ("需复查", "#f59e0b"),
    "running": ("运行中", "#3b82f6"),
}

TEMPLATE_DIR = Path(__file__).resolve().parent / "notice_templates"
_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")


@dataclass(frozen=True)
class NoticeMessage:
    subject: str
    title: str
    text: str
    html: str
    variables: Mapping[str, Any]


def _csv_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _normalize_channel(channel: str) -> str | None:
    normalized = channel.strip().lower()
    aliases = {
        "mailgun": "mailgun",
        "mail": "mailgun",
        "email": "mailgun",
        "wx": "wxpusher",
        "wxpusher": "wxpusher",
    }
    return aliases.get(normalized)


def _notice_channels() -> list[str]:
    raw_channels = env(NOTICE_CHANNEL_ENV)
    values = _csv_values(raw_channels)

    channels: list[str] = []
    for value in values:
        normalized = _normalize_channel(value)
        if normalized is None:
            logger.warning(f"MY-OK-WW: Ignore unsupported notice channel '{value}'")
            continue
        if normalized not in channels:
            channels.append(normalized)
    return channels


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


def _farm_snapshot(sheet_config: SheetRunConfig) -> dict[str, str]:
    which_to_farm = safe_str(sheet_config.which_to_farm).strip()

    if which_to_farm == "无音区":
        detail1_label = "无音区"
        detail1_value = safe_str(sheet_config.tacet_name)
        detail2_label = "套装"
        detail2_value = " / ".join(
            value for value in [safe_str(sheet_config.tacet_set1), safe_str(sheet_config.tacet_set2)] if value
        )
    elif which_to_farm == "凝素领域":
        detail1_label = "凝素领域"
        forgery_name = safe_str(sheet_config.forgery_name)
        forgery_version = safe_str(sheet_config.forgery_version)
        if forgery_name and forgery_version:
            detail1_value = f"{forgery_name} ({forgery_version})"
        else:
            detail1_value = forgery_name or forgery_version
        detail2_label = "武器类型"
        detail2_value = safe_str(sheet_config.forgery_weapon_type)
    elif which_to_farm == "模拟领域":
        detail1_label = "模拟领域"
        detail1_value = safe_str(sheet_config.simulation_material)
        detail2_label = ""
        detail2_value = ""
    else:
        detail1_label = "任务配置"
        detail1_value = ""
        detail2_label = ""
        detail2_value = ""

    detail2_row_display = _display_row("x" if (detail2_label and detail2_value) else "")
    return {
        "which_to_farm": which_to_farm,
        "farm_detail1_label": detail1_label,
        "farm_detail1_value": detail1_value,
        "farm_detail2_label": detail2_label,
        "farm_detail2_value": detail2_value,
        "farm_detail2_row_display": detail2_row_display,
    }


def _account_prefix() -> str:
    account_id = safe_str(env(NOTICE_ACCOUNT_ID_ENV)).strip()
    return f"[{account_id}] " if account_id else ""


def _subject_date(value) -> str:
    return value.strftime("%m-%d")


def _render_template(template_text: str, variables: Mapping[str, Any]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return html.escape(safe_str(variables.get(key)))

    return _PLACEHOLDER_PATTERN.sub(_replace, template_text)


def render_html_template(template_name: str, variables: Mapping[str, Any]) -> str:
    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        raise RuntimeError(f"Notice template missing: {template_path}")
    template_text = template_path.read_text(encoding="utf-8")
    return _render_template(template_text, variables)


def _common_template_variables(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    task_label: str,
    derived: RunResult.Derived | None = None,
) -> tuple[dict[str, Any], RunResult.Derived]:
    derived = derived or result.derive()
    status_label, status_color = _status_info(result.status)
    decision = derived.decision
    error = derived.error
    account_prefix = _account_prefix()
    farm_snapshot = _farm_snapshot(sheet_config)

    return {
        "title": f"{account_prefix}{task_label} · {status_label}",
        "status_color": status_color,
        "started_at": derived.started_at_text,
        "ended_at": derived.ended_at_text,
        "duration": derived.duration_text,
        "stamina_start": safe_str(result.stamina_start),
        "backup_start": safe_str(result.backup_stamina_start),
        "stamina_left": safe_str(result.stamina_left),
        "backup_stamina": safe_str(result.backup_stamina_left),
        "next_daily_stamina": derived.next_daily_stamina,
        "next_daily_backup_stamina": derived.next_daily_backup_stamina,
        "stamina_used": safe_str(result.stamina_used),
        "tacet_name": safe_str(sheet_config.tacet_name),
        "tacet_set1": safe_str(sheet_config.tacet_set1),
        "tacet_set2": safe_str(sheet_config.tacet_set2),
        **farm_snapshot,
        "notes_display": _display_block("x" if derived.notes_visible else ""),
        "decision_display": _display_row(decision),
        "error_display": _display_row(error),
        "decision": decision,
        "error": error,
    }, derived


def build_daily_template_variables(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    derived: RunResult.Derived | None = None,
) -> dict[str, Any]:
    common, _ = _common_template_variables(
        result,
        sheet_config,
        task_label="日常任务",
        derived=derived,
    )
    daily_complete_label = ""
    if result.daily_points is not None:
        daily_complete_label = "是" if result.daily_points >= 100 else "否"

    common.update(
        {
            "daily_points": safe_str(result.daily_points),
            "daily_complete_label": daily_complete_label,
            "sign_in_label": success_label(result.sign_in_success),
            "run_daily": bool_label(sheet_config.run_daily),
            "run_nightmare": bool_label(sheet_config.run_nightmare),
        }
    )
    return common


def build_stamina_template_variables(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    derived: RunResult.Derived | None = None,
) -> dict[str, Any]:
    common, _ = _common_template_variables(
        result,
        sheet_config,
        task_label="体力任务",
        derived=derived,
    )
    common.update({"run_stamina": bool_label(sheet_config.run_stamina)})
    return common


def _daily_subject(result: RunResult, *, derived: RunResult.Derived | None = None) -> str:
    derived = derived or result.derive()
    status_label, _ = _status_info(result.status)
    return f"{_account_prefix()}{_subject_date(derived.end_time)} 鸣潮日常任务 · {status_label}"


def _daily_text_summary(variables: Mapping[str, Any]) -> str:
    lines = [
        safe_str(variables.get("title", "日常任务报告")),
        f"开始: {safe_str(variables.get('started_at'))}",
        f"结束: {safe_str(variables.get('ended_at'))}",
        f"时长: {safe_str(variables.get('duration'))}",
        f"体力: {safe_str(variables.get('stamina_start'))} -> {safe_str(variables.get('stamina_left'))}",
        f"日常点数: {safe_str(variables.get('daily_points'))}",
        f"库街区签到: {safe_str(variables.get('sign_in_label'))}",
        f"梦魇巢穴: {safe_str(variables.get('run_nightmare'))}",
        f"刷什么: {safe_str(variables.get('which_to_farm'))}",
    ]
    detail1_label = safe_str(variables.get("farm_detail1_label"))
    detail1_value = safe_str(variables.get("farm_detail1_value"))
    detail2_label = safe_str(variables.get("farm_detail2_label"))
    detail2_value = safe_str(variables.get("farm_detail2_value"))
    if detail1_label and detail1_value:
        lines.append(f"{detail1_label}: {detail1_value}")
    if detail2_label and detail2_value:
        lines.append(f"{detail2_label}: {detail2_value}")
    decision = safe_str(variables.get("decision"))
    error = safe_str(variables.get("error"))
    if decision:
        lines.append(f"提示: {decision}")
    if error:
        lines.append(f"错误: {error}")
    return "\n".join(line for line in lines if line.strip())


def _stamina_subject(result: RunResult, *, derived: RunResult.Derived | None = None) -> str:
    derived = derived or result.derive()
    status_label, _ = _status_info(result.status)
    return f"{_account_prefix()}{_subject_date(derived.end_time)} 鸣潮体力任务 · {status_label}"


def _stamina_text_summary(variables: Mapping[str, Any]) -> str:
    lines = [
        safe_str(variables.get("title", "体力任务报告")),
        f"开始: {safe_str(variables.get('started_at'))}",
        f"结束: {safe_str(variables.get('ended_at'))}",
        f"时长: {safe_str(variables.get('duration'))}",
        f"体力: {safe_str(variables.get('stamina_start'))} -> {safe_str(variables.get('stamina_left'))}",
        f"体力消耗: {safe_str(variables.get('stamina_used'))}",
        f"刷什么: {safe_str(variables.get('which_to_farm'))}",
    ]
    detail1_label = safe_str(variables.get("farm_detail1_label"))
    detail1_value = safe_str(variables.get("farm_detail1_value"))
    detail2_label = safe_str(variables.get("farm_detail2_label"))
    detail2_value = safe_str(variables.get("farm_detail2_value"))
    if detail1_label and detail1_value:
        lines.append(f"{detail1_label}: {detail1_value}")
    if detail2_label and detail2_value:
        lines.append(f"{detail2_label}: {detail2_value}")
    decision = safe_str(variables.get("decision"))
    error = safe_str(variables.get("error"))
    if decision:
        lines.append(f"提示: {decision}")
    if error:
        lines.append(f"错误: {error}")
    return "\n".join(line for line in lines if line.strip())


def build_daily_notice_message(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    derived: RunResult.Derived | None = None,
) -> NoticeMessage:
    derived = derived or result.derive()
    variables = build_daily_template_variables(result, sheet_config, derived=derived)
    return NoticeMessage(
        subject=_daily_subject(result, derived=derived),
        title=safe_str(variables.get("title", "")),
        text=_daily_text_summary(variables),
        html=render_html_template("daily_task.html", variables),
        variables=variables,
    )


def build_stamina_notice_message(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    derived: RunResult.Derived | None = None,
) -> NoticeMessage:
    derived = derived or result.derive()
    variables = build_stamina_template_variables(result, sheet_config, derived=derived)
    return NoticeMessage(
        subject=_stamina_subject(result, derived=derived),
        title=safe_str(variables.get("title", "")),
        text=_stamina_text_summary(variables),
        html=render_html_template("stamina_task.html", variables),
        variables=variables,
    )


def load_mailgun_config() -> tuple[str, str, str]:
    api_key = env(MAILGUN_API_KEY_ENV, required=True)
    domain = env(MAILGUN_DOMAIN_ENV, required=True)
    recipient = env(MAILGUN_RECIPIENT_ENV, required=True)
    return api_key, domain, recipient


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
    response.raise_for_status()
    return response


def send_mailgun_message(
    subject: str,
    text: str,
    html_text: str,
    *,
    recipient: str | None = None,
) -> requests.Response:
    api_key, domain, default_recipient = load_mailgun_config()
    payload: dict[str, Any] = {
        "from": _mailgun_sender(domain),
        "to": recipient or default_recipient,
        "subject": subject,
        "text": text,
        "html": html_text,
    }
    response = requests.post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth=("api", api_key),
        data=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response


def _load_wxpusher_config() -> str:
    spt = env(WXPUSHER_SPT_ENV, required=True)
    return spt


def _wxpusher_message_payload(message: NoticeMessage) -> dict[str, Any]:
    spt = _load_wxpusher_config()
    return {
        "content": message.html,
        "summary": safe_str(message.subject),
        "contentType": 2,
        "spt": spt,
    }


def send_wxpusher_message(message: NoticeMessage) -> bool:
    payload = _wxpusher_message_payload(message)
    response = requests.post(
        url=WXPUSHER_SIMPLE_PUSH_URL,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("code") != 1000:
        logger.error(f"MY-OK-WW: WxPusher send failed {body}")
        return False
    return True


def _send_via_mailgun(
    message: NoticeMessage,
    *,
    template_name: str | None = None,
    template_env_name: str | None = None,
    recipient: str | None = None,
) -> bool:
    use_template = env_bool(MAILGUN_USE_TEMPLATE_ENV, default=False)
    default_template = env(template_env_name) if template_env_name else None
    template = default_template if template_name is None else template_name

    if use_template:
        if not template:
            raise RuntimeError(
                "Mailgun template mode is enabled, but no template name is set. "
                f"Set {template_env_name} or pass template_name."
            )
        send_mailgun_template(
            subject=message.subject,
            template=template,
            variables=message.variables,
            recipient=recipient,
            text=message.text,
        )
    else:
        send_mailgun_message(
            subject=message.subject,
            text=message.text,
            html_text=message.html,
            recipient=recipient,
        )
    return True


def _send_notice(
    message: NoticeMessage,
    *,
    template_name: str | None = None,
    template_env_name: str | None = None,
    recipient: str | None = None,
) -> bool:
    channels = _notice_channels()
    if not channels:
        return True

    all_ok = True
    for channel in channels:
        try:
            if channel == "mailgun":
                success = _send_via_mailgun(
                    message,
                    template_name=template_name,
                    template_env_name=template_env_name,
                    recipient=recipient,
                )
            elif channel == "wxpusher":
                success = send_wxpusher_message(message)
            else:
                logger.warning(f"MY-OK-WW: Unsupported notice channel '{channel}'")
                success = False
        except Exception as exc:
            logger.error(f"MY-OK-WW: Notice send failed via {channel}", exc)
            success = False

        if not success:
            all_ok = False

    return all_ok


def send_daily_run_report(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    template_name: str | None = None,
    subject: str | None = None,
    recipient: str | None = None,
    derived: RunResult.Derived | None = None,
) -> bool:
    message = build_daily_notice_message(result, sheet_config, derived=derived)
    if subject:
        message = NoticeMessage(
            subject=subject,
            title=message.title,
            text=message.text,
            html=message.html,
            variables=message.variables,
        )
    return _send_notice(
        message,
        template_name=template_name,
        template_env_name=MAILGUN_TEMPLATE_DAILY_ENV,
        recipient=recipient,
    )


def send_stamina_run_report(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    template_name: str | None = None,
    subject: str | None = None,
    recipient: str | None = None,
    derived: RunResult.Derived | None = None,
) -> bool:
    message = build_stamina_notice_message(result, sheet_config, derived=derived)
    if subject:
        message = NoticeMessage(
            subject=subject,
            title=message.title,
            text=message.text,
            html=message.html,
            variables=message.variables,
        )
    return _send_notice(
        message,
        template_name=template_name,
        template_env_name=MAILGUN_TEMPLATE_STAMINA_ENV,
        recipient=recipient,
    )


if __name__ == "__main__":
    pass
