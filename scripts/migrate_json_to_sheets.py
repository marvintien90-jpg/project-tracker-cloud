"""把現有的 ~/Desktop/專案追蹤助理/data/*.json 一次性搬進 Google Sheets。

使用方式（本機執行）：
    1. 先把本地測試用的 secrets 放好（.streamlit/secrets.toml）
    2. python -m scripts.migrate_json_to_sheets
    3. 跑完去 Google Sheet 確認資料

預設讀取路徑：
    ~/Desktop/專案追蹤助理/data/tasks.json
    ~/Desktop/專案追蹤助理/data/scanned_files.json
    ~/Desktop/專案追蹤助理/data/progress_history.json

可用第一個位置參數覆寫資料夾路徑。
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

# 讓本檔能被 `python scripts/migrate_json_to_sheets.py` 直接執行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.sheets_db import (  # noqa: E402
    append_scanned_files, append_tasks, upsert_history,
)

DEFAULT_DATA_DIR = Path.home() / 'Desktop' / '專案追蹤助理' / 'data'


def _read_json(path: Path) -> list | dict | None:
    if not path.exists():
        print(f'⚠️ 找不到檔案：{path}')
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def migrate_tasks(data_dir: Path) -> int:
    raw = _read_json(data_dir / 'tasks.json')
    if not raw:
        return 0
    # 確保每筆都有 task_id
    for t in raw:
        if not t.get('task_id'):
            t['task_id'] = str(uuid.uuid4())
        t['progress'] = int(t.get('progress', 0) or 0)
    n = append_tasks(raw)
    print(f'✅ 匯入 tasks：{n} 筆')
    return n


def migrate_scanned(data_dir: Path) -> int:
    raw = _read_json(data_dir / 'scanned_files.json')
    if not raw:
        return 0
    # 原檔可能是 list[str]（純 file_id）或 list[dict]
    items: list[dict] = []
    if raw and isinstance(raw[0], str):
        items = [{'file_id': fid, 'file_name': ''} for fid in raw]
    else:
        items = [{'file_id': r.get('file_id', r.get('id', '')),
                  'file_name': r.get('file_name', r.get('name', ''))}
                 for r in raw]
    items = [i for i in items if i['file_id']]
    n = append_scanned_files(items)
    print(f'✅ 匯入 scanned_files：{n} 筆')
    return n


def migrate_history(data_dir: Path) -> int:
    raw = _read_json(data_dir / 'progress_history.json')
    if not raw:
        return 0
    count = 0
    for r in raw:
        upsert_history({
            'date': r.get('date', ''),
            'total': int(r.get('total', 0)),
            'completed': int(r.get('completed', 0)),
            'avg_progress': float(r.get('avg_progress', 0)),
            'completion_rate': float(r.get('completion_rate', 0)),
        })
        count += 1
    print(f'✅ 匯入 progress_history：{count} 筆')
    return count


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR
    print(f'📂 來源資料夾：{data_dir}')
    if not data_dir.exists():
        print(f'❌ 找不到資料夾：{data_dir}')
        return 1
    migrate_tasks(data_dir)
    migrate_scanned(data_dir)
    migrate_history(data_dir)
    print('🎉 全部搬遷完成！')
    return 0


if __name__ == '__main__':
    sys.exit(main())
