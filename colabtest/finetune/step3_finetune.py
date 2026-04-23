"""
Step 3：Fine-tune cpsam 模型 — 在 Colab 上跑

使用方式：
  1. Colab 新建筆記本，確認啟用 T4 GPU
  2. 第一個 cell：  !pip install cellpose --quiet
  3. 第二個 cell：  貼整個本檔案內容，執行

預估時間：
  - 20 張圖，100 epoch：約 20-30 分鐘
  - 30 張圖，100 epoch：約 30-45 分鐘

檔案需求：
  /content/drive/MyDrive/cellpose_train/
    ├── train/  (至少 20 組 jpg + _seg.npy)
    └── test/   (5 組，用來驗證)
"""

# ============================================================
#  載入套件 + 掛載 Drive
# ============================================================
import os
import glob
import time
import numpy as np
import matplotlib.pyplot as plt

import torch
from cellpose import models, io, train, plot
from google.colab import drive

drive.mount('/content/drive')

if torch.cuda.is_available():
    print(f"[OK] GPU: {torch.cuda.get_device_name(0)}")
else:
    print("[WARN] No GPU detected! Go to Runtime → Change runtime type → T4 GPU")
    raise SystemExit


# ============================================================
#  設定區
# ============================================================
TRAIN_DIR = '/content/drive/MyDrive/cellpose_train/train'
TEST_DIR = '/content/drive/MyDrive/cellpose_train/test'

# 輸出的模型存哪（訓練後可以帶走）
MODEL_SAVE_PATH = '/content/drive/MyDrive/cellpose_train/my_cpsam_model'

# 訓練參數
N_EPOCHS = 100          # 訓練輪數，100 夠了；太多會 overfit
LEARNING_RATE = 1e-5    # cpsam 建議的低學習率（從預訓練開始微調）
WEIGHT_DECAY = 0.1      # 正則化，避免 overfit
BATCH_SIZE = 1          # T4 記憶體限制，cpsam 大模型只能 batch=1


# ============================================================
#  1. 載入訓練資料
# ============================================================
def load_training_data(data_dir):
    """讀取資料夾裡的 jpg 和 _seg.npy，配對起來。"""
    images = []
    masks = []

    jpgs = sorted(glob.glob(os.path.join(data_dir, '*.jpg')))

    for jpg_path in jpgs:
        seg_path = jpg_path.replace('.jpg', '_seg.npy')
        if not os.path.exists(seg_path):
            print(f"[SKIP] 找不到 {os.path.basename(seg_path)}")
            continue

        img = io.imread(jpg_path)
        seg_data = np.load(seg_path, allow_pickle=True).item()
        mask = seg_data['masks']

        images.append(img)
        masks.append(mask)

    print(f"載入 {len(images)} 對訓練資料")
    return images, masks


print("\n==== 載入訓練資料 ====")
train_images, train_masks = load_training_data(TRAIN_DIR)

print("\n==== 載入測試資料 ====")
test_images, test_masks = load_training_data(TEST_DIR)

if len(train_images) < 10:
    print(f"[WARN] 只有 {len(train_images)} 張訓練圖，建議至少 15-20 張！")


# ============================================================
#  2. 載入預訓練 cpsam 作為起點
# ============================================================
print("\n==== 載入預訓練 cpsam ====")
model = models.CellposeModel(gpu=True)
print("[OK] 預訓練模型載入完成")


# ============================================================
#  3. 執行 fine-tune
# ============================================================
print(f"\n==== 開始 fine-tune（{N_EPOCHS} epochs）====")
t0 = time.time()

# CellPose 4.x 訓練 API
new_model_path = train.train_seg(
    net=model.net,
    train_data=train_images,
    train_labels=train_masks,
    test_data=test_images,
    test_labels=test_masks,
    batch_size=BATCH_SIZE,
    n_epochs=N_EPOCHS,
    learning_rate=LEARNING_RATE,
    weight_decay=WEIGHT_DECAY,
    save_path='/content/drive/MyDrive/cellpose_train/',
    model_name='my_cpsam_model',
)

elapsed = time.time() - t0
print(f"\n[OK] 訓練完成！耗時 {elapsed/60:.1f} 分鐘")
print(f"模型存到: {new_model_path}")


# ============================================================
#  4. 測試 fine-tune 前後的效果差異
# ============================================================
print("\n==== 對比測試 ====")

def count_cells(model, img):
    """用模型做偵測，回傳細胞數。"""
    masks, *_ = model.eval(img, diameter=45)
    return len(np.unique(masks)) - 1, masks


# 載入新訓練的模型
new_model = models.CellposeModel(gpu=True, pretrained_model=str(new_model_path))

# 原始 cpsam
old_model = models.CellposeModel(gpu=True)

print(f"{'圖片':<30} {'原始 cpsam':>12} {'Fine-tuned':>12} {'真實':>8}")
print("-" * 70)

for i, (img, true_mask) in enumerate(zip(test_images, test_masks)):
    true_count = len(np.unique(true_mask)) - 1
    old_count, _ = count_cells(old_model, img)
    new_count, _ = count_cells(new_model, img)

    print(f"test_{i+1:<25} {old_count:>12} {new_count:>12} {true_count:>8}")


# ============================================================
#  5. 視覺化：看一張 test 圖的結果差異
# ============================================================
if len(test_images) > 0:
    img = test_images[0]
    true_mask = test_masks[0]
    _, old_mask = count_cells(old_model, img)
    _, new_mask = count_cells(new_model, img)

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    axes[0, 0].imshow(img)
    axes[0, 0].set_title("Original", fontsize=14)
    axes[0, 0].axis('off')

    axes[0, 1].imshow(plot.mask_overlay(img, true_mask))
    axes[0, 1].set_title(f"Ground Truth ({len(np.unique(true_mask))-1} cells)", fontsize=14)
    axes[0, 1].axis('off')

    axes[1, 0].imshow(plot.mask_overlay(img, old_mask))
    axes[1, 0].set_title(f"Original cpsam ({len(np.unique(old_mask))-1} cells)", fontsize=14)
    axes[1, 0].axis('off')

    axes[1, 1].imshow(plot.mask_overlay(img, new_mask))
    axes[1, 1].set_title(f"Fine-tuned ({len(np.unique(new_mask))-1} cells)", fontsize=14)
    axes[1, 1].axis('off')

    plt.tight_layout()
    plt.savefig('/content/drive/MyDrive/cellpose_train/comparison.jpg', dpi=120, bbox_inches='tight')
    plt.show()

print("\n" + "=" * 70)
print(" 訓練完成！")
print(f" 新模型: {new_model_path}")
print(" 下一步：用 step4_inference.py 拿新模型跑批次偵測")
print("=" * 70)
