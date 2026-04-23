# CellPose Fine-tune 完整流程

目標：用你自己的 20-30 張圖，把預訓練 cpsam 的準確率從 **88% 提升到 95%+**。

## 三步驟總覽

```
Step 1：標注圖片（在本機電腦用 CellPose GUI）
        ↓  需要 1-2 小時
Step 2：上傳標注 + 原圖到 Google Drive
        ↓
Step 3：Colab 上跑 fine-tune 腳本
        ↓  Colab T4 GPU 約 20-40 分鐘
測試新模型：用 inference.py 驗證效果
```

---

## 📋 預計總時間

| 階段 | 時間 |
|------|------|
| Step 1 標注 | 1-2 小時（可分批做） |
| Step 2 上傳 | 5-10 分鐘 |
| Step 3 訓練 | 20-40 分鐘（你只要等） |
| 測試 | 10 分鐘 |
| **總計** | **2-3 小時** |

---

## 📁 檔案說明

| 檔案 | 用途 |
|------|------|
| `README.md` | 本檔（總覽） |
| `step1_labeling_guide.md` | **Step 1 標注教學**（先看這個） |
| `step2_upload_guide.md` | Step 2 怎麼把檔案上傳到 Drive |
| `step3_finetune.py` | **Step 3 Colab 訓練腳本** |
| `step4_inference.py` | 用訓練好的模型做偵測 |

**建議順序：** 先讀 `step1_labeling_guide.md` → 動手標注 → 讀 step2 → 讀 step3 跑訓練。
