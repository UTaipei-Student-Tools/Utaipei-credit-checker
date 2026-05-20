---
title: UTaipei Science College Credit Checker
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.57.0
app_file: app.py
pinned: false
license: mit
---

# 🎓 臺北市立大學理學院畢業學分自我審查系統 (Hugging Face Space 版)

本專案專為 **臺北市立大學 (北市大) 地球環境暨生物資源學系 (地生系)** 學生打造，能夠自動模擬登入北市大校務系統抓取成績單 PDF，並依據 **114學年度理學院學生手冊** 之畢業標準，精準核算共同必修、通識領域選修、系專門必修、分組選修與自由選修之學分完成度。

系統特別支援 **應用物理暨化學系 (化學組/物理組)** 與 **資訊科學系 (資科系)** 之雙主修與輔系精密學分試算，自動排除重疊必修學分，防止重複計算。

## 🌟 特色功能

1. **實時爬蟲抓取 (Live Scraper)**：輸入學號密碼，系統自動以唯讀模式安全登入校務系統 (`https://my.utaipei.edu.tw/`) 並下載最新歷年成績單 PDF。
2. **本機 Demo 展示 (Offline Demo)**：一鍵載入本機預先快取的成績單 ( student_transcript.pdf )，在不暴露隱私帳密的情況下完整體驗高級儀表板的全部功能。
3. **精緻視覺美學 (Premium UX)**：
   - 融合高級暗色系與霓虹色彩（HSL Harmony）。
   - 採用現代玻璃擬態卡片（Glassmorphism）與滑動懸停動態效果。
   - 提供精密的多層次進度條矩陣與核算藥丸狀態標章 (Badges)。
   - 支援完整的畢業核心必修缺失稽核 (Audits) 與自由選修外系跨系學分試算。
4. **一鍵 Excel/CSV 匯出**：支持將審查後的修課完整列表一鍵下載為試算表檔案。

---

## 🛠️ 本地執行與開發指南

若您想在本機運行此專案：

### 1. 安裝環境與依賴
確保您的本機已安裝 Python 3.8+，並在專案目錄下執行：
```bash
pip install -r requirements.txt
```

### 2. 啟動 Streamlit 服務
在專案根目錄下執行：
```bash
streamlit run app.py
```
啟動後，瀏覽器將會自動開啟 `http://localhost:8501`。

---

## 🚀 Hugging Face Spaces 部署步驟

要在 Hugging Face 上部署本系統，請遵循以下步驟：

1. **註冊/登入 Hugging Face**。
2. 點擊右上角個人頭像，選擇 **"New Space"**。
3. 設定您的 Space 名稱（例如：`utaipei-credit-checker`）。
4. **SDK 選擇**：選擇 **Streamlit**。
5. **Space License**：可選擇 `MIT`。
6. 點擊 **"Create Space"**。
7. 將本專案的所有檔案（包括此 `README.md`, `app.py`, `scraper.py`, `pdf_parser.py`, `credit_engine.py`, `handbook_rules.py`, `requirements.txt` 及 `student_transcript.pdf`）上傳至您的 Hugging Face Space 儲存庫：
   - 您可以使用 Git 命令推送：
     ```bash
     git clone https://huggingface.co/spaces/您的用戶名/您的Space名稱
     # 將本專案的檔案複製進去
     git add .
     git commit -m "Deploy UTaipei Credit Checker with Premium UI"
     git push
     ```
   - 或是直接透過 Hugging Face 的 Web 介面點擊 **"Files and versions" -> "Add file" -> "Upload files"** 上傳檔案。
8. 檔案上傳完成後，Hugging Face 將會自動偵測 `README.md` 中的元數據 (Metadata) 並於 1-2 分鐘內自動建立、編譯、安裝依賴，並一鍵上線您的專案！

---

## 🔒 隱私與安全承諾

- **唯讀存取**：爬蟲完全基於 `requests` 模擬登入，不包含任何資料庫寫入或表單提交修改操作。
- **無密碼儲存**：本系統為無伺服器狀態（Stateless），絕對不會在任何伺服器或 Hugging Face 雲端紀錄或儲存您的帳號密碼。

---
*北市大理學院大一至大四學術審查輔助軟體 - 祝您順利畢業！🎓*
