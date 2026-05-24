"""
Step 10: 單室血球計數 — 一個資料夾裡直接放 25 張 jpg

跟 step6 差別:
  - step6:處理 up/ + down/ 兩個子資料夾(雙室)
  - step10:只處理 FOLDER/ 裡的所有 jpg(單室)— 25 張 = 10 μL

預設假設(同 step6 / step8):
  - 5×5 計數方格(中央 1mm² 大格)
  - 25 張覆蓋 10 μL(10⁻² mL),每張 = 0.4 μL = 4×10⁻⁴ mL
  - 最終濃度 (cells/mL) = 細胞總數 ÷ 總微升 × 1000 × 稀釋倍率
  - 稀釋倍率 = 1(沒稀釋)

使用方式:
  1. Drive 結構:
     FOLDER/
     ├── *.jpg       ← 25 張直接放這裡
  2. 修改下面 FOLDER 路徑
  3. Colab 設 T4 GPU,把整份貼進 cell 跑
  4. 輸出在 FOLDER/results/
"""
# ============================================================
#  ⚙️ 設定區(可調整)
# ============================================================
FOLDER     = '/content/drive/MyDrive/single_chamber_sample/'   # ← 25 張的母資料夾
MODEL_PATH = '/content/drive/MyDrive/cellpose_train_A/models/my_cpsam_A'

# 計數參數(會依圖片解析度自動縮放)
BASE_IMAGE_WIDTH = 1024    # 訓練/校正基準解析度寬度
CELL_DIAMETER_BASE = 45    # 細胞直徑 @ 基準解析度
SQUARE_SIZE_BASE = 640     # 1mm² 計數方格 @ 基準解析度
SQUARE_SIZE_TOL_FRAC = 0.05  # 方格尺寸容忍誤差(佔目標尺寸的比例,5%)

# 濃度公式(可調)
DILUTION_FACTOR = 1.0      # 稀釋倍率(沒稀釋=1;1:1 trypan blue=2)
IMAGES_PER_CHAMBER = 25    # 每室預期張數(用於體積計算)
VOLUME_PER_CHAMBER_ML = 1e-2  # 每室容積 = 10 microliter = 10⁻² mL
VOLUME_PER_IMAGE_ML = VOLUME_PER_CHAMBER_ML / IMAGES_PER_CHAMBER  # 每張圖計數體積 = 0.4 μL = 4×10⁻⁴ mL
# → 單張外推 cells/mL = L-shape計數 × DILUTION_FACTOR / VOLUME_PER_IMAGE_ML
# → 最終濃度 = total_cells / total_microliter × 1000 × DILUTION_FACTOR


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

drive.mount('/content/drive', force_remount=True)
if not torch.cuda.is_available():
    raise SystemExit("[ERROR] 沒有 GPU,Runtime → Change runtime type → T4 GPU")
print(f"[OK] GPU: {torch.cuda.get_device_name(0)}")

if not os.path.exists(FOLDER):
    raise SystemExit(f"[ERROR] 找不到資料夾: {FOLDER}\n  確認路徑正確,且 Drive 已同步")
print(f"[OK] {FOLDER} 內容: {sorted(os.listdir(FOLDER))}")


# ============================================================
#  載入 fine-tuned 模型
# ============================================================
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
    """身體碰邊規則:碰右/下 → 不算;否則 → 算。"""
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
        touches_right = (xs == right).any() or ((xs > right) & (ys >= top) & (ys <= bottom)).any()
        touches_bottom = (ys == bottom).any() or ((ys > bottom) & (xs >= left) & (xs <= right)).any()
        if touches_right or touches_bottom:
            excluded.append(mid)
        else:
            included.append(mid)
    return included, excluded, outside, centroids


def visualize(img, masks, bounds, included, excluded, outside, centroids, save_path):
    top, bottom, left, right = bounds
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))

    axes[0].imshow(plot.mask_overlay(img, masks))
    axes[0].set_title(f"Cellpose Detection: {int(masks.max())} cells", fontsize=14)
    axes[0].axis('off')

    axes[1].imshow(img)
    axes[1].plot([left, right], [top, top], 'lime', linewidth=4)
    axes[1].plot([left, left], [top, bottom], 'lime', linewidth=4)
    axes[1].plot([right, right], [top, bottom], 'red', linewidth=3, linestyle='--')
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
#  處理單張圖
# ============================================================
def process_one(jpg_path, out_dir):
    name = os.path.basename(jpg_path)
    img = io.imread(jpg_path)

    W = img.shape[1]
    scale = W / BASE_IMAGE_WIDTH
    cell_diameter = CELL_DIAMETER_BASE * scale
    square_size = int(round(SQUARE_SIZE_BASE * scale))
    square_size_tol = max(20, int(round(square_size * SQUARE_SIZE_TOL_FRAC)))

    masks, *_ = model.eval(img, diameter=cell_diameter)
    n_total = int(masks.max())

    img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
    h_peaks, v_peaks = detect_grid_lines(img_gray)
    h_lines = cluster_lines(h_peaks)
    v_lines = cluster_lines(v_peaks)
    bounds = find_square_by_size(h_lines, v_lines, img.shape,
                                 target=square_size, tol=square_size_tol)
    if bounds is None:
        return {'檔名': name, '全部數': n_total, 'L-shape計數': '',
                '排除壓右下': '', '框外': '',
                '方框上': '', '方框下': '', '方框左': '', '方框右': '',
                '單張外推_cells_per_mL': '', '最終濃度_cells_per_mL': '',
                'note': '找不到計數方格'}

    inc, exc, out, cent = apply_lshape(masks, bounds)
    n_in = len(inc)
    concentration = n_in * DILUTION_FACTOR / VOLUME_PER_IMAGE_ML

    base = os.path.splitext(name)[0]
    out_jpg = os.path.join(out_dir, f"{base}_lshape.jpg")
    visualize(img, masks, bounds, inc, exc, out, cent, out_jpg)

    return {
        '檔名': name,
        '全部數': n_total,
        'L-shape計數': n_in,
        '排除壓右下': len(exc),
        '框外': len(out),
        '方框上': bounds[0], '方框下': bounds[1],
        '方框左': bounds[2], '方框右': bounds[3],
        '單張外推_cells_per_mL': round(concentration),
        '最終濃度_cells_per_mL': '',
        'note': '',
    }


# ============================================================
#  主流程
# ============================================================
results_dir = os.path.join(FOLDER, 'results')
os.makedirs(results_dir, exist_ok=True)

all_rows = []
counts = []

jpgs = sorted(glob.glob(os.path.join(FOLDER, '*.jpg')))
jpgs += sorted(glob.glob(os.path.join(FOLDER, '*.png')))
jpgs = [j for j in jpgs if '_seg' not in j and '_lshape' not in j]
print(f"\n==== 單室:{len(jpgs)} 張 ====")

for i, jpg in enumerate(jpgs, 1):
    print(f"  [{i}/{len(jpgs)}] {os.path.basename(jpg)}", end=' ')
    row = process_one(jpg, results_dir)
    all_rows.append(row)
    if isinstance(row['L-shape計數'], int):
        counts.append(row['L-shape計數'])
    print(f"→ 全部={row['全部數']}, L-shape={row['L-shape計數']}, 單張外推={row['單張外推_cells_per_mL']}")


# ============================================================
#  小計、總計
# ============================================================
n_imgs = len(counts)
total_cells = sum(counts)
total_microliter = n_imgs * VOLUME_PER_IMAGE_ML * 1000  # mL → μL
per_microliter = total_cells / total_microliter if total_microliter else 0
final_concentration = per_microliter * 1000 * DILUTION_FACTOR


def empty_row():
    return {k: '' for k in ['檔名', '全部數', 'L-shape計數',
                            '排除壓右下', '框外', '方框上', '方框下',
                            '方框左', '方框右',
                            '單張外推_cells_per_mL', '最終濃度_cells_per_mL', 'note']}

summary_rows = []

# Step 1:合計
r = empty_row(); r.update({
    '檔名': f'Step 1 合計 ({n_imgs} 張)',
    'L-shape計數': total_cells,
    'note': f'所有 L-shape 計數加起來 = {total_cells} 顆 (在 {total_microliter:g} microliter 內)'})
summary_rows.append(r)

# Step 2:÷ μL
r = empty_row(); r.update({
    '檔名': f'Step 2 ÷ {total_microliter:g} 微升',
    'L-shape計數': round(per_microliter, 2),
    'note': f'{total_cells} ÷ {total_microliter:g} = {per_microliter:.2f} 顆 / 1 microliter'})
summary_rows.append(r)

# Step 3:× 1000 → cells/mL
r = empty_row(); r.update({
    '檔名': 'Step 3 × 1000 (回推 1 mL)',
    '最終濃度_cells_per_mL': round(final_concentration),
    'note': f'{per_microliter:.2f} × 1000 × {DILUTION_FACTOR} (稀釋) = {round(final_concentration):,} cells/mL'})
summary_rows.append(r)

# 最終結果
r = empty_row(); r.update({
    '檔名': '⭐ 最終濃度',
    '最終濃度_cells_per_mL': round(final_concentration),
    'note': f'最終 = {round(final_concentration):,} cells/mL'})
summary_rows.append(r)


# ============================================================
#  寫 CSV
# ============================================================
csv_path = os.path.join(results_dir, 'cell_counts.csv')
fieldnames = ['檔名', '全部數', 'L-shape計數',
              '排除壓右下', '框外',
              '方框上', '方框下', '方框左', '方框右',
              '單張外推_cells_per_mL', '最終濃度_cells_per_mL', 'note']

with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    sep = {k: '' for k in fieldnames}
    bar = {k: '─' * 10 if k == '檔名' else '' for k in fieldnames}

    for r in all_rows:
        w.writerow({k: r.get(k, '') for k in fieldnames})
    w.writerow(bar)
    w.writerow(summary_rows[0])  # Step 1 合計
    w.writerow(sep)
    w.writerow(summary_rows[1])  # Step 2 ÷ μL
    w.writerow(summary_rows[2])  # Step 3 × 1000
    w.writerow(sep)
    w.writerow(summary_rows[3])  # ⭐ 最終濃度


print(f"\n{'=' * 70}")
print(f"[OK] CSV: {csv_path}")
print(f"[OK] 視覺化: {results_dir}/")
print(f"\n=== 計算過程 ===")
print(f"  Step 1  合計:  {total_cells} 顆細胞 ({n_imgs} 張 = {total_microliter:g} 微升)")
print(f"  Step 2  ÷ {total_microliter:g} 微升: {per_microliter:.2f} 顆 / 1 微升")
print(f"  Step 3  × 1000(回推 1 mL):  {per_microliter:.2f} × 1000 × {DILUTION_FACTOR} = {final_concentration:,.0f} cells/mL")
print(f"\n  ⭐ 最終濃度 = {final_concentration:,.0f} cells/mL")
print(f"{'=' * 70}")
