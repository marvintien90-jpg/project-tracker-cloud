"""品牌視覺系統 — 色票、字型、CSS 注入。

使用方式：在 app.py 的 st.set_page_config 之後立刻呼叫 apply_brand()。
"""
from __future__ import annotations

import streamlit as st


# ============================================================
# 色票（給 Plotly / 狀態 / 漸層用）
# ============================================================
COLORS = {
    # 主品牌色
    'primary': '#E85D3A',       # 石鍋橘
    'primary_dark': '#D04020',
    'primary_light': '#F27D5A',
    'ink': '#1A1A1A',           # 墨黑
    'ink_soft': '#4A4A4A',
    'cream': '#FAF7F2',         # 奶白
    'cream_dark': '#F0EBE3',
    'white': '#FFFFFF',
    'line': '#E5E0D8',

    # 狀態色（任務燈號）
    'purple': '#8B5CF6',   # 逾期
    'red': '#DC2626',      # 緊急
    'yellow': '#F59E0B',   # 注意
    'green': '#10B981',    # 正常
    'complete': '#6B7280', # 完成
    'info': '#3B82F6',
}

# 給 Plotly 用的離散色盤
PLOTLY_PALETTE = [
    '#E85D3A', '#F59E0B', '#10B981', '#3B82F6', '#8B5CF6',
    '#DC2626', '#6B7280', '#EC4899', '#14B8A6', '#F97316',
]


# ============================================================
# 全站 CSS
# ============================================================
def _base_css() -> str:
    return f"""
<style>
/* ---------- Google Fonts ---------- */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700;900&family=Inter:wght@400;600;700;800&display=swap');

/* ---------- 全站字型 ---------- */
html, body, [class*="css"], .main, .stApp {{
  font-family: 'Noto Sans TC', 'PingFang TC', 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}}

/* 英數字用 Inter（讓數字等寬好讀） */
.stMetricValue, .stProgress > div, [data-testid="stMetricValue"] {{
  font-family: 'Inter', 'Noto Sans TC', sans-serif !important;
  font-variant-numeric: tabular-nums;
}}

h1, h2, h3, h4 {{
  font-family: 'Noto Sans TC', 'PingFang TC', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: -0.02em;
  color: {COLORS['ink']};
}}

/* ---------- 背景：奶白漸層 ---------- */
.stApp {{
  background: linear-gradient(180deg, {COLORS['cream']} 0%, #F3EEE5 100%);
}}

/* ---------- Sidebar：墨黑高級感 ---------- */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #1A1A1A 0%, #2A2A2A 100%);
}}
[data-testid="stSidebar"] * {{
  color: {COLORS['cream']} !important;
}}
[data-testid="stSidebar"] .stRadio label {{
  color: {COLORS['cream']} !important;
  padding: 8px 12px;
  border-radius: 8px;
  transition: all 0.15s;
}}
[data-testid="stSidebar"] .stRadio label:hover {{
  background: rgba(232, 93, 58, 0.15);
}}

/* ---------- 玻璃擬態 KPI 卡 ---------- */
[data-testid="stMetric"] {{
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  padding: 20px 24px !important;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.06),
    0 2px 4px -1px rgba(0, 0, 0, 0.04),
    inset 0 0 0 1px rgba(255, 255, 255, 0.5);
  transition: transform 0.2s, box-shadow 0.2s;
}}
[data-testid="stMetric"]:hover {{
  transform: translateY(-2px);
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.1),
    0 4px 6px -2px rgba(0, 0, 0, 0.05);
}}
[data-testid="stMetricLabel"] {{
  font-size: 0.8rem !important;
  font-weight: 500 !important;
  color: {COLORS['ink_soft']} !important;
  letter-spacing: 0.03em;
}}
[data-testid="stMetricValue"] {{
  font-size: 2.2rem !important;
  font-weight: 800 !important;
  color: {COLORS['ink']} !important;
  line-height: 1.1 !important;
}}

/* ---------- 按鈕 ---------- */
.stButton > button {{
  border-radius: 10px !important;
  font-weight: 600 !important;
  padding: 0.5rem 1.25rem !important;
  transition: all 0.15s !important;
  border: 1.5px solid {COLORS['line']} !important;
}}
.stButton > button:hover {{
  border-color: {COLORS['primary']} !important;
  color: {COLORS['primary']} !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(232, 93, 58, 0.15);
}}
.stButton > button[kind="primary"] {{
  background: linear-gradient(135deg, {COLORS['primary_light']}, {COLORS['primary']}) !important;
  border: none !important;
  color: white !important;
  box-shadow: 0 2px 8px rgba(232, 93, 58, 0.3);
}}
.stButton > button[kind="primary"]:hover {{
  background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['primary_dark']}) !important;
  box-shadow: 0 6px 16px rgba(232, 93, 58, 0.4);
}}

/* ---------- Download 按鈕 ---------- */
.stDownloadButton > button {{
  border-radius: 10px !important;
  font-weight: 600 !important;
}}

/* ---------- Expander ---------- */
.streamlit-expanderHeader, [data-testid="stExpander"] summary {{
  background: rgba(255, 255, 255, 0.6) !important;
  border-radius: 12px !important;
  border: 1px solid {COLORS['line']} !important;
  font-weight: 500 !important;
  padding: 14px 18px !important;
  transition: all 0.15s;
}}
.streamlit-expanderHeader:hover, [data-testid="stExpander"] summary:hover {{
  border-color: {COLORS['primary']} !important;
  background: rgba(255, 255, 255, 0.95) !important;
}}

/* ---------- Text input / Selectbox ---------- */
.stTextInput > div > div > input,
.stSelectbox > div > div,
.stTextArea > div > div > textarea,
.stDateInput > div > div > input {{
  border-radius: 10px !important;
  border: 1.5px solid {COLORS['line']} !important;
  transition: all 0.15s !important;
}}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stDateInput > div > div > input:focus {{
  border-color: {COLORS['primary']} !important;
  box-shadow: 0 0 0 3px rgba(232, 93, 58, 0.12) !important;
}}

/* ---------- Slider ---------- */
.stSlider [data-baseweb="slider"] [role="slider"] {{
  background: {COLORS['primary']} !important;
  box-shadow: 0 0 0 3px rgba(232, 93, 58, 0.15) !important;
}}

/* ---------- Dataframe ---------- */
[data-testid="stDataFrame"] {{
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}}

/* ---------- 移除預設 Streamlit 頁首 Deploy 按鈕空間 ---------- */
header[data-testid="stHeader"] {{
  background: transparent !important;
}}

/* ---------- 主內容區上下padding ---------- */
.block-container {{
  padding-top: 2rem !important;
  padding-bottom: 4rem !important;
  max-width: 1200px !important;
}}

/* ---------- 手機響應 ---------- */
@media (max-width: 768px) {{
  .block-container {{
    padding: 1rem 0.75rem 6rem !important;
  }}
  [data-testid="stMetric"] {{
    padding: 14px 16px !important;
  }}
  [data-testid="stMetricValue"] {{
    font-size: 1.6rem !important;
  }}
  h1 {{ font-size: 1.6rem !important; }}
  h2 {{ font-size: 1.3rem !important; }}
}}

/* ---------- 自訂卡片 class ---------- */
.brand-card {{
  background: {COLORS['white']};
  border-radius: 16px;
  padding: 20px 22px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  border: 1px solid {COLORS['line']};
  margin-bottom: 12px;
  transition: all 0.2s;
}}
.brand-card:hover {{
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}}

/* 任務卡左側色條 */
.brand-card-row {{
  display: flex;
  align-items: center;
  gap: 12px;
}}
.status-bar {{
  width: 4px;
  height: 36px;
  border-radius: 2px;
  flex-shrink: 0;
}}
.status-bar.purple {{ background: {COLORS['purple']}; }}
.status-bar.red {{ background: {COLORS['red']}; }}
.status-bar.yellow {{ background: {COLORS['yellow']}; }}
.status-bar.green {{ background: {COLORS['green']}; }}
.status-bar.complete {{ background: {COLORS['complete']}; }}

/* Badge / Tag */
.brand-tag {{
  display: inline-block;
  padding: 3px 10px;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 999px;
  background: {COLORS['cream_dark']};
  color: {COLORS['ink_soft']};
  margin-right: 6px;
}}
.brand-tag.primary {{
  background: rgba(232, 93, 58, 0.12);
  color: {COLORS['primary_dark']};
}}
.brand-tag.purple {{ background: rgba(139, 92, 246, 0.12); color: {COLORS['purple']}; }}
.brand-tag.red {{ background: rgba(220, 38, 38, 0.12); color: {COLORS['red']}; }}
.brand-tag.yellow {{ background: rgba(245, 158, 11, 0.15); color: #B45309; }}
.brand-tag.green {{ background: rgba(16, 185, 129, 0.12); color: #047857; }}

/* 漸變標題 */
.brand-gradient-title {{
  background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['primary_dark']});
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-weight: 900;
  letter-spacing: -0.02em;
}}

/* Hero KPI 數字 (手動帶 class 用) */
.hero-num {{
  font-family: 'Inter', sans-serif;
  font-size: 3rem;
  font-weight: 800;
  line-height: 1;
  color: {COLORS['ink']};
  font-variant-numeric: tabular-nums;
}}
.hero-num-sub {{
  font-size: 0.85rem;
  color: {COLORS['ink_soft']};
  font-weight: 500;
  margin-top: 4px;
}}

/* ---------- Loading skeleton shimmer ---------- */
.skeleton {{
  background: linear-gradient(90deg, {COLORS['cream_dark']} 25%, #EFE9DF 50%, {COLORS['cream_dark']} 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;
}}
@keyframes shimmer {{
  0% {{ background-position: -200% 0; }}
  100% {{ background-position: 200% 0; }}
}}

/* ---------- Sticky 頂部導航（滾動時仍可見） ---------- */
div[data-testid="stHorizontalBlock"]:has(> div > div > [data-testid*="option_menu"]),
.stHorizontalBlock:has(.option-menu) {{
  position: sticky;
  top: 0;
  z-index: 100;
}}

/* ---------- 錯誤訊息美化 ---------- */
[data-testid="stAlert"][data-baseweb="notification"] {{
  border-radius: 12px !important;
  border-left-width: 4px !important;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}}

/* ---------- st.code copy button 加強 ---------- */
.stCode {{
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}}
.stCode pre {{
  background: {COLORS['ink']} !important;
  color: {COLORS['cream']} !important;
  font-family: 'Noto Sans TC', 'Inter', monospace !important;
  font-size: 0.9rem !important;
  line-height: 1.7 !important;
}}

/* ---------- Dialog 整體 ---------- */
div[role="dialog"] {{
  border-radius: 18px !important;
  box-shadow: 0 24px 60px rgba(0,0,0,0.2) !important;
}}

/* ---------- 頂部 Streamlit 工具列邊距 ---------- */
.stAppDeployButton, div[data-testid="stToolbar"] {{
  /* 讓頂部更乾淨 */
}}

/* ---------- Balloons / confetti 區域 ---------- */
/* Streamlit 自帶 */

/* ---------- 任務卡 hover 效果 ---------- */
div[data-testid="stHorizontalBlock"]:hover > div:first-child > div > div[style*="border-left: 4px solid"] {{
  transform: translateX(2px);
  transition: transform 0.15s;
}}
</style>
"""


_PWA_HEAD = """
<link rel="manifest" href="/app/static/manifest.json">
<meta name="theme-color" content="#E85D3A">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="專案追蹤">
<link rel="apple-touch-icon" href="/app/static/logo.svg">
<link rel="icon" type="image/svg+xml" href="/app/static/favicon.svg">
<!-- Bootstrap Icons (扁平線條 icon) -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
"""


# ============================================================
# Icon helper
# ============================================================
def icon(name: str, size: str = '1em', color: str = None) -> str:
    """產生 Bootstrap Icon HTML。name 不含 'bi-' 前綴。"""
    color_style = f'color:{color};' if color else ''
    return f'<i class="bi bi-{name}" style="font-size:{size};{color_style}"></i>'


def apply_brand() -> None:
    """注入品牌 CSS + PWA meta 到 Streamlit 頁面。"""
    st.markdown(_PWA_HEAD + _base_css(), unsafe_allow_html=True)


def card_html(body: str, *, cls: str = '') -> str:
    """回傳一個品牌卡片的 HTML 片段。"""
    return f'<div class="brand-card {cls}">{body}</div>'


def tag_html(text: str, variant: str = '') -> str:
    """回傳 badge/tag。variant: primary / purple / red / yellow / green / 空"""
    return f'<span class="brand-tag {variant}">{text}</span>'
