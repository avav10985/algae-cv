# algae-cv

藻類影像分析工具集 — 結合**顯微鏡細胞計數**與**手機色彩光度法**估算藻類濃度。

---

## 為什麼有這個專案

藻類培養監測通常仰賴血球計數器+顯微鏡,過程繁瑣。`algae-cv` 想做兩件事:

1. **顯微鏡照片** → 用 fine-tuned Cellpose 自動偵測細胞 + 套用血球計數器規則 → 細胞濃度(cells/mL)
2. **手機照片**(培養瓶/燒杯)→ 從顏色推算細胞濃度 + 葉綠素濃度 → 不用顯微鏡也能即時監測

最終目標:**用手機做藻類培養的快速濃度檢測**。

---

## 工作流程

```
[訓練階段]                          [部署階段]
顯微鏡照片                          手機照片
     ↓                                 ↓
  Cellpose 標注                  RGB 顏色分析
  Fine-tune cpsam模型             Beer-Lambert 律
     ↓                                 ↓
  L-shape 規則計數               迴歸預測濃度
     ↓                                 ↓
  cells/mL (Ground Truth)        cells/mL (即時)
                  ↓ 訓練/校正
              迴歸模型(顏色 → 濃度)
```

---

## 目錄結構

```
algae-cv/
├── colabtest/finetune/          顯微鏡細胞計數工作流(Colab)
│   ├── step1 ~ step7              標注 → 訓練 → 推理 → 計數
│   ├── auto_label_colab.py        自動標注
│   └── count_lshape.py            血球計數器 L-shape 規則
│
├── algae_app/                   手機 app(React Native + Expo,開發中)
│
├── 參考資料/                    技術筆記、原專案演算法、DIY 光譜儀
├── 對話紀錄/                    開發過程的對話備份
│
├── cellpose_portable/           可攜版 cellpose 環境(備用)
├── cellpose_test.py             單張圖 cellpose 測試腳本
│
├── CLAUDE.md                    專案行為準則(給 AI 助手用)
└── export_conversation.py       對話備份工具
```

---

## 目前進度

| 項目 | 狀態 |
|---|---|
| Cellpose fine-tune cpsam 模型 | ✅ 完成(1024×768 圖,準確度 24% → 97%)|
| L-shape 計數規則(身體碰邊版) | ✅ 完成 |
| 上下室 + 濃度公式批次處理 | ✅ 完成(step6/7)|
| 手機 app:相機畫面 + 鎖定設定 | 🟡 開發中 |
| 手機 app:RGB 顏色提取 + 濃度迴歸 | ⏳ 待做 |
| 手機 app:葉綠素濃度估計 | ⏳ 待做 |

---

## 主要技術

- **影像分割**: [Cellpose 4.x](https://github.com/MouseLand/cellpose)(SAM-based cpsam,fine-tuned)
- **訓練**: PyTorch on Google Colab T4
- **計數規則**: 血球計數器 L-shape 規則(身體碰上+左 → 算入)
- **手機 app**: React Native + Expo + react-native-vision-camera
- **顏色 → 濃度**: Beer-Lambert 律 + RGB 通道(R≈660nm 葉綠素 a 紅光峰)

---

## 致謝

本專案受 [Algaeorithm](https://github.com/rohanchanani/Algaeorithm) 啟發 — 一個由高中生開發、獲 AlgaePrize 與 DOE 補助的藻類分析網站。
原專案的細胞濃度公式、成長曲線回歸等概念有參考(詳見 [參考資料/02_原專案有用的演算法.md](參考資料/02_原專案有用的演算法.md))。
