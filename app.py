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
from lib.drive_client import extract_text, get_drive_service, list_doc_files
from lib.ai_parser import parse_meeting
from lib.reports import export_to_excel, generate_line_message, generate_weekly_report
from lib.sheets_db import (
    append_tasks, delete_task, load_history, load_tasks, update_task, upsert_history,
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
    st.error(f'❌ 無法連線 Google Sheets：{e}')
    st.info('請確認 Streamlit secrets 中的 service account 設定，且該帳戶已被加為 Sheet 編輯者。')
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
    # Logo + 標題
    st.markdown("""
    <div style="text-align:center; padding: 12px 0 8px;">
      <div style="font-size:2.8rem; line-height:1;">🍲</div>
      <div style="font-family: 'Noto Sans TC'; font-weight:900; font-size:1.1rem; color:#FAF7F2; margin-top:4px; letter-spacing:0.02em;">
        總部專案追蹤助理
      </div>
      <div style="font-size:0.72rem; color:#A09B95; margin-top:2px;">雲端版 v1.1</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<hr style="border-color:#333; margin:12px 0;">', unsafe_allow_html=True)

    # 統計摘要卡（側邊欄深底配高對比）
    st.markdown(f"""
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px;">
      <div style="background:#2A2A2A; padding:12px; border-radius:10px; text-align:center;">
        <div style="font-size:1.6rem; font-weight:800; color:#FAF7F2; font-family:'Inter';">{total}</div>
        <div style="font-size:0.68rem; color:#A09B95; margin-top:2px;">總事項</div>
      </div>
      <div style="background:#2A2A2A; padding:12px; border-radius:10px; text-align:center; border-left:3px solid {COLORS['complete']};">
        <div style="font-size:1.6rem; font-weight:800; color:#FAF7F2; font-family:'Inter';">{completed_count}</div>
        <div style="font-size:0.68rem; color:#A09B95; margin-top:2px;">已完成</div>
      </div>
      <div style="background:#2A2A2A; padding:12px; border-radius:10px; text-align:center; border-left:3px solid {COLORS['red']};">
        <div style="font-size:1.6rem; font-weight:800; color:#FCA5A5; font-family:'Inter';">{red_count}</div>
        <div style="font-size:0.68rem; color:#A09B95; margin-top:2px;">🔴 緊急</div>
      </div>
      <div style="background:#2A2A2A; padding:12px; border-radius:10px; text-align:center; border-left:3px solid {COLORS['purple']};">
        <div style="font-size:1.6rem; font-weight:800; color:#C4B5FD; font-family:'Inter';">{purple_count}</div>
        <div style="font-size:0.68rem; color:#A09B95; margin-top:2px;">🟣 逾期</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr style="border-color:#333; margin:12px 0;">', unsafe_allow_html=True)

    if st.button('🔄 重新載入資料', use_container_width=True):
        refresh_data()
        st.rerun()


# ============================================================
# 頂部導航列（取代 radio — 桌面 & 手機都友善）
# ============================================================
NAV_LABELS = ['專案總覽', '匯入', '統計', '週報', 'Line']
NAV_ICONS = ['kanban-fill', 'cloud-arrow-down-fill', 'graph-up-arrow', 'journal-text', 'chat-dots-fill']

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
        'icon': {'color': COLORS['ink_soft'], 'font-size': '18px'},
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
    '專案總覽': '📊 專案總覽',
    '匯入': '📥 匯入會議記錄',
    '統計': '📈 統計報表',
    '週報': '📋 週報',
    'Line': '📱 Line 提醒',
}[selected]


# ============================================================
# 1) 專案總覽（含首頁儀表板）
# ============================================================
if page == '📊 專案總覽':
    if not tasks:
        st.title('📊 專案總覽')
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
          <div style="font-weight:700; color:{COLORS['ink']}; font-size:1.1rem;">📋 全部任務</div>
          <div style="flex:1; height:1px; background:{COLORS['line']};"></div>
        </div>
        """, unsafe_allow_html=True)

        # 搜尋列 + 燈號篩選
        col_s1, col_s2 = st.columns([3, 2])
        with col_s1:
            search_q = st.text_input(
                '🔍 搜尋任務', '',
                placeholder='搜尋任務名稱 / 負責人 / 目的…',
                key='search_q', label_visibility='collapsed',
            )
        with col_s2:
            filter_status = st.selectbox(
                '燈號',
                ['全部燈號', '🟣 已逾期', '🔴 緊急', '🟡 注意', '🟢 正常', '✅ 已完成'],
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
                if st.button('💾 儲存', type='primary', use_container_width=True):
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
                if st.button('🗑️ 刪除', use_container_width=True):
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
              <div style="font-size:3rem;">🔍</div>
              <div style="margin-top:8px; font-size:0.95rem;">沒有符合條件的任務</div>
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
                      <div style="font-size:0.75rem; color:{COLORS['ink_soft']}; min-width:90px; text-align:right;">📅 {task.get('when_end','未設定')}</div>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            with btn_col:
                st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
                if st.button('✏️', key=f'edit_{i}_{task.get("task_id","")[:6]}',
                             help='編輯', use_container_width=True):
                    _edit_dialog(task)


# ============================================================
# 2) 匯入會議記錄
# ============================================================
elif page == '📥 匯入會議記錄':
    st.title('📥 匯入 Google Drive 會議記錄')
    st.caption('系統每小時也會由 GitHub Actions 自動掃描，這裡提供手動立即匯入。')

    if st.button('🔄 掃描所有子資料夾'):
        with st.spinner('正在掃描...'):
            try:
                service = get_drive_service()
                from lib.config import get_drive_folder_id
                files = list_doc_files(service, get_drive_folder_id())
                st.session_state['drive_files'] = files
                st.success(f'找到 {len(files)} 個會議記錄檔案')
            except Exception as e:
                st.error(f'掃描失敗：{e}')

    if 'drive_files' in st.session_state and st.session_state['drive_files']:
        files = st.session_state['drive_files']
        selected = st.selectbox('選擇要匯入的會議記錄', [f['name'] for f in files])
        selected_file = next(f for f in files if f['name'] == selected)
        if st.button('🤖 AI 解析並匯入'):
            with st.spinner('AI 正在解析會議記錄，請稍候...'):
                try:
                    service = get_drive_service()
                    text = extract_text(service, selected_file['id'], selected_file['mimeType'], selected_file['name'])
                    result = parse_meeting(text, selected_file['name'])
                    new_tasks = result.get('tasks', [])
                    now = datetime.now().strftime('%Y-%m-%d %H:%M')
                    for t in new_tasks:
                        t['source_file'] = selected_file['name']
                        t['imported_at'] = now
                    n = append_tasks(new_tasks)
                    refresh_data()
                    st.success(f'成功匯入 {n} 個行動事項！')
                    st.session_state['parsed_tasks'] = new_tasks
                except Exception as e:
                    st.error(f'解析失敗：{e}')

    if 'parsed_tasks' in st.session_state:
        st.subheader('📋 AI 解析結果')
        for t in st.session_state['parsed_tasks']:
            status_text, _ = get_status(t.get('when_end', ''), int(t.get('progress', 0)))
            st.markdown(f"""
**{t.get('what', '')}**
- 部門：{t.get('who_dept', '')} ｜ 負責人：{t.get('who_person', '')}
- 截止：{t.get('when_end', '未設定')} ｜ 狀態：{status_text}
- 目的：{t.get('why', '')}
---""")


# ============================================================
# 3) 統計報表
# ============================================================
elif page == '📈 統計報表':
    st.title('📈 統計報表')
    if not tasks:
        st.info('尚無資料，請先匯入會議記錄')
    else:
        col1, col2, col3, col4 = st.columns(4)
        total = len(tasks)
        completed_count = sum(1 for t in tasks if int(t.get('progress', 0)) >= 100)
        purple_count = sum(1 for t in tasks if get_status(t.get('when_end', ''), int(t.get('progress', 0)))[1] == 'purple')
        red_count = sum(1 for t in tasks if get_status(t.get('when_end', ''), int(t.get('progress', 0)))[1] == 'red')
        overall_rate = round(completed_count / total * 100, 1) if total > 0 else 0
        col1.metric('📋 總事項數', total)
        col2.metric('✅ 完成率', f'{overall_rate}%')
        col3.metric('🔴 緊急', red_count)
        col4.metric('🟣 逾期', purple_count)

        st.divider()
        st.subheader('📈 完成率趨勢圖')
        history = cached_history()
        if len(history) >= 2:
            hist_df = pd.DataFrame(history)
            hist_df['date'] = pd.to_datetime(hist_df['date'])
            hist_df = hist_df.sort_values('date').set_index('date')
            st.line_chart(hist_df[['completion_rate', 'avg_progress']], height=300)
            st.caption('藍線：完成率(%) ｜ 橘線：平均進度(%)')
        else:
            st.info('趨勢圖需要至少 2 天的資料才能顯示，目前資料累積中...')
            if history:
                st.write(f"今日完成率：{history[-1].get('completion_rate', 0)}%")
                st.write(f"今日平均進度：{history[-1].get('avg_progress', 0)}%")

        st.divider()
        st.subheader('🏢 各部門完成率')
        dept_counts: dict[str, dict] = {}
        for t in tasks:
            dept = t.get('who_dept', '未分類')
            d = dept_counts.setdefault(dept, {'total': 0, 'completed': 0, 'progress_sum': 0})
            d['total'] += 1
            p = int(t.get('progress', 0))
            if p >= 100:
                d['completed'] += 1
            d['progress_sum'] += p
        dept_rows = []
        for dept, data in dept_counts.items():
            comp_rate = round(data['completed'] / data['total'] * 100, 1) if data['total'] > 0 else 0
            avg_prog = round(data['progress_sum'] / data['total'], 1) if data['total'] > 0 else 0
            dept_rows.append({
                '部門': dept, '總事項': data['total'], '已完成': data['completed'],
                '完成率%': comp_rate, '平均進度%': avg_prog,
            })
        dept_df = pd.DataFrame(dept_rows).sort_values('完成率%', ascending=False)
        st.dataframe(dept_df, use_container_width=True, hide_index=True)
        st.bar_chart(dept_df.set_index('部門')[['完成率%', '平均進度%']], height=300)

        st.divider()
        st.subheader('📅 本週到期事項')
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
            if 0 <= days_left <= 7:
                week_rows.append({
                    '任務名稱': t.get('what', ''),
                    '負責部門': t.get('who_dept', ''),
                    '負責人': t.get('who_person', ''),
                    '截止日期': t.get('when_end', ''),
                    '剩餘天數': days_left,
                    '進度%': int(t.get('progress', 0)),
                })
        if week_rows:
            st.dataframe(pd.DataFrame(week_rows).sort_values('剩餘天數'), use_container_width=True, hide_index=True)
        else:
            st.info('本週無到期事項')

        st.divider()
        excel_data = export_to_excel(tasks)
        st.download_button(
            label='📥 下載完整專案追蹤表 (.xlsx)',
            data=excel_data,
            file_name=f'專案追蹤_{date.today()}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )


# ============================================================
# 4) 週報
# ============================================================
elif page == '📋 週報':
    st.title('📋 週報產生')
    if not tasks:
        st.info('尚無資料，請先匯入會議記錄')
    else:
        if st.button('📊 產出本週週報'):
            report = generate_weekly_report(tasks)
            st.text_area('週報內容', report, height=600)
            st.download_button(
                '⬇️ 下載週報文字檔', report,
                file_name=f'週報_{date.today()}.txt', mime='text/plain',
            )


# ============================================================
# 5) Line 提醒
# ============================================================
elif page == '📱 Line 提醒':
    st.title('📱 一鍵產出 Line 提醒')
    if st.button('🔔 產出今日紅燈／紫燈提醒'):
        msg = generate_line_message(tasks)
        st.text_area('複製以下內容貼到 Line 群組', msg, height=400)
        st.download_button(
            '⬇️ 下載成文字檔', msg,
            file_name=f'line提醒_{date.today()}.txt', mime='text/plain',
        )
