---
name: 北市大畢業通
description: Dimension 靜謐入口與清楚可核對的學分工作區
colors:
  workspace-accent: "#356858"
  workspace-accent-strong: "#244d41"
  workspace-accent-soft: "#e4eee8"
  workspace-canvas: "#f3f5f2"
  workspace-text: "#20332b"
  workspace-border: "#dce3dc"
  cover-text: "#f4f6f7"
  dark-accent: "#b3d7c4"
typography:
  display:
    fontFamily: "Noto Sans TC, sans-serif"
    fontSize: "clamp(2rem,5vw,3.65rem)"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: ".12em"
  headline:
    fontFamily: "Noto Sans TC, Microsoft JhengHei, system-ui, -apple-system, sans-serif"
    fontSize: "clamp(1.6rem,4vw,2.3rem)"
    fontWeight: 600
    letterSpacing: ".05em"
  body:
    fontFamily: "Noto Sans TC, Microsoft JhengHei, system-ui, -apple-system, sans-serif"
  label:
    fontSize: ".82rem"
    fontWeight: 700
rounded:
  cover-control: "4px"
  ui-sm: "8px"
  ui-md: "13px"
  ui-lg: "20px"
  glass: "999px"
spacing:
  compact: "12px"
  regular: "16px"
  roomy: "24px"
components:
  cover-button:
    backgroundColor: "transparent"
    textColor: "{colors.cover-text}"
    rounded: "{rounded.cover-control}"
  workspace-primary:
    backgroundColor: "{colors.workspace-accent-strong}"
    textColor: "{colors.workspace-canvas}"
    rounded: "{rounded.glass}"
  workspace-primary-hover:
    backgroundColor: "{colors.workspace-accent}"
  workspace-secondary:
    rounded: "{rounded.ui-sm}"
  toolbar-button:
    rounded: "{rounded.glass}"
  source-badge:
    backgroundColor: "{colors.workspace-accent-soft}"
    textColor: "{colors.workspace-accent-strong}"
    rounded: "{rounded.ui-sm}"
    padding: ".25rem .65rem"
  info-card:
    rounded: "{rounded.ui-md}"
    padding: "1.1rem 1.25rem"
---

# Design System: 北市大畢業通

## Overview

**Creative North Star: "靜謐的學分入口"**

Dimension 原始背景、細線與明亮中文字構成安靜的封面；進入後轉為資訊密度較高、以課程核對為中心的工作區。此文件依 `welcome.py`、`static/dimension/theme.css` 與 `ui_components.py` 的實作記錄，使用者指定的 Dimension 方向優先於種子 94de1b63。

**Key Characteristics:**

- 封面置中、細線框定標題與入口。
- 工作區以鼠尾草綠與明暗表面區分操作及資料。
- 玻璃材質集中於工作區工具列與主要按鈕。

## Colors

封面保持暗色攝影背景與淺色文字；工作區使用克制的綠色強調。

### Primary

- 鼠尾草綠：工作區操作、焦點與選取狀態；深綠承載主要按鈕，淡綠承載提示與來源標籤。
- 夜間淡綠：深色工作區的強調色，由目前主題切換。

### Neutral

- 灰綠畫布與深綠文字：亮色工作區的閱讀基底。
- 淺色封面文字：搭配背景暗化處理，不以工作區淺底色覆蓋封面。
- 灰綠邊線：表面分組；成功、警告、錯誤仍沿用既有語意色，不視為品牌配色。

**The Theme Roles Rule.** 工作區元件沿用 `--ui-*` 語意變數；亮色值不可直接套到深色主題。

## Typography

**Display Font:** Noto Sans TC，sans-serif 後備。

**Body Font:** Noto Sans TC，Microsoft JhengHei 與系統無襯線後備。

封面使用中等字重與較開的字距，工作區以較緊湊的標題與表格資訊呈現。字級為按角色設定的流動階層，沒有固定比例音階；不另引入裝飾字體。課程與資料表使用等寬數字對齊。

### Hierarchy

- Display：封面產品名稱，尺寸與字距依前置 token。
- Headline：工作區頁首，較封面緊湊。
- Body：封面說明為（16px），行高（1.9）；窄螢幕改為（14px）。一般工作區文字繼承既有排版。
- Label：來源標籤等短資訊；不延伸為裝飾性前導標。

## Layout

封面內容最大寬度（760px），操作區（420px），工作區（1120px）。封面主標題上下細線與置中的 UT 圓形字標構成垂直軸線。工作區標題採底線分隔，工具列靠右，最大寬度（300px）。

封面於（600px）以下縮小字標、字距與內距，兩個入口仍並排。工作區於（1100px）將指標改為兩欄、資訊卡改為一欄；於（768px）讓課程列轉為帶欄位名稱的直排資料；於（480px）將指標改為一欄。保留安全區內距與原生頁面捲動。

## Elevation & Depth

封面深度來自背景圖與暗色遮罩，入口按鈕為透明細框。資料卡平時無陰影，以邊線與底色分層；部分指標與一般控制項在滑入時使用既有柔影。工作區工具列及主要按鈕具有內側高光、柔影、模糊及環形反光邊緣。

**The Glass Scope Rule.** 玻璃材質只套用工作區工具列與工作區主要按鈕；封面維持 Dimension 的透明細框控制項。

入場為短暫淡入及向上位移；工具列滑入略微縮小、按下略微傾斜。降低動態偏好停用相關動畫；降低透明度偏好將工具列改為實色表面。

## Shapes

### 畢業要求浮雕卡片（2026-09-08）

使用者指定 Uiverse.io / Codewithvinay 浮雕樣式：保留相反方向的柔和陰影，改為內容自適應高度。
主修要求用鼠尾草綠，雙主修獨立區塊使用淡紫／深紫；標題同時標明身份，不只靠顏色辨識。
實作與完整明暗色票在 `requirement_layout.py`，只改分組和外觀，不改審核數字。

封面採細直線、小圓角按鈕與圓形字標。工作區一般控制項使用小圓角，資訊容器使用中、大圓角；摺疊區塊另為（12px）。玻璃按鈕使用膠囊形，不推廣到資料卡與一般次要按鈕。

## Components

### Buttons

封面兩個動作均為透明細框、最小高度（52px），滑入填入暗灰綠。工作區工具列最小高度（44px），以反光邊緣、玻璃表面表現可操作性；主要按鈕保留實色語意綠。一般次要按鈕沿用既有表面及小圓角。鍵盤焦點有可見外框；禁用狀態保留原生語意。

### Cards / Containers

資料卡使用實色表面與一像素邊框，資訊卡內距依 token；大型區塊採流動內距。摺疊內容在手機縮減內距，不以玻璃效果包覆大量資料。

### Inputs / Fields

輸入框採語意表面色與邊線，控制項最小高度（44px）。選單的焦點框畫在外層容器，內部文字輸入不重複畫框。

### Navigation

封面使用「開始檢查」及「使用說明」；工作區提供「返回封面」及「使用說明」。說明以原生對話框顯示，返回封面保留工作階段資料。封面保留 Dimension 與 CC BY 3.0 來源連結。

### Source Badge

短來源資訊使用淡綠底、深綠字與細框，不當作按鈕或狀態判定的唯一依據。

## Do's and Don'ts

### Do:

- **Do** 保留封面細框入口與工作區玻璃控制項的材質差異。
- **Do** 使用既有語意變數與可見鍵盤焦點，維持明暗主題及降低動態支援。
- **Do** 以直白繁體中文呈現操作與未確認狀態。

### Don't:

- **Don't** 將玻璃效果擴散至封面按鈕、表單與資料卡。
- **Don't** 把封面背景圖當成工作區資料容器的底圖。
- **Don't** 將既有裝飾性 eyebrow 樣式升格為新頁面的排版規則。
