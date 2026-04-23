"""
CellPose 藻類細胞偵測 — Colab 版

使用方式：
  1. 在 Colab 新建筆記本
  2. 第一個 Cell 貼：!pip install cellpose --quiet
  3. 第二個 Cell 貼：整個本檔案的內容
  4. 執行（第一次會下載 1.15 GB 模型約 30 秒）

硬體：需要 GPU（Colab 免費版 T4 即可）
"""

# ============================================================
#  載入套件
# ============================================================
import os
import glob
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import torch
from cellpose import models, io, plot
from google.colab import drive


# ============================================================
#  設定區（可自由調整）
# ============================================================
# 要處理的圖片（單張）
IMAGE_PATH = '/content/drive/MyDrive/0102下/20260102144751.jpg'

# 模型選擇 — 可選 'cpsam'（預設，最強但會漏抓小細胞）或 'cyto3'（對小細胞較敏感）
MODEL_TYPE = 'cpsam'

# 細胞直徑（像素）— 自動估計常常偏大，手動指定能抓到更多小細胞
# None = 自動估計；或試 40, 45, 50（你的 Chlorella 看起來約 45 像素）
CELL_DIAMETER = 45

# 面積過濾 — 移除超大的 mask（格線殘影會超過 10000 像素²）
MAX_AREA = 10000
MIN_AREA = 100

# 邊緣裁切寬度（像素）— 消除血球計數板的格線干擾
# 設 0 完全不裁邊（可用來跟原本的偵測結果對比）
# 要消格線誤偵測時再調為 80-150
CROP_MARGIN = 0

# 偵測後，碰到邊界的 mask 會被丟掉（像素）— 安全網
# 設 0 則不過濾
BORDER_FILTER = 0

# 結果存檔位置
OUTPUT_PATH = '/content/drive/MyDrive/cellpose_result.jpg'


# ============================================================
#  1. 掛載 Google Drive + 檢查 GPU
# ============================================================
def setup():
    drive.mount('/content/drive')

    if torch.cuda.is_available():
        print(f"✅ GPU 可用: {torch.cuda.get_device_name(0)}")
    else:
        print("⚠️  沒有 GPU！Colab 設定 → 變更執行階段類型 → 硬體加速器選 T4 GPU")


# ============================================================
#  2. 載入模型（cpsam, v4 最強模型）
# ============================================================
def load_model():
    print(f"載入 {MODEL_TYPE} 模型（第一次約 30 秒下載權重）...")
    if MODEL_TYPE == 'cpsam':
        model = models.CellposeModel(gpu=True)
    else:
        model = models.CellposeModel(gpu=True, model_type=MODEL_TYPE)
    print("✅ 模型載入完成")
    return model


# ============================================================
#  3. 讀取並裁切圖片
# ============================================================
def load_and_crop(image_path, margin):
    img = io.imread(image_path)
    print(f"原始尺寸: {img.shape}")

    h, w = img.shape[:2]
    img_cropped = img[margin:h-margin, margin:w-margin]
    print(f"裁邊後: {img_cropped.shape}")

    return img, img_cropped


# ============================================================
#  4. 執行偵測
# ============================================================
def detect(model, img):
    print(f"🔄 偵測中（diameter={CELL_DIAMETER}）...")
    t0 = time.time()
    masks, flows, styles, *_ = model.eval(img, diameter=CELL_DIAMETER)
    elapsed = time.time() - t0
    print(f"⏱️  耗時 {elapsed:.1f} 秒，偵測到 {int(masks.max())} 顆（過濾前）")
    return masks


# ============================================================
#  4.5 按面積過濾 — 移除過大的 mask（格線）和過小的 mask（雜訊）
# ============================================================
def filter_by_area(masks, min_area, max_area):
    removed_big = 0
    removed_small = 0
    for mask_id in np.unique(masks):
        if mask_id == 0:
            continue
        area = (masks == mask_id).sum()
        if area > max_area:
            masks[masks == mask_id] = 0
            removed_big += 1
        elif area < min_area:
            masks[masks == mask_id] = 0
            removed_small += 1
    n = len(np.unique(masks)) - 1
    print(f"🗑️  移除過大 mask: {removed_big}，過小 mask: {removed_small}，剩 {n} 顆")
    return masks


# ============================================================
#  5. 過濾碰到邊界的 mask
# ============================================================
def filter_border_masks(masks, border):
    """移除碰到影像邊界的 mask（通常是格線或不完整細胞）。"""
    if border <= 0:
        n = len(np.unique(masks)) - 1
        print(f"🗑️  跳過邊界過濾，細胞數：{n} 顆")
        return masks

    h, w = masks.shape
    removed = 0

    for mask_id in np.unique(masks):
        if mask_id == 0:
            continue
        ys, xs = np.where(masks == mask_id)
        if len(ys) == 0:
            continue
        if (ys.min() < border or ys.max() > h - border or
            xs.min() < border or xs.max() > w - border):
            masks[masks == mask_id] = 0
            removed += 1

    n = len(np.unique(masks)) - 1
    print(f"🗑️  移除碰邊界 mask: {removed} 個，最終 {n} 顆")
    return masks


# ============================================================
#  6. 視覺化（4 種視圖）
# ============================================================
def visualize(img, masks, output_path):
    n = len(np.unique(masks)) - 1
    fig, axes = plt.subplots(2, 2, figsize=(18, 14))

    axes[0, 0].imshow(img)
    axes[0, 0].set_title("1. Original", fontsize=14)
    axes[0, 0].axis('off')

    outlines = plot.outline_view(img, masks)
    axes[0, 1].imshow(outlines)
    axes[0, 1].set_title(f"2. Outlines ({n} cells)", fontsize=14)
    axes[0, 1].axis('off')

    axes[1, 0].imshow(masks, cmap='nipy_spectral')
    axes[1, 0].set_title("3. Colored masks", fontsize=14)
    axes[1, 0].axis('off')

    overlay = plot.mask_overlay(img, masks)
    axes[1, 1].imshow(overlay)
    axes[1, 1].set_title("4. Mask overlay", fontsize=14)
    axes[1, 1].axis('off')

    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches='tight')
    plt.show()
    print(f"✅ 結果已存到 {output_path}")


# ============================================================
#  7. 統計細胞面積分布
# ============================================================
def show_statistics(masks):
    unique_ids = np.unique(masks)
    unique_ids = unique_ids[unique_ids != 0]
    areas = np.array([(masks == i).sum() for i in unique_ids])

    print("\n=== 細胞統計 ===")
    print(f"細胞數：{len(areas)}")
    print(f"平均面積：{areas.mean():.1f} 像素²")
    print(f"中位數：{np.median(areas):.1f} 像素²")
    print(f"最小 / 最大：{areas.min()} / {areas.max()}")

    plt.figure(figsize=(10, 5))
    plt.hist(areas, bins=30, edgecolor='black')
    plt.xlabel('Area (pixels^2)')
    plt.ylabel('Cell count')
    plt.title('Cell area distribution')
    plt.grid(alpha=0.3)
    plt.show()


# ============================================================
#  8. 批次處理整個資料夾（可選）
# ============================================================
def batch_process(model, folder, output_csv):
    """跑一整個資料夾，輸出 CSV 統計。"""
    image_files = sorted(glob.glob(os.path.join(folder, '*.jpg')))
    print(f"找到 {len(image_files)} 張圖片")

    results = []
    for i, path in enumerate(image_files, 1):
        fname = os.path.basename(path)
        print(f"\n[{i}/{len(image_files)}] {fname}")

        _, img_c = load_and_crop(path, CROP_MARGIN)
        masks = detect(model, img_c)
        masks = filter_by_area(masks, MIN_AREA, MAX_AREA)
        masks = filter_border_masks(masks, BORDER_FILTER)

        count = len(np.unique(masks)) - 1
        results.append({'file': fname, 'count': count})

    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False)
    print(f"\n✅ 統計結果存到 {output_csv}")
    print(df)
    return df


# ============================================================
#  主程式：單張圖完整流程
# ============================================================
if __name__ == '__main__':
    # 準備環境
    setup()
    model = load_model()

    # 處理單張圖
    img_original, img_cropped = load_and_crop(IMAGE_PATH, CROP_MARGIN)
    masks = detect(model, img_cropped)
    masks = filter_by_area(masks, MIN_AREA, MAX_AREA)
    masks = filter_border_masks(masks, BORDER_FILTER)

    # 顯示結果
    visualize(img_cropped, masks, OUTPUT_PATH)
    show_statistics(masks)

    # ----------------------------------------
    # 要批次處理整個資料夾的話，取消下面註解：
    # ----------------------------------------
    # IMAGE_FOLDER = '/content/drive/MyDrive/0102下/'
    # OUTPUT_CSV = '/content/drive/MyDrive/cell_counts.csv'
    # batch_process(model, IMAGE_FOLDER, OUTPUT_CSV)
