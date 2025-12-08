from __future__ import annotations

import base64
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import gspread
from google.oauth2.service_account import Credentials

from custom.env_vars import env_var

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOOGLE_SERVICE_ACCOUNT_JSON_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"
GOOGLE_SERVICE_ACCOUNT_JSON_B64_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON_BASE64"
GOOGLE_SHEET_ID_ENV = "GOOGLE_SHEET_ID"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]


def _load_spreadsheet_id() -> str:
    env_value = env_var(GOOGLE_SHEET_ID_ENV)
    if env_value:
        return env_value.strip()
    raise RuntimeError("Google Sheet ID missing; set GOOGLE_SHEET_ID in environment.")


def _load_service_account_info() -> dict:
    raw_json = env_var(GOOGLE_SERVICE_ACCOUNT_JSON_ENV)
    if raw_json:
        return json.loads(raw_json)

    raw_b64 = env_var(GOOGLE_SERVICE_ACCOUNT_JSON_B64_ENV)
    if raw_b64:
        decoded = base64.b64decode(raw_b64).decode("utf-8")
        return json.loads(decoded)

    raise RuntimeError("Google service account missing; set GOOGLE_SERVICE_ACCOUNT_JSON(_BASE64) in environment.")


SPREADSHEET_ID = _load_spreadsheet_id()

CONFIG_SHEET = "Config"
DAILY_RUNS_SHEET = "DailyRuns"
STAMINA_RUNS_SHEET = "StaminaRuns"
FAST_FARM_SHEET = "5to1"


@dataclass
class SheetRunConfig:
    run_daily: bool
    run_stamina: bool
    run_nightmare: bool
    tacet_serial: int
    shutdown_after_daily: bool = False
    shutdown_after_stamina: bool = False
    tacet_name: str = ""
    tacet_set1: str = ""
    tacet_set2: str = ""

@dataclass
class RunResult:
    started_at: dt.datetime
    ended_at: dt.datetime | None
    task_type: str
    status: str
    stamina_start: int | None = None
    backup_start: int | None = None
    projected_daily_stamina: int | None = None
    daily_points: int | None = None
    stamina_used: int | None = None
    stamina_left: int | None = None
    backup_stamina: int | None = None
    decision: str | None = None
    error: str | None = None

    def as_row(self, sheet: str | None = None) -> List[str]:
        """Convert to a flat row for Sheets."""
        end = self.ended_at or dt.datetime.now()
        total_seconds = max(0, int(round((end - self.started_at).total_seconds())))
        info = self._info_text()
        if sheet == DAILY_RUNS_SHEET:
            return [
                _format_timestamp(self.started_at),
                _format_timestamp(end),
                _format_duration(total_seconds),
                self.status,
                "" if self.stamina_start is None else str(self.stamina_start),
                "" if self.backup_start is None else str(self.backup_start),
                "" if self.daily_points is None else str(self.daily_points),
                "" if self.stamina_used is None else str(self.stamina_used),
                "" if self.stamina_left is None else str(self.stamina_left),
                "" if self.backup_stamina is None else str(self.backup_stamina),
                info,
            ]
        if sheet == STAMINA_RUNS_SHEET:
            return [
                _format_timestamp(self.started_at),
                _format_timestamp(end),
                _format_duration(total_seconds),
                self.status,
                "" if self.stamina_start is None else str(self.stamina_start),
                "" if self.backup_start is None else str(self.backup_start),
                "" if self.stamina_used is None else str(self.stamina_used),
                "" if self.stamina_left is None else str(self.stamina_left),
                "" if self.backup_stamina is None else str(self.backup_stamina),
                "" if self.projected_daily_stamina is None else str(self.projected_daily_stamina),
                info,
            ]
        raise ValueError(f"Unsupported sheet '{sheet}' for result row.")

    def _info_text(self) -> str:
        parts: list[str] = []
        if self.decision:
            parts.append(f"Decision: {self.decision}")
        if self.error:
            parts.append(f"Error: {self.error}")
        return "; ".join(parts)


@dataclass
class FastFarmResult:
    started_at: dt.datetime
    ended_at: dt.datetime
    status: str
    fight_count: int
    fight_speed: int
    merge_count: int
    error: str = ""

    def as_row(self) -> List[str]:
        duration_seconds = max(0, int(round((self.ended_at - self.started_at).total_seconds())))
        return [
            _format_timestamp(self.started_at),
            _format_timestamp(self.ended_at),
            _format_duration_hours_minutes(duration_seconds),
            self.status,
            self.fight_count,
            self.fight_speed,
            self.merge_count,
            self.error,
        ]


class GoogleSheetClient:
    def __init__(
        self,
        *,
        service_account_info: dict | None = None,
        spreadsheet_id: str | None = None,
        scopes=SCOPES,
    ):
        self.service_account_info = service_account_info
        self.spreadsheet_id = spreadsheet_id or SPREADSHEET_ID
        self.scopes = list(scopes)
        self._client: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None
        self._loaded_service_account_info: dict | None = None

    @property
    def client(self) -> gspread.Client:
        if self._client is None:
            creds = Credentials.from_service_account_info(
                self._get_service_account_info(),
                scopes=self.scopes,
            )
            self._client = gspread.authorize(creds)
        return self._client

    @property
    def spreadsheet(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            self._spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        return self._spreadsheet

    def fetch_config_rows(self) -> List[List[str]]:
        return self.spreadsheet.worksheet(CONFIG_SHEET).get_all_values()

    def fetch_run_config(self) -> SheetRunConfig:
        rows = self.fetch_config_rows()
        pairs = _rows_to_pairs(rows)
        run_daily = _get_bool(pairs, {"日常任务"})
        run_stamina = _get_bool(pairs, {"体力任务"})
        tacet_serial = _get_int(pairs, {"序号"}, default=1)
        run_nightmare = _get_bool(pairs, {"梦魇巢穴"})
        shutdown_after_daily = _get_bool(pairs, {"日常后关机"})
        shutdown_after_stamina = _get_bool(pairs, {"体力后关机"})
        tacet_name = _get_str(pairs, {"无音区选择"})
        tacet_set1 = _get_str(pairs, {"套装1"})
        tacet_set2 = _get_str(pairs, {"套装2"})
        return SheetRunConfig(
            run_daily=run_daily,
            run_stamina=run_stamina,
            run_nightmare=run_nightmare,
            tacet_serial=tacet_serial,
            shutdown_after_daily=shutdown_after_daily,
            shutdown_after_stamina=shutdown_after_stamina,
            tacet_name=tacet_name,
            tacet_set1=tacet_set1,
            tacet_set2=tacet_set2,
        )

    def update_stamina(self, current: int, backup: int, updated_at: dt.datetime) -> None:
        """Update stamina cells on Config sheet (E2 for timestamp, B4/B5 for current values)."""
        ws = self.spreadsheet.worksheet(CONFIG_SHEET)
        ws.update([[updated_at.strftime("%m-%d %H:%M")]], "E2", value_input_option="USER_ENTERED")
        ws.update([[current], [backup]], "B4:B5", value_input_option="USER_ENTERED")

    def append_run_result(self, result: RunResult) -> None:
        sheet = self._sheet_name_for_result(result.task_type)
        ws = self.spreadsheet.worksheet(sheet)
        ws.append_row(result.as_row(sheet), value_input_option="USER_ENTERED")

    def append_fast_farm_result(self, result: FastFarmResult) -> None:
        ws = self.spreadsheet.worksheet(FAST_FARM_SHEET)
        ws.append_row(result.as_row(), value_input_option="USER_ENTERED")

    def _get_service_account_info(self) -> dict:
        if self._loaded_service_account_info is None:
            if self.service_account_info is not None:
                self._loaded_service_account_info = dict(self.service_account_info)
            else:
                self._loaded_service_account_info = _load_service_account_info()
        return self._loaded_service_account_info

    def _sheet_name_for_result(self, task_type: str) -> str:
        if task_type.lower() == "daily":
            return DAILY_RUNS_SHEET
        if task_type.lower() == "stamina":
            return STAMINA_RUNS_SHEET
        raise ValueError(f"Unsupported task type: {task_type}")


def _rows_to_pairs(rows: Iterable[Sequence[str]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in rows:
        for idx in range(0, len(row), 2):
            key = (row[idx] or "").strip()
            if not key:
                continue
            val = (row[idx + 1] if idx + 1 < len(row) else "").strip()
            pairs.append((key, val))
    return pairs


def _format_timestamp(value: dt.datetime) -> str:
    """Return a Google Sheets friendly timestamp."""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(total_seconds: int) -> str:
    """Return durations like '1m 30s' instead of decimal minutes."""
    seconds = max(0, int(total_seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _format_duration_hours_minutes(total_seconds: int) -> str:
    """Return durations like '1h 05m' for fast-farm runs."""
    seconds = max(0, int(total_seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"


def _get_bool(pairs: list[tuple[str, str]], names: set[str], default: bool = False) -> bool:
    for key, val in pairs:
        if key in names:
            normalized = str(val).strip().lower()
            return normalized in {"true", "1", "yes", "y", "是"}
    return default


def _get_int(pairs: list[tuple[str, str]], names: set[str], default: int) -> int:
    for key, val in pairs:
        if key in names:
            try:
                return int(val)
            except ValueError:
                return default
    return default


def _get_str(pairs: list[tuple[str, str]], names: set[str], default: str = "") -> str:
    for key, val in pairs:
        if key in names:
            return str(val).strip()
    return default


if __name__ == "__main__":
    sheet = GoogleSheetClient()

    print("Config rows snapshot:")
    print(sheet.fetch_config_rows())
    config = sheet.fetch_run_config()
    print("Fetched configuration:")
    print(json.dumps(config.__dict__, ensure_ascii=False, indent=2))

    # Flip these to True when you want to manually exercise write paths.
    run_append_daily = False
    run_append_stamina = False
    run_update_stamina_example = False

    now = dt.datetime.now()

    if run_append_daily:
        fake_result = RunResult(
            started_at=now - dt.timedelta(minutes=8),
            ended_at=now,
            task_type="daily",
            status="manual-test",
            stamina_start=210,
            backup_start=120,
            daily_points=120,
            stamina_used=180,
            stamina_left=30,
            backup_stamina=0,
            decision="测试写入日常",
            error=None,
        )
        sheet.append_run_result(fake_result)
        print("Appended a test row to DailyRuns.")

    if run_append_stamina:
        fake_result = RunResult(
            started_at=now - dt.timedelta(minutes=5),
            ended_at=now,
            task_type="stamina",
            status="manual-test",
            stamina_start=240,
            backup_start=360,
            stamina_used=60,
            stamina_left=180,
            backup_stamina=300,
            projected_daily_stamina=210,
            decision="测试写入体力",
            error=None,
        )
        sheet.append_run_result(fake_result)
        print("Appended a test row to StaminaRuns.")

    if run_update_stamina_example:
        sheet.update_stamina(120, 0, dt.datetime.now())
        print("Updated stamina values on Config.")
