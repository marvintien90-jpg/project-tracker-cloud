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

from lib.config import DEPARTMENTS
from lib.drive_client import extract_text, get_drive_service, list_doc_files
from lib.ai_parser import parse_meeting
from lib.reports import export_to_excel, generate_line_message, generate_weekly_report
from lib.sheets_db import (
    append_tasks, delete_task, load_history, load_tasks, update_task, upsert_history,
)
from lib.status import COLOR_EMOJI, get_status

st.set_page_config(
    page_title='總部專案追蹤助理',
    page_icon='📋',
    layout='wide',
    initial_sidebar_state='expanded',
)


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
# 側邊欄
# ============================================================
with st.sidebar:
    st.title('📋 總部專案\n進度追蹤助理')
    st.caption('雲端版 v1.0')
    st.divider()
    page = st.radio(
        '功能選單',
        ['📊 專案總覽', '📥 匯入會議記錄', '📈 統計報表', '📋 週報', '📱 Line 提醒'],
        label_visibility='collapsed',
    )
    st.divider()

    total = len(tasks)
    completed_count = sum(1 for t in tasks if int(t.get('progress', 0)) >= 100)
    purple_count = sum(1 for t in tasks if get_status(t.get('when_end', ''), int(t.get('progress', 0)))[1] == 'purple')
    red_count = sum(1 for t in tasks if get_status(t.get('when_end', ''), int(t.get('progress', 0)))[1] == 'red')
    st.markdown(f'**📋 總事項：{total} 件**')
    st.markdown(f'**🔴 緊急：{red_count} 件**')
    st.markdown(f'**🟣 逾期：{purple_count} 件**')
    st.markdown(f'**✅ 完成：{completed_count} 件**')
    st.divider()
    if st.button('🔄 重新載入資料'):
        refresh_data()
        st.rerun()


# ============================================================
# 1) 專案總覽
# ============================================================
if page == '📊 專案總覽':
    st.title('📊 專案總覽')
    if not tasks:
        st.info('尚無任何專案，請先到「匯入會議記錄」頁面匯入資料')
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filter_dept = st.selectbox('篩選部門', ['全部'] + DEPARTMENTS)
        with col_f2:
            filter_status = st.selectbox(
                '篩選燈號',
                ['全部', '🟣 已逾期', '🔴 緊急', '🟡 注意', '🟢 正常', '✅ 已完成'],
            )

        for i, task in enumerate(tasks):
            if filter_dept != '全部' and task.get('who_dept') != filter_dept:
                continue
            status_text, color = get_status(task.get('when_end', ''), int(task.get('progress', 0)))
            if filter_status != '全部' and filter_status not in status_text:
                continue

            emoji = COLOR_EMOJI.get(color, '🟢')
            label = f"{emoji} {task.get('what', '未命名')} ｜ {task.get('who_dept', '')} {task.get('who_person', '')} ｜ {status_text}"
            with st.expander(label):
                col1, col2 = st.columns(2)
                with col1:
                    new_what = st.text_input('任務名稱', task.get('what', ''), key=f'what_{i}')
                    dept_val = task.get('who_dept', DEPARTMENTS[0])
                    dept_index = DEPARTMENTS.index(dept_val) if dept_val in DEPARTMENTS else 0
                    new_dept = st.selectbox('負責部門', DEPARTMENTS, index=dept_index, key=f'dept_{i}')
                    new_person = st.text_input('負責人', task.get('who_person', ''), key=f'person_{i}')
                    new_where = st.text_input('執行地點', task.get('where', ''), key=f'where_{i}')
                with col2:
                    new_why = st.text_area('目的', task.get('why', ''), key=f'why_{i}')
                    new_how = st.text_area('執行方式', task.get('how', ''), key=f'how_{i}')
                    new_start = st.text_input('開始日期 (YYYY-MM-DD)', task.get('when_start', ''), key=f'start_{i}')
                    new_end = st.text_input('截止日期 (YYYY-MM-DD)', task.get('when_end', ''), key=f'end_{i}')
                new_progress = st.slider('進度 %', 0, 100, int(task.get('progress', 0)), key=f'progress_{i}')

                col_save, col_del = st.columns([1, 4])
                with col_save:
                    if st.button('💾 儲存', key=f'save_{i}'):
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
                                st.error('找不到對應的 task_id，無法更新')
                        except Exception as e:
                            st.error(f'儲存失敗：{e}')
                with col_del:
                    if st.button('🗑️ 刪除此事項', key=f'del_{i}'):
                        try:
                            if delete_task(task.get('task_id', '')):
                                refresh_data()
                                st.success('已刪除')
                                st.rerun()
                            else:
                                st.error('刪除失敗（找不到對應 row）')
                        except Exception as e:
                            st.error(f'刪除失敗：{e}')


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
