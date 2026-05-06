"""
Step 3b: 用現有 my_cpsam_A 模型跑 IoU + Accuracy 評估(不重新訓練)

跟 step3 的差別:
  - step3 → 從零開始 fine-tune,要 30 分鐘
  - step3b → 載入已訓練的模型,只跑評估,約 1-3 分鐘

適用情境:已經跑過 step3、模型已經在 Drive,只想拿到 IoU / Accuracy 數字填報告 / 海報。

使用方式:
  Colab 開新筆記本,貼整份進一個 cell 跑完即可。
  輸出最後 2 行就是海報「性能評估」區塊要填的數字。
"""
# ============================================================
#  ⚙️ 設定區
# ============================================================
TEST_DIR   = '/content/drive/MyDrive/cellpose_train_A/test'
MODEL_PATH = '/content/drive/MyDrive/cellpose_train_A/models/my_cpsam_A'
DIAMETER   = 45              # 跟 step3 訓練時一致
IOU_THRESH = 0.5             # IoU ≥ 0.5 才算 True Positive(常見標準)


# ============================================================
#  安裝 + 載入
# ============================================================
!pip install cellpose --quiet

import os, glob
import numpy as np
import torch
from cellpose import models, io
from google.colab import drive

drive.mount('/content/drive', force_remount=True)
if not torch.cuda.is_available():
    raise SystemExit("[ERROR] 沒有 GPU,Runtime → Change runtime type → T4 GPU")
print(f"[OK] GPU: {torch.cuda.get_device_name(0)}")


# ============================================================
#  載入 test 資料
# ============================================================
def load_pairs(d):
    images, masks = [], []
    for jpg in sorted(glob.glob(os.path.join(d, '*.jpg'))):
        seg = jpg.replace('.jpg', '_seg.npy')
        if not os.path.exists(seg):
            continue
        images.append(io.imread(jpg))
        masks.append(np.load(seg, allow_pickle=True).item()['masks'])
    return images, masks

test_images, test_masks = load_pairs(TEST_DIR)
if not test_images:
    raise SystemExit(
        f"[ERROR] {TEST_DIR} 找不到 .jpg + _seg.npy 對\n"
        f"  → 確認 Drive 已掛載,以及資料夾名稱(若不是 _A,改最上面的 TEST_DIR)")
print(f"[OK] 載入 {len(test_images)} 張 test 影像")


# ============================================================
#  載入兩個模型(原始 cpsam vs fine-tuned)
# ============================================================
print("\n載入原始 cpsam...")
old_model = models.CellposeModel(gpu=True)

print(f"載入 fine-tuned: {MODEL_PATH}")
new_model = models.CellposeModel(gpu=True)
state = torch.load(MODEL_PATH, map_location='cuda', weights_only=False)
new_model.net.load_state_dict(state)
print("[OK] 模型都載好了")


# ============================================================
#  IoU + Accuracy 評估工具
# ============================================================
def compute_iou_matrix(pred, gt):
    """逐顆 mask × mask 算 IoU,回傳 (n_gt × n_pred) 矩陣。"""
    pred_ids = np.unique(pred); pred_ids = pred_ids[pred_ids > 0]
    gt_ids   = np.unique(gt);   gt_ids   = gt_ids[gt_ids > 0]
    n_gt, n_pred = len(gt_ids), len(pred_ids)
    if n_gt == 0 or n_pred == 0:
        return np.zeros((n_gt, n_pred))

    max_pred = int(pred_ids.max())
    overlap = (gt > 0) & (pred > 0)
    enc = gt[overlap].astype(np.int64) * (max_pred + 1) + pred[overlap].astype(np.int64)
    pair_counts = np.bincount(enc)
    gt_area   = np.bincount(gt.flatten().astype(np.int64))
    pred_area = np.bincount(pred.flatten().astype(np.int64))

    iou = np.zeros((n_gt, n_pred))
    for i, g in enumerate(gt_ids):
        for j, p in enumerate(pred_ids):
            key = int(g) * (max_pred + 1) + int(p)
            inter = pair_counts[key] if key < len(pair_counts) else 0
            union = gt_area[g] + pred_area[p] - inter
            iou[i, j] = inter / union if union > 0 else 0
    return iou


def evaluate(pred, gt, thresh=IOU_THRESH):
    """Greedy 配對,IoU≥thresh 算 TP。回傳 (mean_iou, accuracy, tp, fp, fn)。"""
    iou_mat = compute_iou_matrix(pred, gt)
    n_gt, n_pred = iou_mat.shape
    if n_gt == 0:
        return 0.0, 0.0, 0, n_pred, 0
    if n_pred == 0:
        return 0.0, 0.0, 0, 0, n_gt

    pairs = sorted(
        [(i, j, iou_mat[i, j]) for i in range(n_gt) for j in range(n_pred)],
        key=lambda x: -x[2])
    used_g, used_p, matched = set(), set(), []
    for i, j, v in pairs:
        if v < thresh: break
        if i in used_g or j in used_p: continue
        used_g.add(i); used_p.add(j); matched.append(v)

    tp = len(matched); fp = n_pred - tp; fn = n_gt - tp
    mean_iou = float(np.mean(matched)) if matched else 0.0
    accuracy = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0
    return mean_iou, accuracy, tp, fp, fn


# ============================================================
#  跑評估
# ============================================================
print(f"\n{'圖片':<14} {'cpsam (count/IoU/Acc)':>30} {'fine-tuned (count/IoU/Acc)':>32} {'GT':>5}")
print("-" * 90)

old_ious, new_ious = [], []
old_accs, new_accs = [], []
old_counts, new_counts, true_counts = [], [], []

for i, (img, gt) in enumerate(zip(test_images, test_masks)):
    true_count = len(np.unique(gt)) - 1
    old_pred, *_ = old_model.eval(img, diameter=DIAMETER)
    new_pred, *_ = new_model.eval(img, diameter=DIAMETER)
    old_count = len(np.unique(old_pred)) - 1
    new_count = len(np.unique(new_pred)) - 1

    o_iou, o_acc, *_ = evaluate(old_pred, gt)
    n_iou, n_acc, *_ = evaluate(new_pred, gt)

    old_ious.append(o_iou); old_accs.append(o_acc); old_counts.append(old_count)
    new_ious.append(n_iou); new_accs.append(n_acc); new_counts.append(new_count)
    true_counts.append(true_count)

    print(f"test_{i+1:<9}  {old_count:>5} / {o_iou:.3f} / {o_acc:.3f}      "
          f"{new_count:>5} / {n_iou:.3f} / {n_acc:.3f}      {true_count:>4}")

print("-" * 90)
old_mae = float(np.mean(np.abs(np.array(old_counts) - np.array(true_counts))))
new_mae = float(np.mean(np.abs(np.array(new_counts) - np.array(true_counts))))

print(f"\n{'=' * 70}")
print("  📊 平均統計(填海報「性能評估」用)")
print(f"{'=' * 70}")
print(f"  原始 cpsam    →  mean IoU = {np.mean(old_ious):.3f}")
print(f"                   Accuracy = {np.mean(old_accs):.3f}")
print(f"                   Count MAE = {old_mae:.2f}")
print(f"")
print(f"  Fine-tuned    →  mean IoU = {np.mean(new_ious):.3f}")
print(f"                   Accuracy = {np.mean(new_accs):.3f}")
print(f"                   Count MAE = {new_mae:.2f}")
print(f"{'=' * 70}")
