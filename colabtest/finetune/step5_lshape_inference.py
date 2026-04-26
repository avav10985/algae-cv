"""
Step 5: Fine-tuned 模型 + L-shape 規則 一條龍批次處理(Colab)

對 Drive 裡一個資料夾的所有圖:
  1. 用 fine-tuned cpsam 偵測細胞(全部數)
  2. 自動偵測血球計數器的 1mm² 方格
  3. 套用 L-shape 規則(身體碰上/右算,碰下/左不算)
  4. 輸出 CSV(全部數 + L-shape 數)+ 視覺化

使用方式:
  1. Colab 設 T4 GPU
  2. 把這整份內容貼進 cell 跑
  3. 結果在 Drive 的 OUTPUT_DIR 裡
"""
# ============================================================
#  設定
# ============================================================
MODEL_PATH = '/content/drive/MyDrive/cellpose_train_A/models/my_cpsam_A'
IMAGE_FOLDER = '/content/drive/MyDrive/labeling/'   # ← 改成你要分析的資料夾
OUTPUT_DIR = '/content/drive/MyDrive/cellpose_results_lshape/'

# Cellpose 參數
CELL_DIAMETER = 45

# L-shape 計數方格參數(從 39_23 範例量出)
SQUARE_SIZE_PX = 640    # 1mm² 在這個放大率下的像素邊長
SQUARE_SIZE_TOL = 30    # 容忍誤差


# ============================================================
#  安裝 + 載入
# ============================================================
!pip install cellpose --quiet

import os, glob, csv
import numpy as np
import cv2
from scipy.signal import find_peaks
from scipy.ndimage import uniform_filter1d
import matplotlib.pyplot as plt
import torch
from cellpose import models, io, plot
from google.colab import drive

drive.mount('/content/drive')

if not torch.cuda.is_available():
    raise SystemExit("[ERROR] 沒有 GPU,Runtime → Change runtime type → T4 GPU")

print(f"[OK] GPU: {torch.cuda.get_device_name(0)}")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
#  載入 fine-tuned 模型
# ============================================================
# cpsam 不能用 pretrained_model=path 載入,要手動 load_state_dict
print(f"載入 fine-tuned 模型...")
model = models.CellposeModel(gpu=True)
state = torch.load(MODEL_PATH, map_location='cuda', weights_only=False)
model.net.load_state_dict(state)
print("[OK] 模型載入完成")


# ============================================================
#  L-shape 規則用的工具函式
# ============================================================
def detect_grid_lines(img_gray, brightness_thresh=180, min_line_distance=20,
                     smooth_window=5, peak_height_sigma=1.0):
    _, binary = cv2.threshold(img_gray, brightness_thresh, 255, cv2.THRESH_BINARY)
    h_proj = binary.sum(axis=1).astype(float)
    v_proj = binary.sum(axis=0).astype(float)
    h_s = uniform_filter1d(h_proj, size=smooth_window)
    v_s = uniform_filter1d(v_proj, size=smooth_window)
    h_thresh = h_s.mean() + h_s.std() * peak_height_sigma
    v_thresh = v_s.mean() + v_s.std() * peak_height_sigma
    h_peaks, _ = find_peaks(h_s, height=h_thresh, distance=min_line_distance)
    v_peaks, _ = find_peaks(v_s, height=v_thresh, distance=min_line_distance)
    return h_peaks, v_peaks


def cluster_lines(peaks, gap_threshold=40):
    if len(peaks) == 0:
        return []
    clusters, cur = [], [peaks[0]]
    for p in peaks[1:]:
        if p - cur[-1] <= gap_threshold:
            cur.append(p)
        else:
            clusters.append(int(np.median(cur)))
            cur = [p]
    clusters.append(int(np.median(cur)))
    return clusters


def find_square_by_size(h_lines, v_lines, img_shape, target=640, tol=30):
    H, W = img_shape[:2]
    h_pairs = [(a, b) for i, a in enumerate(h_lines) for b in h_lines[i+1:]
               if abs((b - a) - target) <= tol]
    v_pairs = [(a, b) for i, a in enumerate(v_lines) for b in v_lines[i+1:]
               if abs((b - a) - target) <= tol]
    if not h_pairs or not v_pairs:
        return None
    cy, cx = H / 2, W / 2
    best_h = min(h_pairs, key=lambda p: abs((p[0] + p[1]) / 2 - cy))
    best_v = min(v_pairs, key=lambda p: abs((p[0] + p[1]) / 2 - cx))
    return (best_h[0], best_h[1], best_v[0], best_v[1])


def apply_lshape(masks, bounds):
    """身體碰邊規則:碰左/下 → 不算;否則(在框內或碰上/右)→ 算。"""
    top, bottom, left, right = bounds
    included, excluded, outside = [], [], []
    centroids = {}
    for mid in range(1, int(masks.max()) + 1):
        ys, xs = np.where(masks == mid)
        if len(ys) == 0:
            continue
        centroids[mid] = (float(ys.mean()), float(xs.mean()))
        in_box = ((ys >= top) & (ys <= bottom) & (xs >= left) & (xs <= right))
        if not in_box.any():
            outside.append(mid)
            continue
        touches_left = (xs == left).any() or ((xs < left) & (ys >= top) & (ys <= bottom)).any()
        touches_bottom = (ys == bottom).any() or ((ys > bottom) & (xs >= left) & (xs <= right)).any()
        if touches_left or touches_bottom:
            excluded.append(mid)
        else:
            included.append(mid)
    return included, excluded, outside, centroids


# ============================================================
#  視覺化
# ============================================================
def visualize(img, masks, bounds, included, excluded, outside, centroids, save_path):
    top, bottom, left, right = bounds
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))

    # 左:原圖 + cellpose 偵測
    axes[0].imshow(plot.mask_overlay(img, masks))
    axes[0].set_title(f"Cellpose Detection: {int(masks.max())} cells", fontsize=14)
    axes[0].axis('off')

    # 右:L-shape 規則結果
    axes[1].imshow(img)
    # 框:上(算)+ 右(算) = 綠;下(不算)+ 左(不算)= 紅虛線
    axes[1].plot([left, right], [top, top], 'lime', linewidth=4)
    axes[1].plot([right, right], [top, bottom], 'lime', linewidth=4)
    axes[1].plot([left, left], [top, bottom], 'red', linewidth=3, linestyle='--')
    axes[1].plot([left, right], [bottom, bottom], 'red', linewidth=3, linestyle='--')
    for mid in included:
        cy, cx = centroids[mid]
        axes[1].plot(cx, cy, 'o', color='lime', markersize=5,
                     markeredgecolor='black', markeredgewidth=0.5)
    for mid in excluded:
        cy, cx = centroids[mid]
        axes[1].plot(cx, cy, 'x', color='red', markersize=10, markeredgewidth=2)
    for mid in outside:
        cy, cx = centroids[mid]
        axes[1].plot(cx, cy, 'o', color='gray', markersize=3, alpha=0.4)
    axes[1].set_title(f"L-shape Count: {len(included)} (excluded {len(excluded)})", fontsize=14)
    axes[1].axis('off')

    plt.tight_layout()
    plt.savefig(save_path, dpi=80, bbox_inches='tight')
    plt.close(fig)


# ============================================================
#  批次處理
# ============================================================
jpgs = sorted(glob.glob(os.path.join(IMAGE_FOLDER, '*.jpg')))
jpgs += sorted(glob.glob(os.path.join(IMAGE_FOLDER, '*.png')))
jpgs = [j for j in jpgs if '_seg' not in j and '_cp_' not in j and '_lshape' not in j]
print(f"\n找到 {len(jpgs)} 張圖")

rows = []
for i, jpg in enumerate(jpgs, 1):
    name = os.path.basename(jpg)
    print(f"\n[{i}/{len(jpgs)}] {name}")

    img = io.imread(jpg)

    # cellpose 偵測
    masks, *_ = model.eval(img, diameter=CELL_DIAMETER)
    n_total = int(masks.max())

    # 偵測計數方格
    img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
    h_peaks, v_peaks = detect_grid_lines(img_gray)
    h_lines = cluster_lines(h_peaks)
    v_lines = cluster_lines(v_peaks)
    bounds = find_square_by_size(h_lines, v_lines, img.shape,
                                 target=SQUARE_SIZE_PX, tol=SQUARE_SIZE_TOL)

    if bounds is None:
        print(f"  [WARN] 找不到計數方格 — 只記錄全部數")
        rows.append({
            '檔名': name, '全部數': n_total, 'L-shape計數': '',
            '排除壓左下': '', '框外': '',
            '方框上': '', '方框下': '', '方框左': '', '方框右': '',
        })
        continue

    included, excluded, outside, centroids = apply_lshape(masks, bounds)
    n_in, n_ex, n_out = len(included), len(excluded), len(outside)
    print(f"  全部={n_total}  L-shape={n_in}  (排除 {n_ex},框外 {n_out})")

    # 視覺化
    out_jpg = os.path.join(OUTPUT_DIR, name.replace('.jpg', '_lshape.jpg').replace('.png', '_lshape.jpg'))
    visualize(img, masks, bounds, included, excluded, outside, centroids, out_jpg)

    rows.append({
        '檔名': name,
        '全部數': n_total,
        'L-shape計數': n_in,
        '排除壓左下': n_ex,
        '框外': n_out,
        '方框上': bounds[0], '方框下': bounds[1],
        '方框左': bounds[2], '方框右': bounds[3],
    })


# ============================================================
#  輸出 CSV + 摘要
# ============================================================
csv_path = os.path.join(OUTPUT_DIR, 'cell_counts.csv')
with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print(f"\n{'=' * 60}")
print(f"[OK] CSV: {csv_path}")
print(f"[OK] 視覺化: {OUTPUT_DIR}")
print(f"\n=== 統計摘要 ===")
print(f"  圖片數: {len(rows)}")
totals = [r['全部數'] for r in rows if isinstance(r['全部數'], int)]
lshapes = [r['L-shape計數'] for r in rows if isinstance(r['L-shape計數'], int)]
if totals:
    print(f"  全部數平均: {sum(totals)/len(totals):.1f}  (min={min(totals)}, max={max(totals)})")
if lshapes:
    print(f"  L-shape 平均: {sum(lshapes)/len(lshapes):.1f}  (min={min(lshapes)}, max={max(lshapes)})")
print(f"{'=' * 60}")
