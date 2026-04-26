"""
Step 4：用 fine-tuned 模型做批次偵測

這個腳本用你訓練好的模型（而不是原始 cpsam）跑所有圖，
輸出每張圖的細胞數到 CSV。

使用方式：在 Colab 裡貼這整個檔案執行
"""

import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import torch
from cellpose import models, io, plot
from google.colab import drive

drive.mount('/content/drive')


# ============================================================
#  設定
# ============================================================
# 訓練好的模型路徑（step3 訓練完會印出來）
MODEL_PATH = '/content/drive/MyDrive/cellpose_train_A/models/my_cpsam_A'

# 要處理的圖片資料夾
IMAGE_FOLDER = '/content/drive/MyDrive/labeling/'

# 結果輸出（CSV 跟結果圖放同一個資料夾）
OUTPUT_DIR = '/content/drive/MyDrive/cellpose_results_finetuned/'
OUTPUT_CSV = os.path.join(OUTPUT_DIR, 'cell_counts.csv')
OUTPUT_IMAGES_DIR = OUTPUT_DIR

# 偵測參數
CELL_DIAMETER = 45
MAX_AREA = 10000
MIN_AREA = 100


# ============================================================
#  載入 fine-tuned 模型
# ============================================================
# 注意：cpsam 不能用 pretrained_model=path 載入，會被默默忽略。
# 必須先建模型再用 load_state_dict 手動灌入訓練後的權重。
print(f"載入 fine-tuned 模型：{MODEL_PATH}")
model = models.CellposeModel(gpu=True)
state = torch.load(MODEL_PATH, map_location='cuda', weights_only=False)
model.net.load_state_dict(state)
print("[OK] 模型載入完成（手動 load_state_dict）")


# ============================================================
#  過濾函數（跟主腳本一樣）
# ============================================================
def filter_by_area(masks, min_area, max_area):
    for mask_id in np.unique(masks):
        if mask_id == 0:
            continue
        area = (masks == mask_id).sum()
        if area > max_area or area < min_area:
            masks[masks == mask_id] = 0
    return masks


# ============================================================
#  批次處理
# ============================================================
os.makedirs(OUTPUT_IMAGES_DIR, exist_ok=True)

image_files = sorted(glob.glob(os.path.join(IMAGE_FOLDER, '*.jpg')))
# 排除 _seg.npy 等中間檔
image_files = [f for f in image_files if '_seg' not in f and '_cp_' not in f]

print(f"\n找到 {len(image_files)} 張圖片")

results = []
for i, path in enumerate(image_files, 1):
    fname = os.path.basename(path)
    print(f"\n[{i}/{len(image_files)}] {fname}")

    img = io.imread(path)
    masks, *_ = model.eval(img, diameter=CELL_DIAMETER)
    masks = filter_by_area(masks, MIN_AREA, MAX_AREA)

    count = len(np.unique(masks)) - 1
    print(f"  → {count} 顆細胞")

    # 存視覺化結果
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))
    axes[0].imshow(img)
    axes[0].set_title(f"Original: {fname}", fontsize=14)
    axes[0].axis('off')

    overlay = plot.mask_overlay(img, masks)
    axes[1].imshow(overlay)
    axes[1].set_title(f"Detected: {count} cells", fontsize=14)
    axes[1].axis('off')

    plt.tight_layout()
    output_path = os.path.join(OUTPUT_IMAGES_DIR, fname.replace('.jpg', '_result.jpg'))
    plt.savefig(output_path, dpi=100, bbox_inches='tight')
    plt.close()

    results.append({'file': fname, 'count': count})


# ============================================================
#  輸出 CSV
# ============================================================
df = pd.DataFrame(results)
df.to_csv(OUTPUT_CSV, index=False)

print("\n" + "=" * 60)
print(f"[OK] 全部完成！")
print(f"統計表: {OUTPUT_CSV}")
print(f"結果圖: {OUTPUT_IMAGES_DIR}")
print(f"\n統計摘要：")
print(f"  圖片數: {len(df)}")
print(f"  平均細胞數: {df['count'].mean():.1f}")
print(f"  最少 / 最多: {df['count'].min()} / {df['count'].max()}")
print("=" * 60)
print(df)
