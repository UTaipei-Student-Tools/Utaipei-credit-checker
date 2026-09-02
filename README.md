---
title: UTaipei Credit Audit
emoji: 🎓
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# UTaipei Credit Audit

臺北市立大學畢業學分預估工具。目前支援：

- 地球環境暨生物資源學系 114 學年度、非師培主修。
- 地球環境與生命科學兩個專業領域。
- 物化系應用化學組雙主修、資訊科學系雙主修與輔系的初步預估。

雙主修、輔系、兼充、替代科目及人工核准仍以教務處與系所正式審核為準。

## 線上版本

- GitHub Pages 前端：`https://jimmymochi.github.io/utaipei-credit-audit/`
- Hugging Face 完整部署：`https://sapphirejimmy-utaipei-credit-audit.hf.space/`

GitHub Pages 只提供靜態介面；學分解析與計算會送到 Hugging Face FastAPI 後端。後端只接受來自指定 Pages 網域的跨來源請求，且不啟用校務系統帳密登入。

## 正確性設計

- 解析失敗時採 fail-closed：不產生看似正常但可能漏算的結果。
- 回傳 `complete`、`partial`、`failed` 資料品質與解析統計。
- 未知成績不預設為及格，而是列入人工確認。
- 114 學年度規則包含上下學期同名課、服務學習與大學生活學習與輔導等零學分條件。
- API 公開回應不包含解析器的 `raw` 原始資料。
- 規則結果會顯示版本、正式來源與檢核日期。

## 隱私與安全

- Hugging Face 公開部署預設 `ENABLE_REMOTE_LOGIN=false`，不接收校務系統帳密。
- 手動上傳檔案只寫入單次請求的暫存目錄，完成後刪除。
- 上傳有容量、副檔名與 PDF 檔頭驗證。
- 回應使用 `Cache-Control: no-store`。
- 日誌過濾 password、username、Cookie、Authorization 與 token 等敏感欄位。
- 若在可信任的本機環境啟用帳密模式，爬蟲只讀取歷年成績與選課結果，不點擊成績確認等寫入按鈕。

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
playwright install chromium
ruff check .
pytest -q
uvicorn app.web.main:app --host 0.0.0.0 --port 7860
```

若只在可信任的本機環境使用校務系統登入：

```powershell
$env:ENABLE_REMOTE_LOGIN="true"
uvicorn app.web.main:app --host 127.0.0.1 --port 7860
```

## CLI

```powershell
utaipei-credit-audit audit --transcript path\to\transcript.pdf --selection-html path\to\selection.html
```

## Docker

```powershell
docker build -t utaipei-credit-audit .
docker run --rm -p 7860:7860 utaipei-credit-audit
```

## GitHub to Hugging Face

Repository secrets：

- `HF_TOKEN`：可寫入目標 Space 的 Hugging Face token。
- `HF_SPACE_REPO`：例如 `Sapphirejimmy/utaipei-credit-audit`。

Pull request 會執行 lint、測試、Python 編譯與 Docker build；合併到 `main` 後才部署 Hugging Face。

## GitHub Pages

`scripts/build_pages.py` 會從與 Hugging Face 共用的 `app/web/static` 建立 Pages artifact，避免維護兩套介面。`.github/workflows/deploy-pages.yml` 在 `main` 更新後發布該 artifact。

## 規則來源

地生系 114 學年度規則依據「114學年度地球環境暨生物資源學系課程手冊」。工具僅供預估，正式認定以學校公告與人工審核為準。
