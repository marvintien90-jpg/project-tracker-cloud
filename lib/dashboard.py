"""首頁儀表板元件 — Hero KPI 卡、今日焦點、AI 摘要。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import streamlit as st

from .brand import COLORS
from .config import get_openai_api_key
from .status import get_status


# ============================================================
# 指標計算
# ============================================================
def compute_metrics(tasks: list[dict[str, Any]]) -> dict:
    today = date.today()
    m = {
        'total': len(tasks),
        'completed': 0,
        'in_progress': 0,
        'overdue': 0,   # 紫
        'urgent': 0,    # 紅
        'warning': 0,   # 黃
        'week_due': [],
        'today_due': [],
        'overdue_tasks': [],
        'urgent_tasks': [],
        'dept_counts': {},
        'avg_progress': 0,
    }
    prog_sum = 0
    for t in tasks:
        p = int(t.get('progress', 0))
        prog_sum += p
        status_text, color = get_status(t.get('when_end', ''), p)
        if color == 'complete':
            m['completed'] += 1
        elif color == 'purple':
            m['overdue'] += 1
            m['overdue_tasks'].append(t)
        elif color == 'red':
            m['urgent'] += 1
            m['urgent_tasks'].append(t)
        elif color == 'yellow':
            m['warning'] += 1
        if color in ('green', 'yellow'):
            m['in_progress'] += 1

        dept = t.get('who_dept', '未分類')
        dd = m['dept_counts'].setdefault(dept, {'total': 0, 'done': 0, 'urgent': 0})
        dd['total'] += 1
        if p >= 100:
            dd['done'] += 1
        if color in ('red', 'purple'):
            dd['urgent'] += 1

        # 到期事項
        if t.get('when_end'):
            try:
                end = datetime.strptime(t['when_end'], '%Y-%m-%d').date()
                days_left = (end - today).days
                if days_left == 0:
                    m['today_due'].append(t)
                if 0 <= days_left <= 7:
                    m['week_due'].append(t)
            except ValueError:
                pass

    m['avg_progress'] = round(prog_sum / max(m['total'], 1), 1)
    m['completion_rate'] = round(m['completed'] / max(m['total'], 1) * 100, 1)
    return m


# ============================================================
# Hero KPI 卡組（4 張大卡）
# ============================================================
def render_hero_kpis(m: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)

    def hero_card(col, bi_icon, label, value, suffix, accent, extra=''):
        col.markdown(f"""
        <div style="
          background: rgba(255,255,255,0.7);
          border-radius: 16px;
          padding: 20px 22px;
          border: 1px solid rgba(255,255,255,0.8);
          box-shadow: 0 4px 12px rgba(0,0,0,0.06);
          backdrop-filter: blur(10px);
          position: relative;
          overflow: hidden;
          min-height: 128px;
        ">
          <div style="position:absolute; top:-10px; right:-10px; width:80px; height:80px; background:{accent}; opacity:0.1; border-radius:50%;"></div>
          <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div style="font-size:0.8rem; color:{COLORS['ink_soft']}; font-weight:500;">{label}</div>
            <div style="display:inline-flex; align-items:center; justify-content:center; width:34px; height:34px; border-radius:10px; background:{accent}1F;">
              <i class="bi bi-{bi_icon}" style="font-size:1.1rem; color:{accent};"></i>
            </div>
          </div>
          <div style="font-family:'Inter',sans-serif; font-size:2.6rem; font-weight:800; color:{COLORS['ink']}; line-height:1.1; margin-top:8px; font-variant-numeric: tabular-nums;">
            {value}<span style="font-size:1rem; color:{COLORS['ink_soft']}; margin-left:4px; font-weight:500;">{suffix}</span>
          </div>
          <div style="font-size:0.78rem; color:{COLORS['ink_soft']}; margin-top:6px; min-height:1em;">{extra}</div>
        </div>
        """, unsafe_allow_html=True)

    hero_card(c1, 'list-task', '總追蹤事項', m['total'], '件', COLORS['primary'],
              f"平均進度 {m['avg_progress']}%")
    hero_card(c2, 'check-circle', '完成率', m['completion_rate'], '%', COLORS['green'],
              f"已完成 {m['completed']} 件")
    hero_card(c3, 'exclamation-triangle', '緊急處理', m['urgent'], '件', COLORS['red'],
              "3 天內到期" if m['urgent'] else '本週無緊急')
    hero_card(c4, 'clock-history', '已逾期', m['overdue'], '件', COLORS['purple'],
              '需立即補救' if m['overdue'] else '準時達成')


# ============================================================
# 今日焦點卡（逾期 + 本週到期條列）
# ============================================================
def render_focus_cards(m: dict) -> None:
    c1, c2 = st.columns(2)

    # 逾期清單
    with c1:
        st.markdown(f"""
        <div style="
          background: linear-gradient(135deg, rgba(139,92,246,0.08), rgba(139,92,246,0.02));
          border-left: 4px solid {COLORS['purple']};
          border-radius: 14px;
          padding: 18px 20px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.04);
          margin-bottom: 10px;
        ">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div style="font-weight:700; font-size:1rem; color:{COLORS['purple']}; display:flex; align-items:center; gap:8px;">
              <i class="bi bi-clock-history"></i> 已逾期
            </div>
            <div style="background:{COLORS['purple']}; color:white; padding:2px 10px; border-radius:999px; font-size:0.75rem; font-weight:700;">{len(m['overdue_tasks'])}</div>
          </div>
        """, unsafe_allow_html=True)

        if m['overdue_tasks']:
            today = date.today()
            shown = sorted(m['overdue_tasks'],
                           key=lambda t: t.get('when_end', ''))[:5]
            for t in shown:
                try:
                    end = datetime.strptime(t['when_end'], '%Y-%m-%d').date()
                    days = (today - end).days
                    days_txt = f'逾期 {days} 天'
                except Exception:
                    days_txt = ''
                st.markdown(f"""
                <div style="padding:8px 0; border-bottom:1px solid rgba(139,92,246,0.15);">
                  <div style="font-weight:600; font-size:0.9rem; color:{COLORS['ink']};">{t.get('what','')[:30]}</div>
                  <div style="font-size:0.75rem; color:{COLORS['ink_soft']}; margin-top:2px;">
                    {t.get('who_dept','')} · {t.get('who_person','')} · <span style="color:{COLORS['purple']}; font-weight:600;">{days_txt}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            if len(m['overdue_tasks']) > 5:
                st.markdown(f"<div style='margin-top:8px; font-size:0.75rem; color:{COLORS['ink_soft']}; text-align:center;'>還有 {len(m['overdue_tasks'])-5} 件…</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style='color:#047857; font-size:0.9rem; display:flex; align-items:center; gap:6px;'><i class="bi bi-check2-circle"></i> 目前沒有逾期事項</div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # 本週到期（紅黃）
    with c2:
        st.markdown(f"""
        <div style="
          background: linear-gradient(135deg, rgba(220,38,38,0.06), rgba(245,158,11,0.02));
          border-left: 4px solid {COLORS['red']};
          border-radius: 14px;
          padding: 18px 20px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.04);
          margin-bottom: 10px;
        ">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div style="font-weight:700; font-size:1rem; color:{COLORS['red']}; display:flex; align-items:center; gap:8px;">
              <i class="bi bi-exclamation-triangle"></i> 本週到期
            </div>
            <div style="background:{COLORS['red']}; color:white; padding:2px 10px; border-radius:999px; font-size:0.75rem; font-weight:700;">{len(m['week_due'])}</div>
          </div>
        """, unsafe_allow_html=True)

        if m['week_due']:
            today = date.today()
            shown = sorted(m['week_due'], key=lambda t: t.get('when_end', ''))[:5]
            for t in shown:
                try:
                    end = datetime.strptime(t['when_end'], '%Y-%m-%d').date()
                    days = (end - today).days
                    if days == 0:
                        days_txt = '今天到期'
                        color = COLORS['red']
                    elif days <= 3:
                        days_txt = f'剩 {days} 天'
                        color = COLORS['red']
                    else:
                        days_txt = f'剩 {days} 天'
                        color = '#B45309'
                except Exception:
                    days_txt = ''
                    color = COLORS['ink_soft']
                st.markdown(f"""
                <div style="padding:8px 0; border-bottom:1px solid rgba(220,38,38,0.12);">
                  <div style="font-weight:600; font-size:0.9rem; color:{COLORS['ink']};">{t.get('what','')[:30]}</div>
                  <div style="font-size:0.75rem; color:{COLORS['ink_soft']}; margin-top:2px;">
                    {t.get('who_dept','')} · {t.get('who_person','')} · <span style="color:{color}; font-weight:600;">{days_txt}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            if len(m['week_due']) > 5:
                st.markdown(f"<div style='margin-top:8px; font-size:0.75rem; color:{COLORS['ink_soft']}; text-align:center;'>還有 {len(m['week_due'])-5} 件…</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style='color:#047857; font-size:0.9rem; display:flex; align-items:center; gap:6px;'><i class="bi bi-check2-circle"></i> 本週無事項到期</div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


# ============================================================
# AI 老闆視角摘要（GPT 一句話）
# ============================================================
@st.cache_data(ttl=1800, show_spinner=False)
def _ai_summary_cached(total: int, completed: int, urgent: int, overdue: int,
                       avg_progress: float, top_urgent_titles_str: str) -> str:
    """由 GPT 產生 2-3 句老闆視角的今日摘要。快取 30 分鐘避免每次開頁都打 API。

    注意：top_urgent_titles_str 傳入 \\n 分隔的字串（避免 tuple hashing 問題）。
    """
    try:
        from openai import OpenAI
        api_key = get_openai_api_key()
        if not api_key:
            return '（未設定 OpenAI Key，無法生成 AI 摘要）'

        client = OpenAI(api_key=api_key)
        rate = round(completed / max(total, 1) * 100, 1)
        urgent_block = top_urgent_titles_str if top_urgent_titles_str else '- 無'

        prompt = (
            "你是總部營運長。根據以下專案數據，用 2-3 句繁體中文給老闆「今日專案狀況簡報」。"
            "語氣要專業、有洞察、給具體行動建議。不要用條列，用一段流暢的敘述。\n\n"
            "數據：\n"
            f"- 總追蹤事項：{total} 件\n"
            f"- 已完成：{completed} 件（完成率 {rate}%）\n"
            f"- 平均進度：{avg_progress}%\n"
            f"- 緊急（3 天內到期）：{urgent} 件\n"
            f"- 已逾期：{overdue} 件\n\n"
            "前 3 個最急的事項：\n"
            f"{urgent_block}\n\n"
            "請直接給那段敘述，不要多餘前後文。"
        )
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.4,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f'（AI 摘要暫時無法生成：{type(e).__name__} — {str(e)[:120]}）'


def render_ai_summary(m: dict) -> None:
    top_urgent_list = [t.get('what', '') for t in
                       (m['overdue_tasks'] + m['urgent_tasks'])[:3]]
    top_urgent_str = '\n'.join(f'- {t}' for t in top_urgent_list if t)
    summary = _ai_summary_cached(
        m['total'], m['completed'], m['urgent'], m['overdue'],
        m['avg_progress'], top_urgent_str,
    )
    st.markdown(f"""
    <div style="
      background: linear-gradient(135deg, #1A1A1A 0%, #2A1F1A 100%);
      color: {COLORS['cream']};
      border-radius: 18px;
      padding: 22px 26px;
      margin-bottom: 22px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.15);
      position: relative;
      overflow: hidden;
    ">
      <div style="position:absolute; top:-30px; right:-30px; width:160px; height:160px; background:radial-gradient(circle, {COLORS['primary']}33, transparent); border-radius:50%;"></div>
      <div style="display:flex; align-items:center; gap:12px; margin-bottom:10px; position:relative;">
        <div style="
          background: linear-gradient(135deg, {COLORS['primary_light']}, {COLORS['primary']});
          width: 36px; height: 36px; border-radius: 10px;
          display: inline-flex; align-items: center; justify-content: center;
          box-shadow: 0 2px 8px rgba(232,93,58,0.35);
        "><i class="bi bi-stars" style="color:white; font-size:1.2rem;"></i></div>
        <div>
          <div style="font-weight:700; font-size:0.95rem;">AI 老闆簡報</div>
          <div style="font-size:0.7rem; color:#A09B95;">{datetime.now().strftime('%Y/%m/%d %H:%M')} · 30 分快取</div>
        </div>
      </div>
      <div style="font-size:0.98rem; line-height:1.7; position:relative; letter-spacing:0.01em;">
        {summary}
      </div>
    </div>
    """, unsafe_allow_html=True)
