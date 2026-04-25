"""
Colab 批次自動標注腳本

用途：
    用 Colab 的 T4 GPU 跑 cpsam，幫所有圖產生 _seg.npy 標注檔。
    下載回本機後，本機 GUI 只需要「修正」AI 錯誤，不用每張重跑模型。

每次執行會把結果存在獨立子資料夾 auto_label_d{D}_f{F}_c{C}/ 裡，
不會覆蓋之前的結果。可以多跑幾組參數比較。

使用步驟：
    1. Google Drive 建資料夾 MyDrive/labeling/，把所有 jpg 丟進去
    2. Colab 開新 notebook，設定 T4 GPU
       (Runtime → Change runtime type → T4 GPU)
    3. 貼這份程式碼整段，執行
    4. 跑完去 Drive 對應的子資料夾下載 jpg + _seg.npy 回本機
"""

# ============================================================
#  設定區
# ============================================================
DRIVE_FOLDER = '/content/drive/MyDrive/labeling'

# 模型參數（改這些來嘗試不同效果）
DIAMETER = 12             # 細胞直徑(像素)— 1024x768 圖約 12，4K 原圖約 45
FLOW_THRESHOLD = 0.4      # 流場閾值，越低越嚴格(預設 0.4)
CELLPROB_THRESHOLD = 0.0  # 細胞機率閾值，越低抓越多(預設 0.0，可試 -2 ~ 2)

# ============================================================
#  1. 安裝 + 掛載 Drive + 檢查 GPU
# ============================================================
!pip install cellpose --quiet

from google.colab import drive
import torch
import os
import glob
import time
import shutil
import numpy as np

drive.mount('/content/drive')

if torch.cuda.is_available():
    print(f"[OK] GPU: {torch.cuda.get_device_name(0)}")
else:
    print("[WARN] 沒有 GPU！Runtime → Change runtime type → T4 GPU")

# ============================================================
#  2. 建立輸出子資料夾(名稱含參數)
# ============================================================
out_name = f"auto_label_d{DIAMETER}_f{FLOW_THRESHOLD}_c{CELLPROB_THRESHOLD}"
OUTPUT_FOLDER = os.path.join(DRIVE_FOLDER, out_name)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
print(f"輸出資料夾: {OUTPUT_FOLDER}")

# ============================================================
#  3. 載入 cpsam 模型
# ============================================================
from cellpose import models, io

print("載入 cpsam 模型...")
model = models.CellposeModel(gpu=True)
print("[OK] 模型載入完成")

# ============================================================
#  4. 找出所有要處理的圖（只看主資料夾，不遞迴進子資料夾）
# ============================================================
jpg_files = sorted(glob.glob(os.path.join(DRIVE_FOLDER, '*.jpg')))
jpg_files += sorted(glob.glob(os.path.join(DRIVE_FOLDER, '*.png')))
print(f"找到 {len(jpg_files)} 張圖")

if len(jpg_files) == 0:
    raise SystemExit(f"資料夾沒有圖：{DRIVE_FOLDER}")

# ============================================================
#  5. 批次自動標注
# ============================================================
results = []
total_start = time.time()

for i, img_path in enumerate(jpg_files, 1):
    name = os.path.basename(img_path)
    print(f"\n[{i}/{len(jpg_files)}] {name}")

    img = io.imread(img_path)
    print(f"  尺寸: {img.shape}")

    t0 = time.time()
    masks, flows, styles = model.eval(
        img,
        diameter=DIAMETER,
        flow_threshold=FLOW_THRESHOLD,
        cellprob_threshold=CELLPROB_THRESHOLD,
    )
    elapsed = time.time() - t0

    n_cells = int(masks.max())
    print(f"  偵測到 {n_cells} 顆，耗時 {elapsed:.1f} 秒")

    # 把原圖複製到輸出資料夾(讓 GUI 開那邊就能直接用)
    img_dst = os.path.join(OUTPUT_FOLDER, name)
    if not os.path.exists(img_dst):
        shutil.copy2(img_path, img_dst)

    # 存成 _seg.npy(GUI 相容格式)，放在輸出資料夾
    base = os.path.splitext(name)[0]
    save_path = os.path.join(OUTPUT_FOLDER, base + '_seg.npy')

    seg_dict = {
        'masks': masks,
        'outlines': np.zeros_like(masks),
        'colors': np.random.randint(0, 255, (n_cells, 3)),
        'img': img,
        'filename': img_dst,
        'flows': flows,
        'chan_choose': [0, 0],
        'ismanual': np.zeros(n_cells, dtype=bool),
        'diameter': DIAMETER,
    }
    np.save(save_path, seg_dict)
    print(f"  存到 {save_path}")

    results.append({'name': name, 'cells': n_cells, 'time_s': elapsed})

# ============================================================
#  6. 寫入參數紀錄(方便日後對照)
# ============================================================
with open(os.path.join(OUTPUT_FOLDER, 'params.txt'), 'w', encoding='utf-8') as f:
    f.write(f"diameter={DIAMETER}\n")
    f.write(f"flow_threshold={FLOW_THRESHOLD}\n")
    f.write(f"cellprob_threshold={CELLPROB_THRESHOLD}\n")
    f.write(f"\n=== 各圖細胞數 ===\n")
    for r in results:
        f.write(f"{r['name']:30s}  {r['cells']:4d} 顆\n")

# ============================================================
#  7. 總結
# ============================================================
total = time.time() - total_start
print(f"\n========== 完成 ==========")
print(f"總共 {len(jpg_files)} 張，耗時 {total:.1f} 秒")
print(f"\n各圖細胞數：")
for r in results:
    print(f"  {r['name']:30s}  {r['cells']:4d} 顆  ({r['time_s']:.1f}s)")

print(f"\n結果存在: {OUTPUT_FOLDER}")
print(f"下一步：去 Drive 下載整個 {out_name}/ 資料夾，本機開 GUI 載入該資料夾的圖")
