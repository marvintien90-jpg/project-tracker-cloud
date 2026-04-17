"""Google Sheets 當資料庫的 CRUD 介面。

設計：
  - 每個 sheet 第一列是欄位 header
  - tasks 用 task_id (uuid) 作為主鍵
  - scanned_files 用 file_id 作為主鍵
  - progress_history 用 date 作為主鍵
"""
from __future__ import annotations

import uuid
from datetime import datetime
from functools import lru_cache
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from .config import (
    DRIVE_SCOPES, HISTORY_COLUMNS, HISTORY_SHEET, SCANNED_COLUMNS,
    SCANNED_SHEET, TASK_COLUMNS, TASKS_SHEET,
    get_service_account_info, get_spreadsheet_id,
)


# ============================================================
# 連線
# ============================================================
@lru_cache(maxsize=1)
def _get_client() -> gspread.Client:
    info = get_service_account_info()
    creds = Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
    return gspread.authorize(creds)


@lru_cache(maxsize=1)
def _get_spreadsheet() -> gspread.Spreadsheet:
    client = _get_client()
    return client.open_by_key(get_spreadsheet_id())


def _get_or_create_worksheet(name: str, columns: list[str]) -> gspread.Worksheet:
    sh = _get_spreadsheet()
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=1000, cols=max(len(columns), 10))
        ws.update('A1', [columns])
        return ws
    # 確認 header
    headers = ws.row_values(1)
    if headers != columns:
        ws.update('A1', [columns])
    return ws


# ============================================================
# 通用：把整張表讀成 list[dict]
# ============================================================
def _read_all(ws: gspread.Worksheet, columns: list[str]) -> list[dict[str, Any]]:
    rows = ws.get_all_records(expected_headers=columns)
    out: list[dict[str, Any]] = []
    for r in rows:
        d = {c: r.get(c, '') for c in columns}
        out.append(d)
    return out


# ============================================================
# tasks
# ============================================================
def load_tasks() -> list[dict[str, Any]]:
    ws = _get_or_create_worksheet(TASKS_SHEET, TASK_COLUMNS)
    rows = _read_all(ws, TASK_COLUMNS)
    # progress 統一轉 int
    for r in rows:
        try:
            r['progress'] = int(r.get('progress') or 0)
        except (ValueError, TypeError):
            r['progress'] = 0
    return rows


def _task_to_row(task: dict[str, Any]) -> list[Any]:
    return [task.get(c, '') for c in TASK_COLUMNS]


def append_tasks(new_tasks: list[dict[str, Any]]) -> int:
    """新增一批 tasks，回傳新增筆數。會自動補 task_id / updated_at。"""
    if not new_tasks:
        return 0
    ws = _get_or_create_worksheet(TASKS_SHEET, TASK_COLUMNS)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    rows = []
    for t in new_tasks:
        if not t.get('task_id'):
            t['task_id'] = str(uuid.uuid4())
        if not t.get('imported_at'):
            t['imported_at'] = now
        t['updated_at'] = now
        rows.append(_task_to_row(t))
    ws.append_rows(rows, value_input_option='USER_ENTERED')
    return len(rows)


def update_task(task: dict[str, Any]) -> bool:
    """根據 task_id 找到對應 row 整列覆寫。"""
    if not task.get('task_id'):
        raise ValueError('task 缺少 task_id，無法更新')
    ws = _get_or_create_worksheet(TASKS_SHEET, TASK_COLUMNS)
    ids = ws.col_values(TASK_COLUMNS.index('task_id') + 1)  # 含 header
    try:
        idx = ids.index(task['task_id'])  # 0-based 含 header
    except ValueError:
        return False
    row_num = idx + 1  # gspread 1-based
    if row_num == 1:
        return False  # 不可能更新 header
    task['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    ws.update(f'A{row_num}', [_task_to_row(task)], value_input_option='USER_ENTERED')
    return True


def delete_task(task_id: str) -> bool:
    if not task_id:
        return False
    ws = _get_or_create_worksheet(TASKS_SHEET, TASK_COLUMNS)
    ids = ws.col_values(TASK_COLUMNS.index('task_id') + 1)
    try:
        idx = ids.index(task_id)
    except ValueError:
        return False
    ws.delete_rows(idx + 1)
    return True


# ============================================================
# scanned_files
# ============================================================
def load_scanned_file_ids() -> set[str]:
    ws = _get_or_create_worksheet(SCANNED_SHEET, SCANNED_COLUMNS)
    rows = _read_all(ws, SCANNED_COLUMNS)
    return {r['file_id'] for r in rows if r.get('file_id')}


def append_scanned_files(items: list[dict[str, Any]]) -> int:
    """items: [{'file_id':..., 'file_name':...}]"""
    if not items:
        return 0
    ws = _get_or_create_worksheet(SCANNED_SHEET, SCANNED_COLUMNS)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    rows = [[i.get('file_id', ''), i.get('file_name', ''), now] for i in items]
    ws.append_rows(rows, value_input_option='USER_ENTERED')
    return len(rows)


# ============================================================
# progress_history
# ============================================================
def load_history() -> list[dict[str, Any]]:
    ws = _get_or_create_worksheet(HISTORY_SHEET, HISTORY_COLUMNS)
    rows = _read_all(ws, HISTORY_COLUMNS)
    for r in rows:
        for k in ('total', 'completed'):
            try:
                r[k] = int(r.get(k) or 0)
            except (ValueError, TypeError):
                r[k] = 0
        for k in ('avg_progress', 'completion_rate'):
            try:
                r[k] = float(r.get(k) or 0)
            except (ValueError, TypeError):
                r[k] = 0.0
    return rows


def upsert_history(entry: dict[str, Any]) -> None:
    """同一天只記一次：若 date 已存在就覆寫，否則 append。"""
    ws = _get_or_create_worksheet(HISTORY_SHEET, HISTORY_COLUMNS)
    dates = ws.col_values(1)  # 含 header
    row = [entry.get(c, '') for c in HISTORY_COLUMNS]
    if entry['date'] in dates:
        idx = dates.index(entry['date'])
        ws.update(f'A{idx + 1}', [row], value_input_option='USER_ENTERED')
    else:
        ws.append_row(row, value_input_option='USER_ENTERED')


def clear_caches() -> None:
    """讓下次 _get_client/_get_spreadsheet 重新連線（給測試或 rerun 用）。"""
    _get_client.cache_clear()
    _get_spreadsheet.cache_clear()
