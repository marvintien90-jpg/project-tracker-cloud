"""Plotly 互動圖表元件（品牌色）。"""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from .brand import COLORS, PLOTLY_PALETTE


def _apply_brand_layout(fig: go.Figure, height: int = 380) -> go.Figure:
    """所有圖表統一套用品牌版面設定。"""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=30),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(255,255,255,0.3)',
        font=dict(
            family="'Noto Sans TC', 'Inter', sans-serif",
            size=12,
            color=COLORS['ink'],
        ),
        title=dict(font=dict(size=15, color=COLORS['ink']), x=0.01),
        legend=dict(
            orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
            bgcolor='rgba(0,0,0,0)',
        ),
        hoverlabel=dict(
            bgcolor='white',
            bordercolor=COLORS['line'],
            font_size=12,
            font_family="'Noto Sans TC', sans-serif",
        ),
    )
    fig.update_xaxes(gridcolor=COLORS['line'], zerolinecolor=COLORS['line'], showline=False)
    fig.update_yaxes(gridcolor=COLORS['line'], zerolinecolor=COLORS['line'], showline=False)
    return fig


# ============================================================
# 完成率趨勢
# ============================================================
def progress_trend(history: list[dict]) -> go.Figure:
    df = pd.DataFrame(history)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['completion_rate'],
        mode='lines+markers',
        name='完成率 %',
        line=dict(color=COLORS['primary'], width=3),
        marker=dict(size=8, line=dict(color='white', width=2)),
        fill='tozeroy',
        fillcolor='rgba(232,93,58,0.12)',
        hovertemplate='<b>%{x|%Y/%m/%d}</b><br>完成率 %{y}%<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['avg_progress'],
        mode='lines+markers',
        name='平均進度 %',
        line=dict(color=COLORS['info'], width=2, dash='dash'),
        marker=dict(size=6),
        hovertemplate='<b>%{x|%Y/%m/%d}</b><br>平均進度 %{y}%<extra></extra>',
    ))
    fig.update_layout(title='完成率 × 平均進度 趨勢')
    return _apply_brand_layout(fig, height=360)


# ============================================================
# 部門燈號堆疊長條（同時看完成/進行/緊急/逾期）
# ============================================================
def dept_status_stacked(dept_breakdown: dict) -> go.Figure:
    """dept_breakdown: {部門: {complete, green, yellow, red, purple}}"""
    depts = list(dept_breakdown.keys())

    statuses = [
        ('complete', '已完成', COLORS['complete']),
        ('green', '正常', COLORS['green']),
        ('yellow', '注意', COLORS['yellow']),
        ('red', '緊急', COLORS['red']),
        ('purple', '逾期', COLORS['purple']),
    ]

    fig = go.Figure()
    for key, label, color in statuses:
        fig.add_trace(go.Bar(
            y=depts,
            x=[dept_breakdown[d].get(key, 0) for d in depts],
            name=label,
            orientation='h',
            marker=dict(color=color, line=dict(color='white', width=1)),
            hovertemplate=f'<b>%{{y}}</b><br>{label}：%{{x}} 件<extra></extra>',
        ))
    fig.update_layout(
        title='各部門事項燈號分布',
        barmode='stack',
        legend=dict(orientation='h', yanchor='bottom', y=1.05, x=0.01, xanchor='left'),
    )
    return _apply_brand_layout(fig, height=max(300, 32 * len(depts) + 80))


# ============================================================
# 部門 × 完成率 Heatmap
# ============================================================
def dept_completion_bar(dept_rows: list[dict]) -> go.Figure:
    df = pd.DataFrame(dept_rows).sort_values('完成率%', ascending=True)

    # 依完成率 0-100 產生漸層色
    def _color(pct: float) -> str:
        if pct < 30:
            return COLORS['red']
        elif pct < 60:
            return COLORS['yellow']
        elif pct < 90:
            return COLORS['primary']
        else:
            return COLORS['green']
    colors = [_color(p) for p in df['完成率%']]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df['部門'], x=df['完成率%'],
        orientation='h',
        marker=dict(color=colors, line=dict(color='white', width=1)),
        text=[f"{v}%" for v in df['完成率%']],
        textposition='outside',
        textfont=dict(size=11, color=COLORS['ink'], family="'Inter'"),
        hovertemplate='<b>%{y}</b><br>完成率 %{x}%<br>共 %{customdata} 件<extra></extra>',
        customdata=df['總事項'],
    ))
    fig.update_layout(
        title='各部門完成率排行',
        showlegend=False,
        xaxis=dict(title='完成率 %', range=[0, 110]),
    )
    return _apply_brand_layout(fig, height=max(300, 32 * len(df) + 80))


# ============================================================
# 本週到期 timeline
# ============================================================
def week_due_timeline(week_rows: list[dict]) -> go.Figure:
    df = pd.DataFrame(week_rows).sort_values('剩餘天數')

    def _color(days):
        if days < 0: return COLORS['purple']
        if days <= 3: return COLORS['red']
        if days <= 7: return COLORS['yellow']
        return COLORS['green']

    colors = [_color(d) for d in df['剩餘天數']]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df['任務名稱'].str.slice(0, 25),
        x=df['剩餘天數'],
        orientation='h',
        marker=dict(color=colors, line=dict(color='white', width=1)),
        text=[f"{d} 天" if d >= 0 else f"逾 {-d}" for d in df['剩餘天數']],
        textposition='outside',
        textfont=dict(size=11, family="'Inter'"),
        hovertemplate='<b>%{y}</b><br>剩 %{x} 天<br>%{customdata}<extra></extra>',
        customdata=df['負責部門'] + ' · ' + df['負責人'],
    ))
    fig.update_layout(
        title='本週到期事項倒數',
        showlegend=False,
        xaxis=dict(title='剩餘天數'),
    )
    return _apply_brand_layout(fig, height=max(300, 32 * len(df) + 80))
