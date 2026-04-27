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
| `auto_label_colab.py` | Colab 批次自動標注（本機 GUI 之前先跑這個省時間）|
| `split_train_test.py` | 把標好的 labeling_X/ 分成 train/test 並打包成 zip |
| `step3_finetune.py` | **Step 3 Colab 訓練腳本** |
| `step4_inference.py` | Step 4 用訓練好的模型做偵測（只算全部數）|
| `count_lshape.py` | L-shape 規則計數核心模組（單張）|
| `batch_lshape.py` | 本機批次:對已有 jpg + _seg.npy 的資料夾跑 L-shape |
| `step5_lshape_inference.py` | **Step 5 Colab 一條龍**:cellpose + L-shape 規則 + CSV |
| `step6_chamber_inference.py` | **Step 6 上下室完整計算**:up/down 子資料夾 + 濃度公式 + 平均/總計(高解析度圖會等比放大參數)|
| `step7_chamber_inference_downsample.py` | **Step 7**:同 step6,但**先把高解析度圖縮小到 1024 寬**再分析(對 4K 圖更貼近訓練條件)|

## 標注規則對應

| 資料夾 | 規則 |
|---|---|
| `labeling_A/` | 連在一起算 1 顆（整個分裂雙球當 1 個 mask）|
| `labeling_B/` | 明顯兩球算 2 顆（分裂雙球各當 1 個 mask）|

**建議順序：** 先讀 `step1_labeling_guide.md` → 動手標注 → 讀 step2 → 讀 step3 跑訓練。
