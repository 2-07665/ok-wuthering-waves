import base64
import datetime as dt
import json
from dataclasses import dataclass
from functools import lru_cache

import gspread
from google.oauth2.service_account import Credentials

from .env_vars import env
from .format_utils import bool_label, safe_str, safe_str_list, success_label
from .time_utils import (
    format_duration,
    format_timestamp,
    minutes_until_target_time,
    now,
    predict_future_stamina,
    DAILY_HOUR,
    DAILY_MINUTE,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

STAMINA_CONSUME_UNIT = 20

@lru_cache(maxsize=1)
def sheet_names() -> dict[str, str]:
    return {
        "CONFIG": env("SHEET_NAME_CONFIG", required=True),
        "DAILY_RUNS": env("SHEET_NAME_DAILY", required=True),
        "STAMINA_RUNS": env("SHEET_NAME_STAMINA", required=True),
        "FAST_FARM_RUNS": env("SHEET_NAME_FASTFARM", required=True),
    }


def _load_service_account_info() -> dict:
    raw_b64 = env("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")
    if raw_b64:
        decoded = base64.b64decode(raw_b64).decode("utf-8")
        return json.loads(decoded)
    raise RuntimeError("Google service account info missing; set GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 in environment.")


def _load_spreadsheet_id() -> str:
    env_value = env("GOOGLE_SHEET_ID")
    if env_value:
        return env_value
    raise RuntimeError("Google sheet ID missing; set GOOGLE_SHEET_ID in environment.")


@dataclass
class SheetRunConfig:
    run_daily: bool = True
    skip_daily_once: bool = False
    exit_game_after_daily: bool = False
    shutdown_after_daily: bool = False
    run_nightmare: bool = False
    
    run_stamina: bool = True
    skip_stamina_once: bool = False
    exit_game_after_stamina: bool = False
    shutdown_after_stamina: bool = False
    
    which_to_farm: str = "无音区"

    tacet_serial: int = 1
    tacet_name: str = ""
    tacet_set1: str = ""
    tacet_set2: str = ""

    forgery_serial: int = 1
    forgery_name: str = ""
    forgery_weapon_type: str = ""
    forgery_version: str = ""

    simulation_material: str = "贝币"


@dataclass
class RunResult:
    task_type: str

    started_at: dt.datetime
    ended_at: dt.datetime | None
    
    status: str

    stamina_start: int | None = None
    backup_stamina_start: int | None = None
    stamina_used: int | None = None
    stamina_left: int | None = None
    backup_stamina_left: int | None = None

    run_nightmare: bool = False

    daily_points: int | None = None
    sign_in_success: bool | None = None

    decision: str | None = None
    error: str | None = None

    def as_row(self, sheet: str) -> list[str]:
        """Convert to a flat row for Sheets."""
        names = sheet_names()
        if self.ended_at is None:
            end = now()
        else:
            end = self.ended_at
        total_seconds = max(0, int(round((end - self.started_at).total_seconds())))
        if self.stamina_left is not None and self.backup_stamina_left is not None:
            next_daily_stamina, next_daily_backup_stamina = predict_future_stamina(
                self.stamina_left, 
                self.backup_stamina_left, 
                minutes_until_target_time(DAILY_HOUR, DAILY_MINUTE, end))
            future_stamina = safe_str_list([next_daily_stamina, next_daily_backup_stamina])
        else:
            future_stamina = ["", ""]

        basic_entry = [format_timestamp(self.started_at), format_timestamp(end), format_duration(total_seconds), self.status]
        stamina_entry = safe_str_list([self.stamina_start, self.backup_stamina_start, self.stamina_used, self.stamina_left, self.backup_stamina_left])
        info_entry = safe_str_list([self.decision, self.error])
        if sheet == names["DAILY_RUNS"]:
            sign_in_entry = [success_label(self.sign_in_success)]
            nest_entry = [bool_label(self.run_nightmare)]
            return  (basic_entry + stamina_entry + [safe_str(self.daily_points)] + future_stamina + sign_in_entry + nest_entry + info_entry)
        if sheet == names["STAMINA_RUNS"]:
            return (basic_entry + stamina_entry + future_stamina + info_entry)
        raise ValueError(f"Unsupported sheet '{sheet}' for result row.")
    
    def fill_stamina_start(self, stamina: int | None, backup_stamina: int | None) -> None:
        self.stamina_start = stamina
        self.backup_stamina_start = backup_stamina

    def fill_stamina_left(self, stamina: int | None, backup_stamina: int | None) -> None:
        self.stamina_left = stamina
        self.backup_stamina_left = backup_stamina

    def fill_stamina_left_from_start(self) -> None:
        self.stamina_left = self.stamina_start
        self.backup_stamina_left = self.backup_stamina_start

    def fill_stamina_used(self) -> None:
        """Calculate and fill stamina_used from start/left totals."""
        if (None in (self.stamina_start, self.backup_stamina_start, self.stamina_left, self.backup_stamina_left)):
            return
        start_total = (self.stamina_start or 0) + (self.backup_stamina_start or 0)
        end_total = (self.stamina_left or 0) + (self.backup_stamina_left or 0)
        consumed = max(0, start_total - end_total)
        self.stamina_used = int(round(consumed / STAMINA_CONSUME_UNIT)) * STAMINA_CONSUME_UNIT


@dataclass
class FastFarmResult:
    started_at: dt.datetime
    ended_at: dt.datetime | None

    status: str

    fight_count: int | None = None
    fight_speed: int | None = None

    echo_number_start: int | None = None
    echo_number_end: int | None = None
    echo_number_gained: int | None = None
    merge_count: int | None = None

    error: str | None = ""

    def as_row(self) -> list[str]:
        """Convert to a flat row for Sheets."""
        if self.ended_at is None:
            end = now()
        else:
            end = self.ended_at
        total_seconds = max(0, int(round((end - self.started_at).total_seconds())))

        if self.fight_count is not None and total_seconds != 0:
            self.fight_speed =  max(0, round(self.fight_count * 3600 / total_seconds))

        self.fill_echo_number_gained()

        basic_entry = [format_timestamp(self.started_at), format_timestamp(end), format_duration(total_seconds), self.status]
        fight_entry = safe_str_list([self.fight_count, self.fight_speed])
        echo_entry = safe_str_list([self.echo_number_start, self.echo_number_end, self.echo_number_gained, self.merge_count])
        info_entry = [safe_str(self.error)]

        return (basic_entry + fight_entry + echo_entry + info_entry)
    
    def fill_echo_number_gained(self) -> None:
        if self.echo_number_start is None or self.echo_number_end is None:
            return
        self.echo_number_gained = max(0, self.echo_number_end - self.echo_number_start)


class GoogleSheetClient:
    def __init__(self):
        self.service_account_info = _load_service_account_info()
        self.spreadsheet_id = _load_spreadsheet_id()
        self.scopes = SCOPES
        self._client: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None

    @property
    def client(self) -> gspread.Client:
        if self._client is None:
            creds = Credentials.from_service_account_info(self.service_account_info, scopes=self.scopes)
            self._client = gspread.authorize(creds)
        return self._client

    @property
    def spreadsheet(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            self._spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        return self._spreadsheet

    def fetch_config_rows(self) -> list[list[str]]:
        return self.spreadsheet.worksheet(sheet_names()["CONFIG"]).get_all_values()

    @staticmethod
    def _get_bool(raw: str) -> bool:
        normalized = raw.strip().lower()
        return normalized in {"true", "1", "yes", "y", "是", "on"}

    # improve later
    def fetch_run_config(self) -> SheetRunConfig:
        rows = self.fetch_config_rows()
        return SheetRunConfig(
            run_daily = self._get_bool(rows[8][1]),
            skip_daily_once = self._get_bool(rows[9][1]),
            exit_game_after_daily = self._get_bool(rows[10][1]),
            shutdown_after_daily = self._get_bool(rows[11][1]),
            run_nightmare = self._get_bool(rows[18][1]),
            run_stamina = self._get_bool(rows[8][3]),
            skip_stamina_once = self._get_bool(rows[9][3]),
            exit_game_after_stamina = self._get_bool(rows[10][3]),
            shutdown_after_stamina = self._get_bool(rows[11][3]),
            which_to_farm = rows[12][1],
            tacet_serial = int(rows[13][3]),
            tacet_name = rows[13][1],
            tacet_set1 = rows[14][1],
            tacet_set2 = rows[14][3],
            forgery_serial = int(rows[15][3]),
            forgery_name = rows[15][1],
            forgery_weapon_type = rows[16][1],
            forgery_version = rows[16][3],
            simulation_material = rows[17][1],
        )
    
    def handle_skip_once(self, task_type: str) -> None:
        ws = self.spreadsheet.worksheet(sheet_names()["CONFIG"])
        if task_type.lower() == "daily":
            ws.update([["FALSE"]], "B10", value_input_option = gspread.utils.ValueInputOption.user_entered)
        if task_type.lower() == "stamina":
            ws.update([["FALSE"]], "D10", value_input_option = gspread.utils.ValueInputOption.user_entered)

    def update_stamina(self, stamina: int, backup_stamina: int, updated_at: dt.datetime) -> None:
        """Update stamina cells on Config sheet (E2 for timestamp, B4/B5 for current values)."""
        ws = self.spreadsheet.worksheet(sheet_names()["CONFIG"])
        ws.update([[updated_at.strftime("%m-%d %H:%M")]], "E2", value_input_option = gspread.utils.ValueInputOption.user_entered)
        ws.update([[stamina], [backup_stamina]], "B4:B5", value_input_option = gspread.utils.ValueInputOption.user_entered)

    def update_stamina_from_run(self, result: RunResult) -> None:
        if result.stamina_left is None:
            return
        else:
            ws = self.spreadsheet.worksheet(sheet_names()["CONFIG"])
            updated_at = result.ended_at if result.ended_at else now()
            backup = result.backup_stamina_left if result.backup_stamina_left else 0
            ws.update([[updated_at.strftime("%m-%d %H:%M")]], "E2", value_input_option = gspread.utils.ValueInputOption.user_entered)
            ws.update([[result.stamina_left], [backup]], "B4:B5", value_input_option = gspread.utils.ValueInputOption.user_entered)
        
    def _sheet_name_for_result(self, task_type: str) -> str:
        names = sheet_names()
        if task_type.lower() == "daily":
            return names["DAILY_RUNS"]
        if task_type.lower() == "stamina":
            return names["STAMINA_RUNS"]
        raise ValueError(f"Unsupported task type: {task_type}")

    def append_run_result(self, result: RunResult) -> None:
        sheet = self._sheet_name_for_result(result.task_type)
        ws = self.spreadsheet.worksheet(sheet)
        ws.append_row(result.as_row(sheet), value_input_option = gspread.utils.ValueInputOption.user_entered)

    def append_fast_farm_result(self, result: FastFarmResult) -> None:
        ws = self.spreadsheet.worksheet(sheet_names()["FAST_FARM_RUNS"])
        ws.append_row(result.as_row(), value_input_option = gspread.utils.ValueInputOption.user_entered)
