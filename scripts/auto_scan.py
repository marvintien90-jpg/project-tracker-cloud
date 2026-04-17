"""自動掃描 Google Drive、AI 解析、寫入 Sheets。

由 GitHub Actions 每小時執行一次（也可本地手動跑驗證）：
    python -m scripts.auto_scan
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

# 讓本檔案能被 `python scripts/auto_scan.py` 直接執行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ai_parser import parse_meeting  # noqa: E402
from lib.config import get_drive_folder_id  # noqa: E402
from lib.drive_client import extract_text, get_drive_service, list_doc_files  # noqa: E402
from lib.sheets_db import (  # noqa: E402
    append_scanned_files, append_tasks, load_scanned_file_ids,
)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    log('🚀 開始自動掃描 Google Drive...')
    try:
        service = get_drive_service()
        folder_id = get_drive_folder_id()
        files = list_doc_files(service, folder_id)
        log(f'📂 共找到 {len(files)} 個檔案')

        scanned = load_scanned_file_ids()
        new_task_count = 0
        new_scanned: list[dict] = []

        for f in files:
            if f['id'] in scanned:
                continue
            log(f'📄 新檔案：{f["name"]}')
            try:
                text = extract_text(service, f['id'], f['mimeType'], f['name'])
                result = parse_meeting(text, f['name'])
                tasks = result.get('tasks', [])
                now = datetime.now().strftime('%Y-%m-%d %H:%M')
                for t in tasks:
                    t['source_file'] = f['name']
                    t['imported_at'] = now
                if tasks:
                    n = append_tasks(tasks)
                    new_task_count += n
                    log(f'  ✅ 匯入 {n} 個事項')
                else:
                    log('  ⚠️ AI 沒有解析出任何事項')
                new_scanned.append({'file_id': f['id'], 'file_name': f['name']})
            except Exception as e:
                log(f'  ❌ 解析失敗：{e}')
                traceback.print_exc()

        if new_scanned:
            append_scanned_files(new_scanned)

        log(f'🎉 完成！本次新增 {new_task_count} 個事項，{len(new_scanned)} 個檔案')
        return 0
    except Exception as e:
        log(f'❌ 掃描整體失敗：{e}')
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
