from dataclasses import dataclass

import datetime as dt
from custom.time_utils import now, format_timestamp, format_duration, predict_future_stamina, minutes_until_next_daily

from custom.env_vars import env
import base64
import json

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NAME = {"CONFIG": env("SHEET_NAME_CONFIG"), "DAILY_RUNS": env("SHEET_NAME_DAILY"), "STAMINA_RUNS": env("SHEET_NAME_STAMINA"), "FAST_FARM_RUNS": env("SHEET_NAME_FASTFARM")}


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
    exit_game_after_daily: bool = False
    shutdown_after_daily: bool = False
    run_nightmare: bool = False
    
    run_stamina: bool = True
    exit_game_after_stamina: bool = False
    shutdown_after_stamina: bool = False
    
    tacet_serial: int = 1
    tacet_name: str = ""
    tacet_set1: str = ""
    tacet_set2: str = ""


def _to_str(value) -> str:
    return "" if value is None else str(value)
    

def _to_str_list(values: list) -> list[str]:
    return [_to_str(v) for v in values]


def _bool_to_str(value: bool) -> str:
    return "是" if value else "否"


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

    decision: str | None = None
    error: str | None = None

    def as_row(self, sheet: str | None = None) -> list[str]:
        """Convert to a flat row for Sheets."""
        if self.ended_at is None:
            end = now()
        else:
            end = self.ended_at
        total_seconds = max(0, int(round((end - self.started_at).total_seconds())))
        if self.stamina_left is not None:
            next_daily_stamina, next_daily_backup_stamina = predict_future_stamina(self.stamina_left, self.backup_stamina_left, minutes_until_next_daily(end))
            future_stamina = _to_str_list([next_daily_stamina, next_daily_backup_stamina])
        else: future_stamina = ["", ""]

        basic_entry = [format_timestamp(self.started_at), format_timestamp(end), format_duration(total_seconds), self.status]
        stamina_entry = _to_str_list([self.stamina_start, self.backup_stamina_start, self.stamina_used, self.stamina_left, self.backup_stamina_left])
        info_entry = _to_str_list([self.decision, self.error])
        if sheet == SHEET_NAME["DAILY_RUNS"]:
            return  (basic_entry + stamina_entry + [_to_str(self.daily_points)] + future_stamina + [_bool_to_str(self.run_nightmare)]  + info_entry)
        if sheet == SHEET_NAME["STAMINA_RUNS"]:
            return (basic_entry + stamina_entry + future_stamina + info_entry)
        raise ValueError(f"Unsupported sheet '{sheet}' for result row.")
    
    def fill_stamina_used(self) -> None:
        """Calculate and fill stamina_used from start/left totals."""
        if (None in (self.stamina_start, self.backup_stamina_start, self.stamina_left, self.backup_stamina_left)):
            return
        start_total = (self.stamina_start or 0) + (self.backup_stamina_start or 0)
        end_total = (self.stamina_left or 0) + (self.backup_stamina_left or 0)
        consumed = max(0, start_total - end_total)
        self.stamina_used = int(round(consumed / 10.0)) * 10


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

        if self.fight_count is not None:
            self.fight_speed =  max(0, round(self.fight_count * 3600 / total_seconds))

        self.fill_echo_number_gained()

        basic_entry = [format_timestamp(self.started_at), format_timestamp(end), format_duration(total_seconds), self.status]
        fight_entry = _to_str_list([self.fight_count, self.fight_speed])
        echo_entry = _to_str_list([self.echo_number_start, self.echo_number_end, self.echo_number_gained, self.merge_count])
        info_entry = [_to_str(self.error)]

        return (basic_entry + fight_entry + echo_entry + info_entry)
    
    def fill_echo_number_gained(self) -> None:
        if (None in (self.echo_number_start, self.echo_number_end)):
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
        return self.spreadsheet.worksheet(SHEET_NAME["CONFIG"]).get_all_values()

    @staticmethod
    def _get_bool(raw: str) -> bool:
        normalized = raw.strip().lower()
        return normalized in {"true", "1", "yes", "y", "是"}

    def fetch_run_config(self) -> SheetRunConfig:
        rows = self.fetch_config_rows()
        return SheetRunConfig(
            run_daily = self._get_bool(rows[12][1]),
            exit_game_after_daily = self._get_bool(rows[13][1]),
            shutdown_after_daily = self._get_bool(rows[14][1]),
            run_nightmare = self._get_bool(rows[17][1]),
            run_stamina = self._get_bool(rows[12][3]),
            exit_game_after_stamina = self._get_bool(rows[13][3]),
            shutdown_after_stamina = self._get_bool(rows[14][3]),
            tacet_serial = int(rows[15][3]),
            tacet_name = rows[15][1],
            tacet_set1 = rows[16][1],
            tacet_set2 = rows[16][3])
    
    def update_stamina(self, stamina: int, backup_stamina: int, updated_at: dt.datetime) -> None:
        """Update stamina cells on Config sheet (E2 for timestamp, B4/B5 for current values)."""
        ws = self.spreadsheet.worksheet(SHEET_NAME["CONFIG"])
        ws.update([[updated_at.strftime("%m-%d %H:%M")]], "E2", value_input_option = gspread.utils.ValueInputOption.user_entered)
        ws.update([[stamina], [backup_stamina]], "B4:B5", value_input_option = gspread.utils.ValueInputOption.user_entered)

    def update_stamina_from_run(self, result: RunResult) -> None:
        if result.stamina_left is None:
            return
        else:
            ws = self.spreadsheet.worksheet(SHEET_NAME["CONFIG"])
            updated_at = result.ended_at if result.ended_at else now()
            backup = result.backup_stamina_left if result.backup_stamina_left else 0
            ws.update([[updated_at.strftime("%m-%d %H:%M")]], "E2", value_input_option = gspread.utils.ValueInputOption.user_entered)
            ws.update([[result.stamina_left], [backup]], "B4:B5", value_input_option = gspread.utils.ValueInputOption.user_entered)
        

    def _sheet_name_for_result(self, task_type: str) -> str:
        if task_type.lower() == "daily":
            return SHEET_NAME["DAILY_RUNS"]
        if task_type.lower() == "stamina":
            return SHEET_NAME["STAMINA_RUNS"]
        raise ValueError(f"Unsupported task type: {task_type}")

    def append_run_result(self, result: RunResult) -> None:
        sheet = self._sheet_name_for_result(result.task_type)
        ws = self.spreadsheet.worksheet(sheet)
        ws.append_row(result.as_row(sheet), value_input_option = gspread.utils.ValueInputOption.user_entered)

    def append_fast_farm_result(self, result: FastFarmResult) -> None:
        ws = self.spreadsheet.worksheet(SHEET_NAME["FAST_FARM_RUNS"])
        ws.append_row(result.as_row(), value_input_option = gspread.utils.ValueInputOption.user_entered)


# region Test Area
if __name__ == "__main__":
    run_update_stamina_example = False
    run_append_daily_task_row = False
    run_append_stamina_task_row = False
    run_append_fast_farm_task_row = True

    some_time = now()

    sheet = GoogleSheetClient()

    print(sheet.fetch_run_config())

    if run_update_stamina_example:
        sheet.update_stamina(30, 20, some_time)
        print(f"Updated stamina values on {SHEET_NAME['CONFIG']}.")

    if run_append_daily_task_row:
        fake_result = RunResult(
            task_type = "daily",

            started_at = some_time - dt.timedelta(minutes=8),
            ended_at = some_time,
            status = "manual-test",

            stamina_start = 210,
            backup_stamina_start = 20,
            stamina_used = 180,
            stamina_left = 30,
            backup_stamina_left = 20,

            daily_points = 120,

            decision = "测试写入日常任务结果",
        )
        sheet.append_run_result(fake_result)
        print(f"Appended a test row to {SHEET_NAME['DAILY_RUNS']}.")

    if run_append_stamina_task_row:
        fake_result = RunResult(
            task_type = "stamina",

            started_at = some_time - dt.timedelta(minutes=8),
            ended_at = some_time,
            status = "manual-test",

            stamina_start = 110,
            backup_stamina_start = 20,
            stamina_used = 60,
            stamina_left = 50,
            backup_stamina_left = 20,

            decision = "测试写入体力任务结果",
        )
        sheet.append_run_result(fake_result)
        print(f"Appended a test row to {SHEET_NAME['STAMINA_RUNS']}.")

    if run_append_fast_farm_task_row:
        fake_result = FastFarmResult(
            started_at = some_time - dt.timedelta(minutes=60),
            ended_at = some_time,
            status = "manual-test",

            fight_count = 360,
            fight_speed = 360,

            echo_number_start=1000,
            echo_number_end=1800,
            merge_count = 0
        )
        fake_result.fill_echo_number_gained()
        sheet.append_fast_farm_result(fake_result)
        print(f"Appended a test row to {SHEET_NAME['FAST_FARM_RUNS']}.")

#endregion
