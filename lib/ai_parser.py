"""用 OpenAI 把會議記錄解析成 5W2H 行動事項。"""
from __future__ import annotations

import json

from openai import OpenAI

from .config import DEPARTMENTS, get_openai_api_key


_DEPT_LIST = '、'.join(DEPARTMENTS)


def _build_prompt(text: str, filename: str) -> str:
    return f"""你是一個專業的專案管理助理。請從以下會議記錄中，找出所有需要追蹤的行動事項。

會議記錄檔名：{filename}
會議記錄內容：
{text}

請用JSON格式回傳，格式如下（可以有多個事項）：
{{
  "meeting_date": "會議日期（格式：YYYY-MM-DD，若找不到則填今天日期）",
  "tasks": [
    {{
      "what": "做什麼（任務名稱）",
      "why": "為什麼做（目的）",
      "who_dept": "負責部門（從以下選一個：{_DEPT_LIST}）",
      "who_person": "負責人姓名（若找不到填「待確認」）",
      "where": "執行地點或範圍（若找不到填「總部」）",
      "when_start": "開始日期（格式：YYYY-MM-DD，若找不到填今天日期）",
      "when_end": "截止日期（格式：YYYY-MM-DD，若文件中沒有明確截止日期則填空字串，不要猜測）",
      "how": "執行方式或說明",
      "progress": 0
    }}
  ]
}}

重要規則：
1. 截止日期若文件中沒有明確寫出，請填空字串
2. 年份請以文件中的日期為準，若只有月日沒有年份，請填 2026 年
3. 負責人請填姓名，若只有職稱請填職稱，找不到填「待確認」
4. 只回傳JSON，不要有其他文字。"""


def parse_meeting(text: str, filename: str) -> dict:
    client = OpenAI(api_key=get_openai_api_key())
    resp = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': _build_prompt(text, filename)}],
        temperature=0,
        response_format={'type': 'json_object'},
    )
    raw = resp.choices[0].message.content.strip()
    raw = raw.replace('```json', '').replace('```', '').strip()
    return json.loads(raw)
