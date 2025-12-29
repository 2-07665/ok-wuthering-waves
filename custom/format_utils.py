from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def safe_str_list(values: Iterable[Any]) -> list[str]:
    return [safe_str(value) for value in values]


def bool_label(value: bool) -> str:
    return "是" if value else "否"


def success_label(value: bool) -> str:
    return "成功" if value else "失败"
