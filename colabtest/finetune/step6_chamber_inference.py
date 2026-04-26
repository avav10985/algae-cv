"""
Step 6: 血球計數器(上室+下室)完整批次

對母資料夾下的 up/ 和 down/ 子資料夾的所有圖:
  1. 用 fine-tuned cpsam 偵測細胞(全部數)
  2. 偵測 1mm² 方格 + 套 L-shape 規則
  3. 算濃度(cells/mL)
  4. 上室、下室分別平均;再算總平均 + 最終濃度
  5. CSV 包含明細 + 小計 + 總計;視覺化分 up / down 子資料夾

預設假設:
  - 5×5 計數方格(中央 1mm² 大格)
  - 計數體積 = 1mm × 1mm × 0.1mm = 10⁻⁴ mL
  - 細胞濃度 (cells/mL) = L-shape計數 × 10⁴ × 稀釋倍率
  - 稀釋倍率 = 1(沒稀釋)

使用方式:
  1. Drive 結構:
     PARENT_FOLDER/
     ├── up/
     │   ├── *.jpg
     ├── down/
     │   └── *.jpg
  2. 修改下面 PARENT_FOLDER 路徑
  3. Colab 設 T4 GPU,把整份貼進 cell 跑
  4. 輸出在 PARENT_FOLDER/results/
"""
# ============================================================
#  ⚙️ 設定區(可調整)
# ============================================================
PARENT_FOLDER = '/content/drive/MyDrive/sample_2026_04_27/'   # ← 母資料夾
MODEL_PATH    = '/content/drive/MyDrive/cellpose_train_A/models/my_cpsam_A'

# 計數參數
CELL_DIAMETER = 45         # cellpose 偵測直徑
SQUARE_SIZE_PX = 640       # 1mm² 計數方格在這個放大率下的像素邊長
SQUARE_SIZE_TOL = 30       # 方格尺寸容忍誤差

# 濃度公式(可調)
DILUTION_FACTOR = 1.0      # 稀釋倍率(沒稀釋=1;1:1 trypan blue=2)
VOLUME_PER_SQUARE_ML = 1e-4  # 1mm² × 0.1mm 深 = 10⁻⁴ mL
# → 濃度 = L-shape計數 × DILUTION_FACTOR / VOLUME_PER_SQUARE_ML
#   等價於:L-shape計數 × 10⁴ × DILUTION_FACTOR (cells/mL)


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

# 強制重新掛載,確保看得到剛在 Drive 新建的資料夾
drive.mount('/content/drive', force_remount=True)
if not torch.cuda.is_available():
    raise SystemExit("[ERROR] 沒有 GPU,Runtime → Change runtime type → T4 GPU")
print(f"[OK] GPU: {torch.cuda.get_device_name(0)}")

# 確認 PARENT_FOLDER 看得到
if not os.path.exists(PARENT_FOLDER):
    raise SystemExit(f"[ERROR] 找不到母資料夾: {PARENT_FOLDER}\n  確認路徑正確,且 Drive 已同步")
print(f"[OK] {PARENT_FOLDER} 內容: {sorted(os.listdir(PARENT_FOLDER))}")


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
    """身體碰邊規則:碰左/下 → 不算;否則 → 算。"""
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


def visualize(img, masks, bounds, included, excluded, outside, centroids, save_path):
    top, bottom, left, right = bounds
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))

    axes[0].imshow(plot.mask_overlay(img, masks))
    axes[0].set_title(f"Cellpose Detection: {int(masks.max())} cells", fontsize=14)
    axes[0].axis('off')

    axes[1].imshow(img)
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
#  處理單張圖
# ============================================================
def process_one(jpg_path, out_dir, chamber_prefix=''):
    name = os.path.basename(jpg_path)
    img = io.imread(jpg_path)

    # cellpose 偵測
    masks, *_ = model.eval(img, diameter=CELL_DIAMETER)
    n_total = int(masks.max())

    # 自動偵測方格
    img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
    h_peaks, v_peaks = detect_grid_lines(img_gray)
    h_lines = cluster_lines(h_peaks)
    v_lines = cluster_lines(v_peaks)
    bounds = find_square_by_size(h_lines, v_lines, img.shape,
                                 target=SQUARE_SIZE_PX, tol=SQUARE_SIZE_TOL)
    if bounds is None:
        return {'檔名': name, '全部數': n_total, 'L-shape計數': '',
                '排除壓左下': '', '框外': '',
                '方框上': '', '方框下': '', '方框左': '', '方框右': '',
                '濃度_cells_per_mL': '', 'note': '找不到計數方格'}

    inc, exc, out, cent = apply_lshape(masks, bounds)
    n_in = len(inc)

    # 濃度公式
    concentration = n_in * DILUTION_FACTOR / VOLUME_PER_SQUARE_ML

    # 視覺化:檔名加上 chamber 前綴(例如 up_xxx_lshape.jpg)避免 up/down 同名衝突
    base = os.path.splitext(name)[0]
    prefix = f"{chamber_prefix}_" if chamber_prefix else ''
    out_jpg = os.path.join(out_dir, f"{prefix}{base}_lshape.jpg")
    visualize(img, masks, bounds, inc, exc, out, cent, out_jpg)

    return {
        '檔名': name,
        '全部數': n_total,
        'L-shape計數': n_in,
        '排除壓左下': len(exc),
        '框外': len(out),
        '方框上': bounds[0], '方框下': bounds[1],
        '方框左': bounds[2], '方框右': bounds[3],
        '濃度_cells_per_mL': round(concentration),
        'note': '',
    }


# ============================================================
#  主流程
# ============================================================
results_dir = os.path.join(PARENT_FOLDER, 'results')
os.makedirs(results_dir, exist_ok=True)

all_rows = []   # 明細(每張圖一列)
chamber_data = {'up': [], 'down': []}  # 暫存每個 chamber 的 lshape 計數

for chamber in ['up', 'down']:
    in_folder = os.path.join(PARENT_FOLDER, chamber)
    if not os.path.exists(in_folder):
        print(f"[WARN] 找不到 {in_folder},跳過")
        continue
    jpgs = sorted(glob.glob(os.path.join(in_folder, '*.jpg')))
    jpgs += sorted(glob.glob(os.path.join(in_folder, '*.png')))
    jpgs = [j for j in jpgs if '_seg' not in j and '_lshape' not in j]
    print(f"\n==== {chamber} 室:{len(jpgs)} 張 ====")

    for i, jpg in enumerate(jpgs, 1):
        print(f"  [{i}/{len(jpgs)}] {os.path.basename(jpg)}", end=' ')
        # 視覺化檔名加上 chamber 前綴,直接放 results/
        row = process_one(jpg, results_dir, chamber_prefix=chamber)
        row['位置'] = chamber
        all_rows.append(row)
        if isinstance(row['L-shape計數'], int):
            chamber_data[chamber].append(row['L-shape計數'])
        print(f"→ 全部={row['全部數']}, L-shape={row['L-shape計數']}, 濃度={row['濃度_cells_per_mL']}")


# ============================================================
#  小計、總計
# ============================================================
def avg(xs):
    return sum(xs) / len(xs) if xs else 0

up_avg = avg(chamber_data['up'])
down_avg = avg(chamber_data['down'])
overall_avg = (up_avg + down_avg) / 2 if (chamber_data['up'] and chamber_data['down']) else (up_avg or down_avg)
final_concentration = overall_avg * DILUTION_FACTOR / VOLUME_PER_SQUARE_ML

summary_rows = [
    {'位置': '上室平均', '檔名': f"({len(chamber_data['up'])} 張)", '全部數': '',
     'L-shape計數': round(up_avg, 2),
     '排除壓左下': '', '框外': '',
     '方框上': '', '方框下': '', '方框左': '', '方框右': '',
     '濃度_cells_per_mL': round(up_avg * DILUTION_FACTOR / VOLUME_PER_SQUARE_ML),
     'note': ''},
    {'位置': '下室平均', '檔名': f"({len(chamber_data['down'])} 張)", '全部數': '',
     'L-shape計數': round(down_avg, 2),
     '排除壓左下': '', '框外': '',
     '方框上': '', '方框下': '', '方框左': '', '方框右': '',
     '濃度_cells_per_mL': round(down_avg * DILUTION_FACTOR / VOLUME_PER_SQUARE_ML),
     'note': ''},
    {'位置': '總平均', '檔名': '', '全部數': '',
     'L-shape計數': round(overall_avg, 2),
     '排除壓左下': '', '框外': '',
     '方框上': '', '方框下': '', '方框左': '', '方框右': '',
     '濃度_cells_per_mL': round(final_concentration),
     'note': f'稀釋={DILUTION_FACTOR}, 體積={VOLUME_PER_SQUARE_ML}mL'},
]


# ============================================================
#  寫 CSV
# ============================================================
csv_path = os.path.join(results_dir, 'cell_counts.csv')
fieldnames = ['位置', '檔名', '全部數', 'L-shape計數',
              '排除壓左下', '框外',
              '方框上', '方框下', '方框左', '方框右',
              '濃度_cells_per_mL', 'note']

with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    # 上室明細
    for r in all_rows:
        if r['位置'] == 'up':
            w.writerow({k: r.get(k, '') for k in fieldnames})
    w.writerow({'位置': '─' * 10, '檔名': '', '全部數': '', 'L-shape計數': '',
                '排除壓左下': '', '框外': '', '方框上': '', '方框下': '',
                '方框左': '', '方框右': '', '濃度_cells_per_mL': '', 'note': ''})
    w.writerow(summary_rows[0])  # 上室平均

    # 分隔
    w.writerow({k: '' for k in fieldnames})

    # 下室明細
    for r in all_rows:
        if r['位置'] == 'down':
            w.writerow({k: r.get(k, '') for k in fieldnames})
    w.writerow({'位置': '─' * 10, '檔名': '', '全部數': '', 'L-shape計數': '',
                '排除壓左下': '', '框外': '', '方框上': '', '方框下': '',
                '方框左': '', '方框右': '', '濃度_cells_per_mL': '', 'note': ''})
    w.writerow(summary_rows[1])  # 下室平均

    # 分隔 + 總計
    w.writerow({k: '' for k in fieldnames})
    w.writerow(summary_rows[2])

print(f"\n{'=' * 70}")
print(f"[OK] CSV: {csv_path}")
print(f"[OK] 視覺化: {results_dir}/(檔名以 up_ / down_ 前綴區分)")
print(f"\n=== 統計摘要 ===")
print(f"  上室({len(chamber_data['up'])} 張)平均 L-shape = {up_avg:.2f}")
print(f"  下室({len(chamber_data['down'])} 張)平均 L-shape = {down_avg:.2f}")
print(f"  總平均 L-shape = {overall_avg:.2f}")
print(f"  最終濃度 = {final_concentration:,.0f} cells/mL")
print(f"  (稀釋倍率 = {DILUTION_FACTOR}, 體積 = {VOLUME_PER_SQUARE_ML} mL)")
print(f"{'=' * 70}")
