"""總部專案進度追蹤助理 — 雲端版。

部署：Streamlit Community Cloud
資料庫：Google Sheets（透過 Service Account）
AI 解析：OpenAI gpt-4o-mini
背景掃描：GitHub Actions（每小時）
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu

from lib.brand import COLORS, apply_brand
from lib.config import DEPARTMENTS
from lib.dashboard import compute_metrics, render_ai_summary, render_focus_cards, render_hero_kpis
from lib.drive_client import extract_text, extract_text_from_url, get_drive_service, list_doc_files
from lib.ai_parser import parse_meeting
from lib.reports import export_to_excel, generate_line_message, generate_weekly_report
from lib.sheets_db import (
    append_tasks, append_scanned_files, delete_task, get_setting,
    load_history, load_scanned_file_ids, load_tasks,
    set_setting, update_task, upsert_history,
)
from lib.status import COLOR_EMOJI, get_status

st.set_page_config(
    page_title='總部專案追蹤助理',
    page_icon='static/favicon.svg',
    layout='wide',
    initial_sidebar_state='expanded',
    menu_items={
        'About': '嗑肉石鍋總部專案進度追蹤助理 — 雲端版 v1.1',
    },
)
apply_brand()


# ============================================================
# 資料載入（cache 5 分鐘，避免每次互動都打 Sheets API）
# ============================================================
@st.cache_data(ttl=300)
def cached_tasks() -> list[dict]:
    return load_tasks()


@st.cache_data(ttl=300)
def cached_history() -> list[dict]:
    return load_history()


def refresh_data() -> None:
    cached_tasks.clear()
    cached_history.clear()


def record_daily_progress(tasks: list[dict]) -> None:
    if not tasks:
        return
    today_str = date.today().strftime('%Y-%m-%d')
    history = cached_history()
    if any(h.get('date') == today_str for h in history):
        return
    total = len(tasks)
    completed = sum(1 for t in tasks if int(t.get('progress', 0)) >= 100)
    avg_progress = sum(int(t.get('progress', 0)) for t in tasks) / total
    upsert_history({
        'date': today_str,
        'total': total,
        'completed': completed,
        'avg_progress': round(avg_progress, 1),
        'completion_rate': round(completed / total * 100, 1),
    })
    cached_history.clear()


# ============================================================
# 主流程
# ============================================================
try:
    tasks = cached_tasks()
except Exception as e:
    st.markdown(f"""
    <div style="max-width:600px; margin:60px auto; background:white; border-radius:18px;
                padding:32px; box-shadow:0 8px 24px rgba(0,0,0,0.08); text-align:center;">
      <div style="font-size:3rem; line-height:1;"><i class="bi bi-exclamation-triangle" style="color:#DC2626;"></i></div>
      <div style="font-size:1.1rem; font-weight:700; margin-top:12px; color:#DC2626;">無法連線 Google Sheets</div>
      <div style="color:#6B7280; margin-top:8px; font-size:0.9rem;">{type(e).__name__}: {str(e)[:200]}</div>
      <div style="color:#6B7280; margin-top:16px; font-size:0.85rem; line-height:1.6; text-align:left; background:#FAF7F2; padding:14px 16px; border-radius:10px;">
        <b>請檢查：</b><br>
        1. Streamlit Secrets 中的 <code>gcp_service_account</code> 欄位完整<br>
        2. 服務帳戶 email 已加入 Sheet 為編輯者<br>
        3. Google Drive API 與 Sheets API 已啟用
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

record_daily_progress(tasks)


# ============================================================
# 側邊欄（Logo + 統計摘要 + 重新載入）
# ============================================================
total = len(tasks)
completed_count = sum(1 for t in tasks if int(t.get('progress', 0)) >= 100)
purple_count = sum(1 for t in tasks if get_status(t.get('when_end', ''), int(t.get('progress', 0)))[1] == 'purple')
red_count = sum(1 for t in tasks if get_status(t.get('when_end', ''), int(t.get('progress', 0)))[1] == 'red')

with st.sidebar:
    # Logo + 標題（線條 icon，非 emoji）
    st.markdown(f"""
    <div style="text-align:center; padding: 14px 0 10px;">
      <div style="display:inline-flex; align-items:center; justify-content:center;
                  width:56px; height:56px; border-radius:14px;
                  background:linear-gradient(135deg, {COLORS['primary_light']}, {COLORS['primary']});
                  box-shadow: 0 4px 14px rgba(232,93,58,0.45);">
        <i class="bi bi-kanban" style="color:white; font-size:1.9rem;"></i>
      </div>
      <div style="font-family: 'Noto Sans TC'; font-weight:900; font-size:1.05rem; color:#FAF7F2; margin-top:10px; letter-spacing:0.02em;">
        總部專案追蹤助理
      </div>
      <div style="font-size:0.72rem; color:#A09B95; margin-top:2px;">雲端版 v1.1</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<hr style="border-color:#333; margin:12px 0;">', unsafe_allow_html=True)

    # 統計摘要卡（側邊欄深底配高對比，用線條 icon 代替彩色 emoji dot）
    st.markdown(f"""
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px;">
      <div style="background:#2A2A2A; padding:12px; border-radius:10px; text-align:center;">
        <div style="font-size:1.6rem; font-weight:800; color:#FAF7F2; font-family:'Inter';">{total}</div>
        <div style="font-size:0.68rem; color:#A09B95; margin-top:2px; display:flex; align-items:center; justify-content:center; gap:4px;">
          <i class="bi bi-list-task"></i> 總事項
        </div>
      </div>
      <div style="background:#2A2A2A; padding:12px; border-radius:10px; text-align:center; border-left:3px solid {COLORS['complete']};">
        <div style="font-size:1.6rem; font-weight:800; color:#FAF7F2; font-family:'Inter';">{completed_count}</div>
        <div style="font-size:0.68rem; color:#A09B95; margin-top:2px; display:flex; align-items:center; justify-content:center; gap:4px;">
          <i class="bi bi-check-circle"></i> 已完成
        </div>
      </div>
      <div style="background:#2A2A2A; padding:12px; border-radius:10px; text-align:center; border-left:3px solid {COLORS['red']};">
        <div style="font-size:1.6rem; font-weight:800; color:#FCA5A5; font-family:'Inter';">{red_count}</div>
        <div style="font-size:0.68rem; color:#A09B95; margin-top:2px; display:flex; align-items:center; justify-content:center; gap:4px;">
          <i class="bi bi-exclamation-triangle" style="color:{COLORS['red']};"></i> 緊急
        </div>
      </div>
      <div style="background:#2A2A2A; padding:12px; border-radius:10px; text-align:center; border-left:3px solid {COLORS['purple']};">
        <div style="font-size:1.6rem; font-weight:800; color:#C4B5FD; font-family:'Inter';">{purple_count}</div>
        <div style="font-size:0.68rem; color:#A09B95; margin-top:2px; display:flex; align-items:center; justify-content:center; gap:4px;">
          <i class="bi bi-clock-history" style="color:{COLORS['purple']};"></i> 逾期
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr style="border-color:#333; margin:12px 0;">', unsafe_allow_html=True)

    if st.button('重新載入資料', use_container_width=True):
        refresh_data()
        st.rerun()

    st.markdown(f"""
    <div style="margin-top:16px; padding:10px 12px; background:rgba(255,255,255,0.05); border-radius:8px;">
      <div style="font-size:0.65rem; color:#A09B95; text-transform:uppercase; letter-spacing:0.08em; font-weight:600;">最後更新</div>
      <div style="font-size:0.85rem; color:{COLORS['cream']}; margin-top:2px; font-family:'Inter';">{datetime.now().strftime('%Y/%m/%d %H:%M')}</div>
      <div style="font-size:0.65rem; color:#A09B95; margin-top:6px; line-height:1.7;">
        <div style="display:flex; align-items:center; gap:4px;"><i class="bi bi-lightning-charge"></i> 自動掃描每小時一次</div>
        <div style="display:flex; align-items:center; gap:4px;"><i class="bi bi-arrow-repeat"></i> Sheet 快取 5 分鐘</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 頂部導航列（取代 radio — 桌面 & 手機都友善）
# ============================================================
NAV_LABELS = ['專案總覽', '匯入', '統計', '週報', 'Line']
NAV_ICONS = ['kanban', 'cloud-arrow-down', 'bar-chart-line', 'journal-text', 'chat-left-dots']

selected = option_menu(
    menu_title=None,
    options=NAV_LABELS,
    icons=NAV_ICONS,
    orientation='horizontal',
    default_index=0,
    key='main_nav',
    styles={
        'container': {
            'padding': '6px!important',
            'background-color': 'rgba(255, 255, 255, 0.7)',
            'border-radius': '14px',
            'border': f'1px solid {COLORS["line"]}',
            'box-shadow': '0 2px 8px rgba(0,0,0,0.04)',
            'backdrop-filter': 'blur(10px)',
            'margin-bottom': '24px',
        },
        'icon': {'color': COLORS['ink_soft'], 'font-size': '17px'},
        'nav-link': {
            'font-family': "'Noto Sans TC', sans-serif",
            'font-size': '0.95rem',
            'font-weight': '600',
            'color': COLORS['ink_soft'],
            'text-align': 'center',
            'margin': '0 2px',
            'padding': '10px 14px',
            'border-radius': '10px',
            '--hover-color': 'rgba(232, 93, 58, 0.08)',
        },
        'nav-link-selected': {
            'background': f'linear-gradient(135deg, {COLORS["primary_light"]}, {COLORS["primary"]})',
            'color': 'white',
            'font-weight': '700',
            'box-shadow': '0 4px 12px rgba(232, 93, 58, 0.35)',
        },
    },
)

# 映射導航標籤到內部判斷字串
page = {
    '專案總覽': '專案總覽',
    '匯入': '匯入會議記錄',
    '統計': '統計報表',
    '週報': '週報',
    'Line': 'Line 提醒',
}[selected]


# ============================================================
# 1) 專案總覽（含首頁儀表板）
# ============================================================
if page == '專案總覽':
    if not tasks:
        st.title('專案總覽')
        st.info('尚無任何專案，請先到「匯入會議記錄」頁面匯入資料')
    else:
        # ---------- 首頁儀表板 ----------
        metrics = compute_metrics(tasks)
        render_ai_summary(metrics)
        render_hero_kpis(metrics)
        st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
        render_focus_cards(metrics)

        # ---------- 分隔 ----------
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:12px; margin:28px 0 16px;">
          <div style="flex:1; height:1px; background:{COLORS['line']};"></div>
          <div style="font-weight:700; color:{COLORS['ink']}; font-size:1.1rem; display:flex; align-items:center; gap:8px;">
            <i class="bi bi-list-check"></i> 全部任務
          </div>
          <div style="flex:1; height:1px; background:{COLORS['line']};"></div>
        </div>
        """, unsafe_allow_html=True)

        # 搜尋列 + 燈號篩選
        col_s1, col_s2 = st.columns([3, 2])
        with col_s1:
            search_q = st.text_input(
                '搜尋任務', '',
                placeholder='搜尋任務名稱 / 負責人 / 目的…',
                key='search_q', label_visibility='collapsed',
            )
        with col_s2:
            filter_status = st.selectbox(
                '燈號',
                ['全部燈號', '已逾期', '緊急', '注意', '正常', '已完成'],
                key='filter_status', label_visibility='collapsed',
            )

        # 部門 chips
        if 'filter_dept' not in st.session_state:
            st.session_state.filter_dept = '全部'

        def _set_dept(d):
            st.session_state.filter_dept = d

        chip_cols = st.columns(len(DEPARTMENTS) + 1)
        with chip_cols[0]:
            is_selected = st.session_state.filter_dept == '全部'
            if st.button(f'全部', key='dept_chip_all',
                         type='primary' if is_selected else 'secondary',
                         use_container_width=True):
                _set_dept('全部')
                st.rerun()
        for idx, d in enumerate(DEPARTMENTS):
            with chip_cols[idx + 1]:
                is_selected = st.session_state.filter_dept == d
                if st.button(d, key=f'dept_chip_{idx}',
                             type='primary' if is_selected else 'secondary',
                             use_container_width=True):
                    _set_dept(d)
                    st.rerun()

        filter_dept = st.session_state.filter_dept

        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)

        # 篩選
        filtered = []
        for task in tasks:
            if filter_dept != '全部' and task.get('who_dept') != filter_dept:
                continue
            status_text, color = get_status(task.get('when_end', ''), int(task.get('progress', 0)))
            if filter_status != '全部燈號' and filter_status not in status_text:
                continue
            if search_q:
                hay = ' '.join(str(task.get(k, '')) for k in
                               ('what', 'why', 'how', 'who_person', 'who_dept', 'where')).lower()
                if search_q.lower() not in hay:
                    continue
            filtered.append((task, status_text, color))

        # 結果計數
        st.markdown(f"""
        <div style="color:{COLORS['ink_soft']}; font-size:0.85rem; margin-bottom:10px;">
          符合條件的任務：<b style="color:{COLORS['ink']};">{len(filtered)}</b> / {len(tasks)} 件
        </div>
        """, unsafe_allow_html=True)

        # ---------- 任務卡片列表 ----------
        @st.dialog('編輯任務', width='large')
        def _edit_dialog(task):
            st.markdown(f"<div style='color:{COLORS['ink_soft']}; font-size:0.8rem; margin-bottom:6px;'>Task ID：<code>{task.get('task_id','')[:8]}…</code></div>", unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                new_what = st.text_input('任務名稱', task.get('what', ''))
                dept_val = task.get('who_dept', DEPARTMENTS[0])
                dept_index = DEPARTMENTS.index(dept_val) if dept_val in DEPARTMENTS else 0
                new_dept = st.selectbox('負責部門', DEPARTMENTS, index=dept_index)
                new_person = st.text_input('負責人', task.get('who_person', ''))
                new_where = st.text_input('執行地點', task.get('where', ''))
            with col2:
                new_why = st.text_area('目的', task.get('why', ''), height=100)
                new_how = st.text_area('執行方式', task.get('how', ''), height=100)

            # 日期：用 st.date_input（手機原生日曆）
            col_d1, col_d2 = st.columns(2)

            def _parse_date(s):
                try:
                    return date.fromisoformat(s) if s else None
                except Exception:
                    return None

            with col_d1:
                start_dt = _parse_date(task.get('when_start', ''))
                new_start_dt = st.date_input('開始日期', start_dt, format='YYYY-MM-DD')
                new_start = new_start_dt.isoformat() if new_start_dt else ''
            with col_d2:
                end_dt = _parse_date(task.get('when_end', ''))
                new_end_dt = st.date_input('截止日期', end_dt, format='YYYY-MM-DD')
                new_end = new_end_dt.isoformat() if new_end_dt else ''

            new_progress = st.slider('進度 %', 0, 100, int(task.get('progress', 0)))

            col_save, col_del, col_cancel = st.columns([1.2, 1.2, 1])
            with col_save:
                if st.button('儲存變更', type='primary', use_container_width=True):
                    updated = dict(task)
                    updated.update({
                        'what': new_what, 'who_dept': new_dept, 'who_person': new_person,
                        'where': new_where, 'why': new_why, 'how': new_how,
                        'when_start': new_start, 'when_end': new_end, 'progress': new_progress,
                    })
                    try:
                        ok = update_task(updated)
                        if ok:
                            refresh_data()
                            st.success('已儲存！')
                            st.rerun()
                        else:
                            st.error('找不到對應的 task_id')
                    except Exception as e:
                        st.error(f'儲存失敗：{e}')
            with col_del:
                if st.button('刪除', use_container_width=True):
                    try:
                        if delete_task(task.get('task_id', '')):
                            refresh_data()
                            st.success('已刪除')
                            st.rerun()
                        else:
                            st.error('刪除失敗（找不到對應 row）')
                    except Exception as e:
                        st.error(f'刪除失敗：{e}')

        # 渲染卡片
        if not filtered:
            st.markdown(f"""
            <div style="text-align:center; padding:40px 20px; color:{COLORS['ink_soft']};">
              <i class="bi bi-search" style="font-size:2.6rem; color:{COLORS['line']};"></i>
              <div style="margin-top:10px; font-size:0.95rem;">沒有符合條件的任務</div>
              <div style="font-size:0.8rem; color:#999; margin-top:4px;">試試調整篩選條件</div>
            </div>
            """, unsafe_allow_html=True)

        # 按燈號排序：紫 > 紅 > 黃 > 綠 > 完成
        order = {'purple': 0, 'red': 1, 'yellow': 2, 'green': 3, 'complete': 4}
        filtered.sort(key=lambda x: (order.get(x[2], 9), x[0].get('when_end', '9999-12-31')))

        # 狀態色對應
        color_map = {
            'purple': COLORS['purple'], 'red': COLORS['red'],
            'yellow': COLORS['yellow'], 'green': COLORS['green'],
            'complete': COLORS['complete'],
        }

        for i, (task, status_text, color) in enumerate(filtered):
            progress = int(task.get('progress', 0))
            bar_color = color_map.get(color, COLORS['green'])

            card_col, btn_col = st.columns([20, 1])
            with card_col:
                st.markdown(f"""
                <div style="
                  background: white;
                  border-radius: 14px;
                  padding: 14px 18px;
                  margin-bottom: 10px;
                  box-shadow: 0 2px 6px rgba(0,0,0,0.05);
                  border-left: 4px solid {bar_color};
                  border-right: 1px solid {COLORS['line']};
                  border-top: 1px solid {COLORS['line']};
                  border-bottom: 1px solid {COLORS['line']};
                  display:grid; grid-template-columns: 1fr auto; gap: 10px; align-items:center;
                ">
                  <div>
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px; flex-wrap:wrap;">
                      <span style="font-weight:700; font-size:1rem; color:{COLORS['ink']};">{task.get('what','未命名')[:60]}</span>
                      <span class="brand-tag primary">{task.get('who_dept','')}</span>
                      <span class="brand-tag">{task.get('who_person','')}</span>
                      <span class="brand-tag {color}">{status_text}</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:10px;">
                      <div style="flex:1; height:6px; background:{COLORS['cream_dark']}; border-radius:999px; overflow:hidden;">
                        <div style="width:{progress}%; height:100%; background:linear-gradient(90deg,{COLORS['primary_light']},{COLORS['primary']}); border-radius:999px; transition:width 0.4s;"></div>
                      </div>
                      <div style="font-size:0.8rem; font-weight:700; font-family:'Inter'; color:{COLORS['ink']}; min-width:40px; text-align:right;">{progress}%</div>
                      <div style="font-size:0.75rem; color:{COLORS['ink_soft']}; min-width:90px; text-align:right; display:flex; align-items:center; justify-content:flex-end; gap:4px;"><i class="bi bi-calendar-event"></i> {task.get('when_end','未設定')}</div>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            with btn_col:
                st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
                if st.button('編輯', key=f'edit_{i}_{task.get("task_id","")[:6]}',
                             help='編輯任務', use_container_width=True):
                    _edit_dialog(task)


# ============================================================
# 2) 匯入會議記錄
# ============================================================
elif page == '匯入會議記錄':
    st.markdown(f"""
    <div style="margin-bottom:18px;">
      <h1 style="margin:0; background:linear-gradient(135deg,{COLORS['primary']},{COLORS['primary_dark']});
                 -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
                 font-weight:900; letter-spacing:-0.02em;">匯入會議記錄</h1>
      <div style="color:{COLORS['ink_soft']}; font-size:0.9rem; margin-top:4px;">
        從 Google Drive 抓取 .doc / .docx / Google Doc，AI 自動解析 5W2H 行動事項
      </div>
    </div>
    <div style="background:rgba(232,93,58,0.08); border-left:3px solid {COLORS['primary']}; border-radius:10px; padding:12px 16px; margin-bottom:20px; font-size:0.88rem; color:{COLORS['ink']}; display:flex; align-items:center; gap:10px;">
      <i class="bi bi-clock" style="color:{COLORS['primary']};"></i>
      系統每小時由 GitHub Actions 自動掃描新檔。本頁供你立刻手動匯入。
    </div>
    """, unsafe_allow_html=True)

    # ── 貼入 URL 快速匯入 ──────────────────────────────────────
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
      <div style="width:4px; height:20px; background:{COLORS['primary']}; border-radius:2px;"></div>
      <div style="font-weight:700; font-size:1.05rem; color:{COLORS['ink']};">貼入連結匯入</div>
    </div>
    <div style="font-size:0.83rem; color:{COLORS['ink_soft']}; margin-bottom:10px;">
      支援 Google Drive 檔案連結、Google Docs 連結、或任意網頁 URL
    </div>
    """, unsafe_allow_html=True)

    _url_col, _btn_col = st.columns([5, 1])
    with _url_col:
        _paste_url = st.text_input(
            '貼入連結',
            value=st.session_state.get('_paste_url_val', ''),
            placeholder='https://drive.google.com/… 或 https://docs.google.com/… 或任何網頁網址',
            label_visibility='collapsed',
            key='_paste_url_input',
        )
    with _btn_col:
        _parse_url_btn = st.button('🔍 解析', use_container_width=True, help='從連結抓取內容並以 AI 解析')

    if _parse_url_btn and _paste_url.strip():
        with st.spinner('正在讀取連結內容並進行 AI 解析，請稍候…'):
            try:
                service = get_drive_service()
                _url_text, _url_source = extract_text_from_url(service, _paste_url.strip())
                if not _url_text.strip():
                    st.warning('讀取到的內容為空，請確認連結是否正確或有存取權限。')
                else:
                    result = parse_meeting(_url_text, _url_source)
                    _url_tasks = result.get('tasks', [])
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
                    for t in _url_tasks:
                        t['source_file'] = _url_source
                        t['imported_at'] = now_str
                    st.session_state['_url_parsed_tasks'] = _url_tasks
                    st.session_state['_url_source'] = _url_source
                    st.session_state['_paste_url_val'] = _paste_url.strip()
            except Exception as e:
                st.error(f'解析失敗：{e}')

    if st.session_state.get('_url_parsed_tasks'):
        _url_tasks = st.session_state['_url_parsed_tasks']
        _url_source = st.session_state.get('_url_source', '')
        st.markdown(f"""
        <div style="background:rgba(232,93,58,0.07); border-radius:10px; padding:10px 16px; margin:10px 0 6px;
                    font-size:0.87rem; color:{COLORS['ink']};">
          <b>來源：</b>{_url_source}　｜　<b>解析出 {len(_url_tasks)} 個行動事項</b>（確認後寫入系統）
        </div>
        """, unsafe_allow_html=True)
        for _t in _url_tasks:
            _status_text, _color = get_status(_t.get('when_end', ''), int(_t.get('progress', 0)))
            _color_map = {'purple': COLORS['purple'], 'red': COLORS['red'], 'yellow': COLORS['yellow'],
                          'green': COLORS['green'], 'complete': COLORS['complete']}
            _bar_color = _color_map.get(_color, COLORS['green'])
            st.markdown(f"""
            <div style="background:white; border-radius:10px; padding:12px 16px; margin-bottom:8px;
                        border-left:4px solid {_bar_color}; border:1px solid {COLORS['line']};
                        border-left:4px solid {_bar_color}; box-shadow:0 1px 4px rgba(0,0,0,0.04);">
              <div style="font-weight:700; font-size:0.93rem; color:{COLORS['ink']};">{_t.get('what','')}</div>
              <div style="margin-top:5px; display:flex; gap:5px; flex-wrap:wrap; font-size:0.8rem;">
                <span class="brand-tag primary">{_t.get('who_dept','')}</span>
                <span class="brand-tag">{_t.get('who_person','')}</span>
                <span class="brand-tag">{_t.get('when_end','未設定')}</span>
              </div>
              <div style="margin-top:6px; font-size:0.8rem; color:{COLORS['ink_soft']};">{_t.get('why','')}</div>
            </div>
            """, unsafe_allow_html=True)

        _conf_col, _discard_col = st.columns(2)
        with _conf_col:
            if st.button('✅ 確認匯入', type='primary', use_container_width=True, key='_url_confirm'):
                n = append_tasks(_url_tasks)
                refresh_data()
                st.toast(f'成功匯入 {n} 個行動事項')
                del st.session_state['_url_parsed_tasks']
                st.session_state.pop('_url_source', None)
                st.session_state.pop('_paste_url_val', None)
                st.rerun()
        with _discard_col:
            if st.button('🗑️ 捨棄', use_container_width=True, key='_url_discard'):
                del st.session_state['_url_parsed_tasks']
                st.session_state.pop('_url_source', None)
                st.session_state.pop('_paste_url_val', None)
                st.rerun()

    st.divider()
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
      <div style="width:4px; height:20px; background:{COLORS['primary']}; border-radius:2px;"></div>
      <div style="font-weight:700; font-size:1.05rem; color:{COLORS['ink']};">掃描 Drive 資料夾</div>
    </div>
    """, unsafe_allow_html=True)

    # ── 持久化預設資料夾（讀 Google Sheets app_settings）────────
    def _parse_folder_url(raw: str) -> str:
        raw = raw.strip()
        if 'folders/' in raw:
            return raw.split('folders/')[-1].split('?')[0].split('/')[0].strip()
        return raw

    # 初次進頁或 session 空白時，從 Sheets 讀預設資料夾
    if '_default_folder_loaded' not in st.session_state:
        try:
            from lib.config import get_drive_folder_id as _cfg_folder
            _sheets_folder = get_setting('default_folder_id', '')
            _config_folder = ''
            try:
                _config_folder = _cfg_folder()
            except Exception:
                pass
            # Sheets 優先，否則 fallback 到 secrets/env
            st.session_state['_saved_folder_id'] = _sheets_folder or _config_folder
        except Exception:
            st.session_state['_saved_folder_id'] = ''
        st.session_state['_default_folder_loaded'] = True

    _saved_fid = st.session_state.get('_saved_folder_id', '')

    # 顯示目前預設資料夾 + 修改輸入
    st.markdown(f"<div style='font-size:0.85rem; color:{COLORS['ink_soft']}; margin-bottom:6px;'>📌 預設掃描資料夾（永久儲存）</div>", unsafe_allow_html=True)
    _def_c1, _def_c2, _def_c3 = st.columns([5, 1, 1])
    with _def_c1:
        _default_url_input = st.text_input(
            '預設資料夾',
            value=_saved_fid,
            placeholder='貼入 Google Drive 資料夾網址或 ID…',
            label_visibility='collapsed',
            key='_default_folder_input',
        )
    _new_default_fid = _parse_folder_url(_default_url_input)
    with _def_c2:
        if st.button('💾 儲存', use_container_width=True, key='_save_default_folder',
                     help='永久儲存此資料夾為預設，重啟後仍有效'):
            if _new_default_fid:
                try:
                    set_setting('default_folder_id', _new_default_fid)
                    st.session_state['_saved_folder_id'] = _new_default_fid
                    st.toast('✅ 預設資料夾已儲存')
                    st.rerun()
                except Exception as _e:
                    st.error(f'儲存失敗：{_e}')
    with _def_c3:
        if _new_default_fid:
            _disp_fid = _new_default_fid[:14] + '…' if len(_new_default_fid) > 14 else _new_default_fid
            st.success(f'`{_disp_fid}`')
        else:
            st.warning('未設定')

    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)

    # ── 額外資料夾管理 ────────────────────────────────────────
    if '_extra_folder_ids' not in st.session_state:
        st.session_state['_extra_folder_ids'] = []

    _fa_col, _fb_col = st.columns([5, 1])
    with _fa_col:
        _new_folder_url = st.text_input(
            '新增掃描資料夾',
            placeholder='貼入其他 Google Drive 資料夾網址或 ID，可新增多個…',
            label_visibility='collapsed',
            key='_new_folder_input',
        )
    with _fb_col:
        if st.button('＋ 新增', use_container_width=True, key='_add_folder_btn'):
            _fid = _parse_folder_url(_new_folder_url)
            if _fid and _fid not in st.session_state['_extra_folder_ids']:
                st.session_state['_extra_folder_ids'].append(_fid)
                st.rerun()

    if st.session_state['_extra_folder_ids']:
        st.markdown(f"<div style='font-size:0.82rem; color:{COLORS['ink_soft']}; margin-bottom:4px;'>額外掃描資料夾：</div>", unsafe_allow_html=True)
        for _eidx, _eid in enumerate(st.session_state['_extra_folder_ids']):
            _rc1, _rc2 = st.columns([6, 1])
            with _rc1:
                _disp = _eid[:28] + '…' if len(_eid) > 28 else _eid
                _ink = COLORS['ink']
                st.markdown(f'<div style="background:#F8F9FA; border-radius:6px; padding:5px 10px; font-size:0.83rem; font-family:monospace; color:{_ink};">📂 {_disp}</div>', unsafe_allow_html=True)
            with _rc2:
                if st.button('✕', key=f'_rm_folder_{_eidx}', use_container_width=True):
                    st.session_state['_extra_folder_ids'].pop(_eidx)
                    st.rerun()

    _all_folder_count = 1 + len(st.session_state['_extra_folder_ids'])
    _scan_label = f'掃描所有子資料夾（共 {_all_folder_count} 個來源）' if _all_folder_count > 1 else '掃描所有子資料夾'

    if st.button(_scan_label, type='primary', use_container_width=True):
        with st.spinner('正在掃描 Google Drive…'):
            try:
                service = get_drive_service()
                # 優先使用持久化儲存的資料夾，fallback 到 secrets/env
                _primary_fid = st.session_state.get('_saved_folder_id', '') or _new_default_fid
                if not _primary_fid:
                    from lib.config import get_drive_folder_id
                    _primary_fid = get_drive_folder_id()
                _folder_ids = [_primary_fid] + st.session_state['_extra_folder_ids']
                files: list[dict] = []
                _seen_ids: set[str] = set()
                for _fid in _folder_ids:
                    for _f in list_doc_files(service, _fid):
                        if _f['id'] not in _seen_ids:
                            _seen_ids.add(_f['id'])
                            files.append(_f)
                st.session_state['drive_files'] = files
                st.toast(f'找到 {len(files)} 個會議記錄檔案（掃描 {len(_folder_ids)} 個資料夾）')
            except Exception as e:
                st.error(f'掃描失敗：{e}')

    if 'drive_files' in st.session_state and st.session_state['drive_files']:
        files = st.session_state['drive_files']

        # ── 讀取已匯入的 file_id 集合（重複匯入防護）──
        try:
            _imported_ids = load_scanned_file_ids()
        except Exception:
            _imported_ids = set()

        _new_files = [f for f in files if f['id'] not in _imported_ids]
        _done_files = [f for f in files if f['id'] in _imported_ids]

        _ink_soft = COLORS['ink_soft']
        _ink = COLORS['ink']
        st.markdown(
            f"<div style='color:{_ink_soft}; font-size:0.85rem; margin:14px 0 6px;'>"
            f"Drive 中共有 <b style='color:{_ink};'>{len(files)}</b> 份可解析文件，"
            f"其中 <b style='color:{COLORS['green']};'>{len(_done_files)}</b> 份已匯入、"
            f"<b style='color:{_ink};'>{len(_new_files)}</b> 份尚未匯入</div>",
            unsafe_allow_html=True,
        )

        # 下拉選單：未匯入優先，已匯入加 ✓ 標示
        _file_options = [f['name'] for f in _new_files] + [f'✓ {f["name"]}' for f in _done_files]
        _file_map = {f['name']: f for f in files}
        _file_map.update({f'✓ {f["name"]}': f for f in _done_files})

        if not _file_options:
            st.info('所有文件均已匯入過，如需重新匯入請從下方選取。')
        else:
            _selected_label = st.selectbox('選擇要匯入的會議記錄', _file_options, label_visibility='collapsed')
            _selected_file = _file_map[_selected_label]
            _already_imported = _selected_file['id'] in _imported_ids

            if _already_imported:
                st.warning(f'⚠️ 此文件已匯入過（{_selected_file["name"]}），再次解析可能產生重複任務。')

            if st.button('🤖 AI 解析（預覽後再決定是否匯入）', type='primary', use_container_width=True):
                with st.spinner('AI 正在解析會議記錄，請稍候…'):
                    try:
                        service = get_drive_service()
                        text = extract_text(service, _selected_file['id'], _selected_file['mimeType'], _selected_file['name'])
                        result = parse_meeting(text, _selected_file['name'])
                        _parsed = result.get('tasks', [])
                        now = datetime.now().strftime('%Y-%m-%d %H:%M')
                        for t in _parsed:
                            t['source_file'] = _selected_file['name']
                            t['imported_at'] = now
                        st.session_state['parsed_tasks'] = _parsed
                        st.session_state['parsed_file'] = _selected_file
                        # 預設全勾
                        st.session_state['parsed_checked'] = [True] * len(_parsed)
                        st.toast(f'解析完成，共找到 {len(_parsed)} 個行動事項，請確認後匯入')
                    except Exception as e:
                        st.error(f'解析失敗：{e}')

    # ── 勾選式匯入預覽 ─────────────────────────────────────
    if st.session_state.get('parsed_tasks'):
        _parsed_list = st.session_state['parsed_tasks']
        _parsed_file = st.session_state.get('parsed_file', {})
        _checked = st.session_state.get('parsed_checked', [True] * len(_parsed_list))

        st.markdown(f"""
        <div style="margin:24px 0 8px; display:flex; align-items:center; gap:10px;">
          <div style="width:4px; height:20px; background:{COLORS['primary']}; border-radius:2px;"></div>
          <div style="font-weight:700; font-size:1.05rem; color:{COLORS['ink']};">
            AI 解析結果 — 請勾選要匯入的項目（共 {len(_parsed_list)} 項）
          </div>
        </div>
        """, unsafe_allow_html=True)

        _sel_col1, _sel_col2, _ = st.columns([1, 1, 4])
        with _sel_col1:
            if st.button('全選', key='_chk_all', use_container_width=True):
                st.session_state['parsed_checked'] = [True] * len(_parsed_list)
                st.rerun()
        with _sel_col2:
            if st.button('全不選', key='_chk_none', use_container_width=True):
                st.session_state['parsed_checked'] = [False] * len(_parsed_list)
                st.rerun()

        _new_checked = list(_checked)
        for _i, _t in enumerate(_parsed_list):
            _status_text, _color = get_status(_t.get('when_end', ''), int(_t.get('progress', 0)))
            _color_map = {'purple': COLORS['purple'], 'red': COLORS['red'], 'yellow': COLORS['yellow'],
                          'green': COLORS['green'], 'complete': COLORS['complete']}
            _bar_color = _color_map.get(_color, COLORS['green'])
            _chk_col, _card_col = st.columns([0.5, 9.5])
            with _chk_col:
                st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
                _new_checked[_i] = st.checkbox('', value=_checked[_i], key=f'_chk_{_i}', label_visibility='collapsed')
            with _card_col:
                _opacity = '1' if _new_checked[_i] else '0.4'
                st.markdown(f"""
                <div style="background:white; border-radius:12px; padding:14px 18px; margin-bottom:6px;
                            border-left:4px solid {_bar_color if _new_checked[_i] else '#ccc'};
                            border-top:1px solid {COLORS['line']}; border-right:1px solid {COLORS['line']};
                            border-bottom:1px solid {COLORS['line']}; box-shadow:0 2px 6px rgba(0,0,0,0.04);
                            opacity:{_opacity};">
                  <div style="font-weight:700; font-size:0.95rem; color:{COLORS['ink']};">{_t.get('what','')}</div>
                  <div style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;">
                    <span class="brand-tag primary">{_t.get('who_dept','')}</span>
                    <span class="brand-tag">{_t.get('who_person','')}</span>
                    <span class="brand-tag {_color}">{_status_text}</span>
                    <span class="brand-tag"><i class="bi bi-calendar-event" style="margin-right:4px;"></i>{_t.get('when_end','未設定')}</span>
                  </div>
                  <div style="margin-top:8px; font-size:0.82rem; color:{COLORS['ink_soft']}; line-height:1.5;">
                    <i class="bi bi-lightbulb" style="color:{COLORS['primary']}; margin-right:6px;"></i>{_t.get('why','')}
                  </div>
                </div>
                """, unsafe_allow_html=True)

        st.session_state['parsed_checked'] = _new_checked
        _selected_count = sum(_new_checked)

        _confirm_col, _discard_col = st.columns(2)
        with _confirm_col:
            if st.button(f'✅ 確認匯入（{_selected_count} 項）', type='primary', use_container_width=True,
                         key='_confirm_import', disabled=_selected_count == 0):
                _to_import = [t for t, c in zip(_parsed_list, _new_checked) if c]
                n = append_tasks(_to_import)
                # 記錄此檔案為已匯入（防重複）
                if _parsed_file:
                    append_scanned_files([{'file_id': _parsed_file['id'], 'file_name': _parsed_file['name']}])
                refresh_data()
                st.toast(f'成功匯入 {n} 個行動事項')
                del st.session_state['parsed_tasks']
                st.session_state.pop('parsed_file', None)
                st.session_state.pop('parsed_checked', None)
                st.rerun()
        with _discard_col:
            if st.button('🗑️ 捨棄解析結果', use_container_width=True, key='_discard_import'):
                del st.session_state['parsed_tasks']
                st.session_state.pop('parsed_file', None)
                st.session_state.pop('parsed_checked', None)
                st.rerun()


# ============================================================
# 3) 統計報表（Plotly 互動圖 + 部門燈號堆疊 + 倒數 timeline）
# ============================================================
elif page == '統計報表':
    st.markdown(f"""
    <div style="margin-bottom:18px;">
      <h1 style="margin:0; background:linear-gradient(135deg,{COLORS['primary']},{COLORS['primary_dark']});
                 -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
                 font-weight:900; letter-spacing:-0.02em;">統計報表</h1>
      <div style="color:{COLORS['ink_soft']}; font-size:0.9rem; margin-top:4px;">全公司專案進度的深度分析</div>
    </div>
    """, unsafe_allow_html=True)

    if not tasks:
        st.info('尚無資料，請先匯入會議記錄')
    else:
        from lib.charts import (
            progress_trend, dept_status_stacked, dept_completion_bar, week_due_timeline,
        )

        # ---------- Hero KPIs (sharing dashboard logic) ----------
        metrics = compute_metrics(tasks)
        render_hero_kpis(metrics)
        st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

        # ---------- 完成率趨勢 ----------
        history = cached_history()
        if len(history) >= 2:
            st.plotly_chart(progress_trend(history), use_container_width=True)
        else:
            st.markdown(f"""
            <div style="background:white; border-radius:14px; padding:26px 20px; text-align:center;
                        border:1px dashed {COLORS['line']}; color:{COLORS['ink_soft']};">
              <i class="bi bi-graph-up-arrow" style="font-size:1.8rem; color:{COLORS['line']};"></i>
              <div style="margin-top:8px;">趨勢圖需要 2 天以上的資料，目前累積中…</div>
              {f"<div style='font-size:0.85rem; margin-top:6px;'>今日：完成率 {history[-1].get('completion_rate',0)}% · 平均進度 {history[-1].get('avg_progress',0)}%</div>" if history else ''}
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

        # ---------- 部門分析：兩欄並排 ----------
        # 計算：dept_rows（for bar）+ dept_breakdown（for stacked 燈號）
        dept_counts: dict[str, dict] = {}
        dept_breakdown: dict[str, dict] = {}
        for t in tasks:
            dept = t.get('who_dept', '未分類')
            d = dept_counts.setdefault(dept, {'total': 0, 'completed': 0, 'progress_sum': 0})
            d['total'] += 1
            p = int(t.get('progress', 0))
            if p >= 100:
                d['completed'] += 1
            d['progress_sum'] += p

            b = dept_breakdown.setdefault(dept, {'complete': 0, 'green': 0, 'yellow': 0, 'red': 0, 'purple': 0})
            _, color = get_status(t.get('when_end', ''), p)
            b[color] = b.get(color, 0) + 1

        dept_rows = [{
            '部門': dept, '總事項': d['total'], '已完成': d['completed'],
            '完成率%': round(d['completed'] / d['total'] * 100, 1) if d['total'] else 0,
            '平均進度%': round(d['progress_sum'] / d['total'], 1) if d['total'] else 0,
        } for dept, d in dept_counts.items()]

        chart_c1, chart_c2 = st.columns(2)
        with chart_c1:
            st.plotly_chart(dept_completion_bar(dept_rows), use_container_width=True)
        with chart_c2:
            st.plotly_chart(dept_status_stacked(dept_breakdown), use_container_width=True)

        st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

        # ---------- 本週到期倒數 ----------
        today = date.today()
        week_rows = []
        for t in tasks:
            if not t.get('when_end'):
                continue
            try:
                end = datetime.strptime(t['when_end'], '%Y-%m-%d').date()
            except ValueError:
                continue
            days_left = (end - today).days
            if -7 <= days_left <= 7:
                week_rows.append({
                    '任務名稱': t.get('what', ''),
                    '負責部門': t.get('who_dept', ''),
                    '負責人': t.get('who_person', ''),
                    '截止日期': t.get('when_end', ''),
                    '剩餘天數': days_left,
                    '進度%': int(t.get('progress', 0)),
                })

        if week_rows:
            st.plotly_chart(week_due_timeline(week_rows), use_container_width=True)
        else:
            st.markdown(f"""
            <div style="background:white; border-radius:14px; padding:26px 20px; text-align:center; color:{COLORS['ink_soft']};">
              <i class="bi bi-check2-circle" style="font-size:1.8rem; color:{COLORS['green']};"></i>
              <div style="margin-top:8px;">本週無逾期或即將到期事項</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)

        # ---------- 匯出 ----------
        excel_data = export_to_excel(tasks)
        st.download_button(
            label='下載完整專案追蹤表（.xlsx）',
            data=excel_data,
            file_name=f'專案追蹤_{date.today()}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            type='primary',
            use_container_width=True,
        )


# ============================================================
# 4) 週報
# ============================================================
elif page == '週報':
    st.markdown(f"""
    <div style="margin-bottom:18px;">
      <h1 style="margin:0; background:linear-gradient(135deg,{COLORS['primary']},{COLORS['primary_dark']});
                 -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
                 font-weight:900; letter-spacing:-0.02em;">週報產生</h1>
      <div style="color:{COLORS['ink_soft']}; font-size:0.9rem; margin-top:4px;">
        一鍵整合緊急事項、各部門進度、整體概況 → 貼進 Line / Email
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not tasks:
        st.info('尚無資料，請先匯入會議記錄')
    else:
        if st.button('產出本週週報', type='primary', use_container_width=True):
            report = generate_weekly_report(tasks)
            st.session_state['weekly_report'] = report
            st.toast('週報已產出')

        if 'weekly_report' in st.session_state:
            report = st.session_state['weekly_report']
            st.markdown(f"""
            <div style='margin:18px 0 8px; font-weight:600; color:{COLORS['ink']}; display:flex; align-items:center; gap:8px;'>
              <i class="bi bi-file-earmark-text"></i> 週報內容（右上角可一鍵複製）
            </div>""", unsafe_allow_html=True)
            st.code(report, language=None)
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button(
                    '下載 .txt', report,
                    file_name=f'週報_{date.today()}.txt', mime='text/plain',
                    use_container_width=True,
                )
            with col_d2:
                if st.button('重新產出', use_container_width=True, key='weekly_regen'):
                    del st.session_state['weekly_report']
                    st.rerun()


# ============================================================
# 5) Line 提醒
# ============================================================
elif page == 'Line 提醒':
    st.markdown(f"""
    <div style="margin-bottom:18px;">
      <h1 style="margin:0; background:linear-gradient(135deg,{COLORS['primary']},{COLORS['primary_dark']});
                 -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
                 font-weight:900; letter-spacing:-0.02em;">Line 提醒</h1>
      <div style="color:{COLORS['ink_soft']}; font-size:0.9rem; margin-top:4px;">
        產出今日紅燈 / 紫燈事項，一鍵複製貼到 Line 群組
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button('產出今日緊急／逾期提醒', type='primary', use_container_width=True):
        msg = generate_line_message(tasks)
        st.session_state['line_msg'] = msg
        st.toast('訊息已產出')

    if 'line_msg' in st.session_state:
        msg = st.session_state['line_msg']
        st.markdown(f"""
        <div style='margin:18px 0 8px; font-weight:600; color:{COLORS['ink']}; display:flex; align-items:center; gap:8px;'>
          <i class="bi bi-chat-left-dots"></i> Line 訊息（右上角可一鍵複製）
        </div>""", unsafe_allow_html=True)
        st.code(msg, language=None)
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button(
                '下載 .txt', msg,
                file_name=f'line提醒_{date.today()}.txt', mime='text/plain',
                use_container_width=True,
            )
        with col_d2:
            if st.button('重新產出', use_container_width=True, key='line_regen'):
                del st.session_state['line_msg']
                st.rerun()


# ============================================================
# 浮動操作按鈕 FAB（全站顯示）
# ============================================================
@st.dialog('快速新增任務', width='large')
def _quick_add_dialog():
    st.markdown('<div style="color:#666; font-size:0.85rem; margin-bottom:10px;">直接手動建立一筆任務（不經過 AI 解析）</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        q_what = st.text_input('任務名稱 *', '')
        q_dept = st.selectbox('負責部門 *', DEPARTMENTS)
        q_person = st.text_input('負責人', '待確認')
        q_where = st.text_input('執行地點', '總部')
    with c2:
        q_why = st.text_area('目的', '', height=80)
        q_how = st.text_area('執行方式', '', height=80)
    c3, c4 = st.columns(2)
    with c3:
        q_start = st.date_input('開始日期', date.today(), format='YYYY-MM-DD')
    with c4:
        q_end = st.date_input('截止日期', None, format='YYYY-MM-DD')
    q_progress = st.slider('起始進度 %', 0, 100, 0)

    if st.button('新增任務', type='primary', use_container_width=True):
        if not q_what.strip():
            st.error('任務名稱必填')
            return
        new = {
            'what': q_what.strip(),
            'why': q_why.strip(),
            'who_dept': q_dept,
            'who_person': q_person.strip() or '待確認',
            'where': q_where.strip() or '總部',
            'when_start': q_start.isoformat() if q_start else '',
            'when_end': q_end.isoformat() if q_end else '',
            'how': q_how.strip(),
            'progress': q_progress,
            'source_file': '手動新增',
            'imported_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        try:
            append_tasks([new])
            refresh_data()
            st.toast('任務已新增')
            st.rerun()
        except Exception as e:
            st.error(f'新增失敗：{e}')


# 浮動按鈕容器（CSS 會把它釘到右下，線條 icon 風格）
st.markdown("""
<style>
.fab-slot {
  position: fixed !important;
  bottom: 28px;
  right: 28px;
  z-index: 9999;
  width: auto;
}
.fab-slot button {
  background: linear-gradient(135deg, #F27D5A, #D04020) !important;
  color: transparent !important;
  border: none !important;
  border-radius: 50% !important;
  width: 60px !important;
  height: 60px !important;
  font-size: 0 !important;
  padding: 0 !important;
  position: relative !important;
  box-shadow: 0 8px 24px rgba(232, 93, 58, 0.45), 0 0 0 6px rgba(232, 93, 58, 0.1) !important;
  transition: all 0.2s !important;
}
.fab-slot button::before {
  content: "\\f4fe"; /* bi-plus-lg unicode */
  font-family: "bootstrap-icons" !important;
  font-size: 1.8rem;
  color: white;
  font-weight: normal;
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  line-height: 1;
}
.fab-slot button:hover {
  transform: translateY(-2px) scale(1.05) !important;
  box-shadow: 0 12px 32px rgba(232, 93, 58, 0.55), 0 0 0 8px rgba(232, 93, 58, 0.15) !important;
}
@media (max-width: 768px) {
  .fab-slot {
    bottom: 20px;
    right: 20px;
  }
  .fab-slot button {
    width: 52px !important;
    height: 52px !important;
  }
  .fab-slot button::before {
    font-size: 1.5rem;
  }
}
</style>
<div class="fab-slot" id="fab-anchor"></div>
<script>
(function moveToFab(){
  const anchor = document.getElementById('fab-anchor');
  const buttons = document.querySelectorAll('button[kind="primary"]');
  for (const b of buttons) {
    if (b.textContent.trim() === '__FAB_NEW__' && !b.dataset.fabMoved) {
      b.dataset.fabMoved = '1';
      anchor.appendChild(b.closest('[data-testid="stButton"]') || b);
      break;
    }
  }
  setTimeout(moveToFab, 500);
})();
</script>
""", unsafe_allow_html=True)

if st.button('__FAB_NEW__', key='fab_main', type='primary', help='快速新增任務'):
    _quick_add_dialog()
