import datetime as dt

def predict_future_stamina(current: int, backup: int, minutes: int) -> tuple[int, int]:
    """Predict current/back-up stamina after `minutes` of regen."""
    current = min(current, 240)
    backup = min(backup, 480)
    gain_current = min(max(0, 240 - current), minutes // 6)
    current_after = current + gain_current
    remaining_minutes = max(0, minutes - gain_current * 6)
    gain_backup = min(max(0, 480 - backup), remaining_minutes // 12)
    backup_after = backup + gain_backup
    return current_after, backup_after


def minutes_until_next_daily(target_hour: int, target_minute: int) -> int:
    """Compute minutes until the next daily run target time (defaults to 24h later)."""
    now = dt.datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return int((target - now).total_seconds() // 60)

def calculate_burn(current: int | None, backup: int | None, minutes_to_next: int) -> tuple[bool, int, int | None, str]:
    """Return (should_run, burn_amount, projected_total, reason)."""
    if current is None:
        return True, 60, None, "无法读取体力，按默认消耗一次"
    if backup is None:
        backup = 0
    current = max(0, current)
    backup = max(0, backup)
    future_current, future_backup = predict_future_stamina(current, backup, minutes_to_next)
    future_total = future_current + 2 * future_backup
    if future_total <= 240:
        return False, 0, future_total, f"预计至下次日常有 {future_total} 体力，不会溢出，无需体力任务"

    target_total = 190
    burn_needed = max(0, future_total - target_total)
    available = current + backup
    burn = min(available, burn_needed)
    burn = (burn // 60) * 60  # align to task spend units
    if burn < 60:
        return False, 0, future_total, f"预计至下次日常有 {future_total} 体力，当前可消耗体力不足 60"
    return True, burn, future_total - burn, f"预计至下次日常有 {future_total} 体力，消耗至约 {future_total - burn}"

print(minutes_until_next_daily(17,7))
print(predict_future_stamina(98,0,minutes_until_next_daily(17,7)))
print(calculate_burn(98,0,minutes_until_next_daily(17,7)))