---
title: UTaipei Credit Audit
emoji: 🎓
colorFrom: teal
colorTo: cyan
sdk: docker
app_port: 7860
pinned: false
---

# utaipei-credit-audit

臺北市立大學畢業學分審核工具。預設支援地球環境暨生物資源學系非師培主修，並支援物化系應用化學組雙主修與資訊科學系雙主修。

## Safety model

- 校務系統帳密每次輸入，只保存在單次請求記憶體中。
- 不把帳密、成績單 PDF、個資報告提交到 GitHub 或 Hugging Face。
- 爬蟲只讀取「學生歷年成績查詢」與「選課結果查詢」，只點下載歷年成績單等唯讀連結。
- 遇到 CAPTCHA/MFA/登入異常會停止並回傳明確錯誤。
- Hugging Face 若無法連到校務系統，可使用手動上傳 PDF/HTML fallback。

## Local development

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
playwright install chromium
pytest
uvicorn app.web.main:app --host 0.0.0.0 --port 7860
```

## CLI

```powershell
utaipei-credit-audit audit --transcript path\\to\\transcript.pdf --selection-html path\\to\\selection.html
```

## Docker

```powershell
docker build -t utaipei-credit-audit .
docker run --rm -p 7860:7860 utaipei-credit-audit
```

## GitHub to Hugging Face

Create a private GitHub repo named `utaipei-credit-audit`. Add these GitHub Secrets:

- `HF_TOKEN`: Hugging Face token with write access to the target Space.
- `HF_SPACE_REPO`: target Space repo, for example `username/utaipei-credit-audit`.

The workflow runs tests and Docker build, then syncs the repo to the Hugging Face Space.
