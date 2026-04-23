# CellPose 藻類細胞偵測 - 可攜帶版

這個資料夾包含執行 CellPose 藻類細胞偵測所需的一切。
可以放到隨身碟帶到任何 Windows 電腦使用。

---

## 資料夾內容

```
cellpose_portable/
├── README.md              ← 本檔案（步驟說明）
├── setup.bat              ← 一鍵安裝環境（第一次才要跑）
├── run.bat                ← 一鍵執行偵測
├── cellpose_test.py       ← 主程式
├── requirements.txt       ← Python 套件清單
├── cellpose_model/
│   └── cpsam              ← 預訓練模型權重（1.15 GB，免再下載）
└── test_images/           ← 測試圖片
    ├── sample1.jpg
    ├── sample2.jpg
    └── sample3.jpg
```

---

## 在新電腦上使用的步驟

### 前置要求

- **Windows 10 或 11**
- **Python 3.11 以上** — 若未安裝，先去 https://www.python.org/downloads/ 下載
  - 安裝時**務必勾選** `Add Python to PATH`
- **網路**（第一次執行時需要下載 PyTorch 等套件，約 1-2 GB）

### 步驟 1：把整個資料夾從隨身碟複製到電腦

建議複製到 `D:\cellpose_portable\` 或任何路徑**都不包含中文**的地方。

> ⚠️ 路徑不要有中文字，OpenCV 在 Windows 上讀不到中文路徑的圖片。

### 步驟 2：執行 setup.bat（只要做一次）

雙擊 `setup.bat`，會自動：

1. 檢查 Python 是否已安裝
2. 建立虛擬環境 `venv`
3. 安裝 cellpose、matplotlib、pillow、opencv-python 等套件
4. 把 `cellpose_model/cpsam` 複製到 `%USERPROFILE%\.cellpose\models\cpsam`
   （這一步很重要，避免重新下載 1.15 GB 的模型）

過程約 5-15 分鐘（看網速），成功訊息為：

```
================================================
  安裝完成！
  執行 run.bat 來測試
================================================
```

### 步驟 3：執行 run.bat

- **用預設的測試圖**：直接雙擊 `run.bat`
  - 會跑 `test_images\sample1.jpg`
- **用自己的圖**：打開命令提示字元 → `cd` 到此資料夾 → 執行：
  ```
  run.bat "C:\完整路徑\到你的圖片.jpg"
  ```

### 執行時間（參考）

| 電腦 CPU | 1920×1080 圖（--scale 0.5） |
|---------|------------------------------|
| 一般筆電 CPU | 2-5 分鐘 |
| 比較舊的 CPU | 10-60 分鐘 |
| 有 NVIDIA 顯卡（GPU） | < 30 秒（但要另外裝 CUDA 版 PyTorch） |

### 結果

- 視窗會彈出顯示：左原圖、右偵測結果
- 終端機會印出：偵測到的細胞數量、耗時
- 結果圖會存成 `cellpose_result.jpg`

---

## 手動執行（進階用法）

如果不想用 `.bat` 檔：

```powershell
# 啟動虛擬環境
venv\Scripts\activate

# 跑偵測
python cellpose_test.py "test_images\sample1.jpg" --scale 0.5
```

### 可用參數

```
python cellpose_test.py <image_path>  [選項]

選項：
  --channel {gray,red,green,blue}   處理的顏色通道（預設 gray）
  --diameter N                      細胞直徑（像素），留空則自動估計
  --scale 0.5                       縮放比例，0.5 加速 4 倍（預設 1.0）
  --output result.jpg               輸出檔名
```

### 範例

```powershell
# 全尺寸（最精準但最慢）
python cellpose_test.py "my_image.jpg" --scale 1.0

# 加速到 0.25 倍（快 16 倍但會漏偵測）
python cellpose_test.py "my_image.jpg" --scale 0.25

# 指定細胞直徑 25 像素
python cellpose_test.py "my_image.jpg" --diameter 25
```

---

## 疑難排解

### Q1. `setup.bat` 跑到一半失敗

- 看錯誤訊息是哪個套件裝不起來
- 常見原因：Python 版本太舊（< 3.11）或網路不穩

### Q2. `python: can't open file 'cellpose_test.py'`

路徑問題。請確認命令提示字元已經 `cd` 到 `cellpose_portable` 資料夾內。

### Q3. `ModuleNotFoundError: No module named 'cellpose'`

沒啟動 venv。執行時命令提示字元前面要有 `(venv)` 字樣。

### Q4. OpenCV 讀不到圖片（路徑亂碼錯誤）

圖片路徑含有中文字元。把圖片複製到純英文路徑下再跑。

### Q5. 跑得超慢

是 CPU 的關係。CellPose 4.x 的 cpsam 模型基於 SAM（Segment Anything），CPU 本來就慢。
可以試：
- `--scale 0.25` 快 4 倍
- 用有 NVIDIA 顯卡的電腦，改裝 GPU 版 PyTorch（`pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121`）

### Q6. 偵測結果不夠準

目前用的是 CellPose 的通用預訓練模型，沒有針對你的藻類圖片微調。
改善方法：用 CellPose 內建的 GUI 標注 30-50 張你自己的圖，然後 fine-tune。
```
pip install cellpose[gui]
cellpose
```

---

## 製作時間

此可攜帶版建立於 2026-04-23。
CellPose 版本：4.1.1
Python 版本需求：3.11+
