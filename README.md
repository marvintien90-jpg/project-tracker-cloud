# 總部專案進度追蹤助理 — 雲端版

把原本本機跑的 Streamlit 助理搬到 Streamlit Community Cloud，
資料庫改用 Google Sheets，會議記錄掃描改由 GitHub Actions 每小時觸發。

電腦關機也能用，手機隨時可看。

---

## 架構

```
┌────────────────────────────┐         ┌──────────────────────────┐
│ GitHub Actions (cron 1h)   │ ──────► │ Google Drive (會議記錄)  │
│  └─ scripts/auto_scan.py   │         └──────────────────────────┘
│       │ Service Account                          │
│       ▼                                          │
│  Google Sheets ◄─────────────────────────────────┘
│  ├─ tasks                                          
│  ├─ scanned_files                                  
│  └─ progress_history                               
└────────────────────────────┘                      
              ▲                                     
              │ gspread (讀寫)                       
              │                                     
        ┌─────┴─────┐                               
        │ Streamlit │  ◄──── 手機/電腦瀏覽器          
        │   Cloud   │                               
        └───────────┘                               
```

---

## 部署步驟

### 1. Google Cloud Service Account
1. https://console.cloud.google.com → 建立／選擇專案
2. 啟用 API：**Google Drive API**、**Google Sheets API**
3. IAM & 管理 → 服務帳戶 → 建立 `project-tracker-bot`
4. 該帳戶 → 金鑰 → 新增 JSON 金鑰 → 下載 JSON
5. 把服務帳戶 email 加入：
   - 會議記錄 Drive 資料夾：**檢視者**
   - Google Sheet 資料庫：**編輯者**

### 2. Google Sheet
1. 新建 Sheet，命名 `專案追蹤資料庫`
2. 建立三個分頁，名稱**完全一致**：
   - `tasks`
   - `scanned_files`
   - `progress_history`
3. 第一次跑時，程式會自動寫入欄位 header（也可以不用手動建欄）
4. 從網址抓 Sheet ID：`docs.google.com/spreadsheets/d/【ID】/edit`

### 3. GitHub repo
```bash
cd ~/Desktop/project-tracker-cloud
git init
git add .
git commit -m "initial cloud version"
git branch -M main
git remote add origin https://github.com/<你的帳號>/project-tracker-cloud.git
git push -u origin main
```

設定 **Repository Secrets**（Settings → Secrets and variables → Actions → New repository secret）：

| Secret 名稱 | 內容 |
|---|---|
| `OPENAI_API_KEY` | sk-proj-xxx |
| `GSPREAD_SPREADSHEET_ID` | 第 2 步的 Sheet ID |
| `DRIVE_FOLDER_ID` | 會議記錄 Drive 資料夾 ID |
| `GCP_SERVICE_ACCOUNT_JSON` | 把 service account JSON **整個檔案內容**貼進去（一行 JSON 字串都可） |

### 4. Streamlit Community Cloud
1. https://share.streamlit.io → New app
2. 連到剛剛的 GitHub repo，main branch，主檔案 `app.py`
3. 進入 App settings → **Secrets**，貼上 `.streamlit/secrets.toml.example` 改好的內容
4. Deploy

### 5. 一次性資料搬移（從本機 JSON 搬進 Sheets）
本地端：
```bash
cd ~/Desktop/project-tracker-cloud
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 本機跑時要有 .streamlit/secrets.toml（複製 .example 改）
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# 編輯 secrets.toml 填好值

python -m scripts.migrate_json_to_sheets
```

跑完去 Google Sheet 確認 `tasks` 分頁有 66 筆資料。

### 6. 驗證
- GitHub → Actions → `Hourly Drive Scan` → 點 **Run workflow** 手動跑一次，看 log 有沒有錯
- Streamlit App URL 在手機開啟，確認五個分頁都正常

---

## 手機加入桌面（PWA 體驗）
- iPhone Safari：分享 → 加入主畫面
- Android Chrome：選單 → 安裝應用程式

---

## 排查

| 症狀 | 原因 / 解法 |
|---|---|
| `無法連線 Google Sheets` | secrets 裡的 `gcp_service_account` 缺欄位，或 Sheet 沒分享給服務帳戶 |
| Drive 掃描 0 個檔案 | Drive 資料夾沒分享給服務帳戶 |
| `gspread.exceptions.APIError 403` | API 沒啟用，去 Cloud Console 啟用 Drive + Sheets |
| AI 解析很慢 | 正常，每份 doc ~5–10 秒 |
| 編輯後沒更新 | 點側邊欄「🔄 重新載入資料」清快取 |

---

## 跟原本本機版的差異

| 項目 | 本機版 | 雲端版 |
|---|---|---|
| 驗證 | OAuth + token.pickle | Service Account JSON |
| 資料儲存 | `data/*.json` | Google Sheets |
| 排程 | LaunchAgent | GitHub Actions cron |
| 週報儲存 | `data/reports/*.txt` | 直接瀏覽器下載（雲端無持久檔案系統） |
| 手機存取 | 同 WiFi 內網 IP | 任何網路皆可 |
