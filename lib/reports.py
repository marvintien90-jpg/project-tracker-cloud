"""週報、Line 提醒、Excel 匯出。"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from .config import DEPARTMENTS
from .status import get_status


def generate_weekly_report(tasks: list[dict[str, Any]]) -> str:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    urgent = [t for t in tasks if get_status(t.get('when_end', ''), t.get('progress', 0))[1] in ('red', 'purple')]
    completed = [t for t in tasks if get_status(t.get('when_end', ''), t.get('progress', 0))[1] == 'complete']
    in_progress = [t for t in tasks if get_status(t.get('when_end', ''), t.get('progress', 0))[1] in ('green', 'yellow')]

    dept_summary: dict[str, dict[str, int]] = {}
    for t in tasks:
        dept = t.get('who_dept', '未分類')
        d = dept_summary.setdefault(dept, {'total': 0, 'urgent': 0, 'completed': 0})
        d['total'] += 1
        _, color = get_status(t.get('when_end', ''), t.get('progress', 0))
        if color in ('red', 'purple'):
            d['urgent'] += 1
        if color == 'complete':
            d['completed'] += 1

    lines: list[str] = []
    lines.append('📊 【總部專案週報】')
    lines.append(f"📅 {week_start.strftime('%Y/%m/%d')} ～ {week_end.strftime('%Y/%m/%d')}")
    lines.append(f"產出時間：{datetime.now().strftime('%Y/%m/%d %H:%M')}")
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━━━━')
    lines.append('📋 本週整體概況')
    lines.append('━━━━━━━━━━━━━━━━━━')
    lines.append(f'・總追蹤事項：{len(tasks)} 件')
    lines.append(f'・進行中：{len(in_progress)} 件')
    lines.append(f'・已完成：{len(completed)} 件')
    lines.append(f'・需緊急處理：{len(urgent)} 件')
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━━━━')
    lines.append('🚨 需緊急處理事項')
    lines.append('━━━━━━━━━━━━━━━━━━')
    if urgent:
        for t in urgent:
            status, _ = get_status(t.get('when_end', ''), t.get('progress', 0))
            lines.append(f"・{t.get('what', '')}")
            lines.append(f"  部門：{t.get('who_dept', '')} ｜ 負責人：{t.get('who_person', '')}")
            lines.append(f"  截止：{t.get('when_end', '未設定')} ｜ 狀態：{status}")
            lines.append('')
    else:
        lines.append('✅ 本週無緊急事項')
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━━━━')
    lines.append('🏢 各部門進度摘要')
    lines.append('━━━━━━━━━━━━━━━━━━')
    for dept in DEPARTMENTS:
        if dept in dept_summary:
            s = dept_summary[dept]
            lines.append(f"・{dept}：共 {s['total']} 件｜完成 {s['completed']} 件｜緊急 {s['urgent']} 件")
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━━━━')
    lines.append('請各部門負責人確認進度並回報 🙏')
    return '\n'.join(lines)


def generate_line_message(tasks: list[dict[str, Any]]) -> str:
    today = date.today().strftime('%Y/%m/%d')
    red_tasks: list[dict] = []
    purple_tasks: list[dict] = []
    for t in tasks:
        _, color = get_status(t.get('when_end', ''), t.get('progress', 0))
        if color == 'red':
            red_tasks.append(t)
        elif color == 'purple':
            purple_tasks.append(t)

    out = [f'📋 【總部專案日報 {today}】', '']
    if purple_tasks:
        out.append('🟣 已逾期（請立即處理）')
        for t in purple_tasks:
            out.append(f"・{t.get('what', '')}")
            out.append(f"  負責：{t.get('who_dept', '')} {t.get('who_person', '')}")
            out.append(f"  截止：{t.get('when_end', '未設定')}")
            out.append('')
    if red_tasks:
        out.append('🔴 緊急警示（3天內到期）')
        for t in red_tasks:
            out.append(f"・{t.get('what', '')}")
            out.append(f"  負責：{t.get('who_dept', '')} {t.get('who_person', '')}")
            out.append(f"  截止：{t.get('when_end', '未設定')}")
            out.append('')
    if not purple_tasks and not red_tasks:
        out.append('✅ 今日無緊急或逾期事項！')
    out.append('請相關負責人今日內回報進度 🙏')
    return '\n'.join(out)


def export_to_excel(tasks: list[dict[str, Any]]) -> io.BytesIO:
    rows = []
    for t in tasks:
        status_text, _ = get_status(t.get('when_end', ''), t.get('progress', 0))
        rows.append({
            '任務名稱': t.get('what', ''),
            '目的': t.get('why', ''),
            '負責部門': t.get('who_dept', ''),
            '負責人': t.get('who_person', ''),
            '執行地點': t.get('where', ''),
            '開始日期': t.get('when_start', ''),
            '截止日期': t.get('when_end', ''),
            '執行方式': t.get('how', ''),
            '進度%': t.get('progress', 0),
            '狀態': status_text,
            '來源檔案': t.get('source_file', ''),
            '匯入時間': t.get('imported_at', ''),
        })
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='專案追蹤')
        ws = writer.sheets['專案追蹤']
        for col in ws.columns:
            max_length = max((len(str(c.value)) if c.value else 0) for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_length + 4, 50)
    output.seek(0)
    return output
