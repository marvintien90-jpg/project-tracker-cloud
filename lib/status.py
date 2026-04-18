"""燈號規則與時間計算。"""
from __future__ import annotations

from datetime import date, datetime


def get_status(when_end: str, progress: int) -> tuple[str, str]:
    """回傳 (顯示文字, 顏色 key)。

    顏色 key: complete / purple / red / yellow / green
    """
    if progress >= 100:
        return '已完成', 'complete'
    if not when_end:
        return '進行中', 'green'
    try:
        end = datetime.strptime(when_end, '%Y-%m-%d').date()
    except ValueError:
        return '進行中', 'green'
    days_left = (end - date.today()).days
    if days_left < 0:
        return f'已逾期 {abs(days_left)} 天', 'purple'
    if days_left <= 3:
        return f'緊急 · 剩 {days_left} 天', 'red'
    if days_left <= 7:
        return f'注意 · 剩 {days_left} 天', 'yellow'
    return f'正常 · 剩 {days_left} 天', 'green'


# 保留 dict 以維持 app.py 匯入（不再使用 emoji）
COLOR_EMOJI = {
    'purple': '', 'red': '', 'yellow': '', 'green': '', 'complete': '',
}
