# Step 2：上傳標注資料到 Google Drive

標注完之後，把原圖和 `_seg.npy` 檔案一起傳到 Drive，讓 Colab 能存取。

---

## 資料夾結構建議

在 Google Drive 建立新資料夾 `cellpose_train/`：

```
Google Drive/
└── cellpose_train/
    ├── train/              ← 20-25 張用來訓練
    │   ├── 20260102144751.jpg
    │   ├── 20260102144751_seg.npy
    │   ├── 20260102144820.jpg
    │   ├── 20260102144820_seg.npy
    │   └── ...
    │
    └── test/               ← 留 5 張不訓練，用來驗證效果
        ├── 20260102151444.jpg
        ├── 20260102151444_seg.npy
        └── ...
```

**重點：** 每張 `.jpg` 都要有對應的 `_seg.npy` 檔案，**名字要配對**。

---

## 為什麼要分 train / test？

訓練時模型會「看過」train 的圖，所以在 train 上測試不公平。
要用**模型沒看過的 test 圖**來驗證效果，才知道真實準確率。

---

## 上傳方式

### 方法 A：網頁拖拉（最簡單）
1. 開啟 https://drive.google.com
2. 建立資料夾 `cellpose_train` → 裡面再建 `train` 和 `test`
3. 把標注好的檔案**拖拉進對應資料夾**

### 方法 B：Google Drive 同步（推薦給大量檔案）
1. 本機安裝 Google Drive 桌面版
2. 登入你的帳號
3. 檔案直接拉到同步資料夾
4. 自動上傳

### 方法 C：壓縮上傳（最快）
1. 把訓練用的圖和 `_seg.npy` 打包成 zip
2. 上傳 zip 到 Drive
3. 在 Colab 解壓：
   ```python
   !unzip /content/drive/MyDrive/cellpose_train.zip -d /content/
   ```

---

## 確認上傳完成

在 Colab 第一格執行：

```python
from google.colab import drive
drive.mount('/content/drive')

import os
train_dir = '/content/drive/MyDrive/cellpose_train/train'
files = os.listdir(train_dir)
jpgs = [f for f in files if f.endswith('.jpg')]
seg = [f for f in files if f.endswith('_seg.npy')]
print(f"訓練圖片: {len(jpgs)} 張")
print(f"標注檔: {len(seg)} 個")
assert len(jpgs) == len(seg), "圖片跟標注數量對不上！"
```

數字要**相等**才對。

---

**下一步：** 開啟 `step3_finetune.py`，跟著裡面的指示在 Colab 跑。
