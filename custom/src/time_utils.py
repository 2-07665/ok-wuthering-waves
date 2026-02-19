import datetime as dt
from .env_vars import env

UTC = dt.timezone.utc
LOCAL_TZ = dt.datetime.now().astimezone().tzinfo

DAILY_HOUR = int(env("DAILY_HOUR", "5"))
DAILY_MINUTE = int(env("DAILY_MINUTE", "0"))

def now():
    return dt.datetime.now().astimezone()


# region Time Formatting Utilities
# ---------------------------------
def format_timestamp(value: dt.datetime) -> str:
    """Return a Google Sheets friendly timestamp."""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def format_date(value: dt.datetime) -> str:
    """Return a YYYY-MM-DD date string."""
    return value.strftime("%Y-%m-%d")


def format_duration(total_seconds: float | int) -> str:
    """Convert durations in seconds to the form "4d 3h 2m 30s"."""
    seconds = max(0, int(total_seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
# endregion


# region Stamina Calculation Utilities
# ---------------------------------
STAMINA_CAP = 240
BACKUP_STAMINA_CAP = 480
STAMINA_REGEN_MINUTE = 6
BACKUP_STAMINA_REGEN_MINUTE = 12

DAILYTASK_STAMINA = 180
TACETFARM_STAMINA_UNIT = 60

BEIJING_TZ = dt.timezone(dt.timedelta(hours=8), name="UTC+08")


def predict_future_stamina(stamina: int, backup_stamina: int, minutes: int) -> tuple[int, int]:
    """Predict current/backup stamina after `minutes` of regen."""
    stamina = max(0, min(stamina, STAMINA_CAP))
    backup_stamina = max(0, min(backup_stamina, BACKUP_STAMINA_CAP))
    minutes = max(0, minutes)

    stamina_regen = min(STAMINA_CAP - stamina, minutes // STAMINA_REGEN_MINUTE)
    stamina_after = stamina + stamina_regen
    remaining_minutes = minutes - stamina_regen * STAMINA_REGEN_MINUTE
    backup_stamina_regen = min(BACKUP_STAMINA_CAP - backup_stamina, remaining_minutes // BACKUP_STAMINA_REGEN_MINUTE)
    backup_stamina_after = backup_stamina + backup_stamina_regen
    return stamina_after, backup_stamina_after


def minutes_until_stamina_full(stamina: int) -> int:
    stamina = max(0, min(stamina, STAMINA_CAP))
    return (STAMINA_CAP - stamina) * STAMINA_REGEN_MINUTE


def minutes_until_target_time(
        target_hour: int, 
        target_minute: int, 
        start_time: dt.datetime | None = None) -> int:
    """Compute minutes until the next target time in the Asia/Shanghai timezone (defaults to 24h later)."""

    start_time = start_time if start_time is not None else now()
    # Ensure timezone awareness by setting start_time to local timezone
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    start_time_bj = start_time.astimezone(BEIJING_TZ)

    target = start_time_bj.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= start_time_bj:
        target += dt.timedelta(days=1)
    return int((target - start_time).total_seconds() // 60)


def stamina_after_consume(stamina: int, backup_stamina: int, consume: int) -> tuple[int, int]:
    """Calculate the stamina and backup_stamina left after consuming an amount."""
    tmp = min(stamina, consume)
    stamina -= tmp
    consume -= tmp

    tmp = min(backup_stamina, consume)
    backup_stamina -= tmp

    backup_stamina = backup_stamina if backup_stamina >= 0 else -1

    return stamina, backup_stamina


def calculate_burn(stamina: int | None, 
                   backup_stamina: int | None, 
                   stamina_consume_unit: int = TACETFARM_STAMINA_UNIT,
                   daily_hour: int = DAILY_HOUR, 
                   daily_minute: int = DAILY_MINUTE) -> tuple[bool, int, bool, str]:
    """Return (should run?, burn amount, good?, reason)."""
    if stamina is None:
        return False, 0, False, "无法读取体力，不执行任务"

    stamina = max(0, min(stamina, STAMINA_CAP))
    backup_stamina = backup_stamina if backup_stamina is not None else 0
    backup_stamina = max(0, min(backup_stamina, BACKUP_STAMINA_CAP))

    stamina_future, backup_stamina_future = predict_future_stamina(
        stamina, backup_stamina, minutes_until_target_time(daily_hour, daily_minute)
    )
    stamina_overflow = (backup_stamina_future - backup_stamina) * 2
    stamina_future_raw = stamina_future + stamina_overflow
    if stamina_future_raw <= STAMINA_CAP:
        return False, 0, True, f"下次日常时有 {stamina_future}+{backup_stamina_future} 体力，不会溢出"

    burn_needed = stamina_future_raw - STAMINA_CAP
    burn_needed = (burn_needed + stamina_consume_unit - 1) // stamina_consume_unit * stamina_consume_unit
    available_stamina = stamina // stamina_consume_unit * stamina_consume_unit

    if available_stamina >= burn_needed + stamina_consume_unit:
        return True, available_stamina, False, f"下次日常时会溢出 {stamina_overflow} 体力，过量消耗 {available_stamina}"

    if available_stamina >= burn_needed:
        return True, burn_needed, True, f"下次日常时会溢出 {stamina_overflow} 体力，消耗 {burn_needed}"

    if available_stamina == 0:
        return False, 0, False, f"下次日常时会溢出 {stamina_overflow} 体力，但当前可消耗不足一次任务"
    else:
        return True, available_stamina, False, f"下次日常时会溢出 {stamina_overflow} 体力，但当前仅可消耗 {available_stamina}"
# endregion
