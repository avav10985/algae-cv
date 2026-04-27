"""
血球計數器 L-shape 計數規則

規則:
    上邊、左邊壓到的細胞 → 算入
    下邊、右邊壓到的細胞 → 不算

判斷:用細胞身體是否碰到右/下邊判斷(碰到 → 排除)

輸入: 原圖 + cellpose 的 _seg.npy
輸出: L-shape 規則下的細胞數 + 視覺化圖

使用:
    python count_lshape.py path/to/image.jpg
    (會自動讀同名的 _seg.npy)
"""
import os
import sys
import numpy as np
import cv2
from scipy.signal import find_peaks
from scipy.ndimage import uniform_filter1d
import matplotlib.pyplot as plt
from PIL import Image


def imread(path):
    """讀圖,回傳 RGB numpy 陣列(避免 cv2 中文路徑問題)。"""
    return np.array(Image.open(path).convert('RGB'))


# ============================================================
#  格線偵測
# ============================================================
def detect_grid_lines(img_gray,
                     brightness_thresh=180,
                     min_line_distance=20,
                     smooth_window=5,
                     peak_height_sigma=1.0):
    """
    回傳 (h_peaks, v_peaks) - 水平、垂直格線的位置(像素)
    """
    _, binary = cv2.threshold(img_gray, brightness_thresh, 255, cv2.THRESH_BINARY)

    h_proj = binary.sum(axis=1).astype(float)
    v_proj = binary.sum(axis=0).astype(float)

    h_proj_s = uniform_filter1d(h_proj, size=smooth_window)
    v_proj_s = uniform_filter1d(v_proj, size=smooth_window)

    h_thresh = h_proj_s.mean() + h_proj_s.std() * peak_height_sigma
    v_thresh = v_proj_s.mean() + v_proj_s.std() * peak_height_sigma

    h_peaks, _ = find_peaks(h_proj_s, height=h_thresh, distance=min_line_distance)
    v_peaks, _ = find_peaks(v_proj_s, height=v_thresh, distance=min_line_distance)

    return h_peaks, v_peaks, (h_proj_s, v_proj_s)


def find_double_line_centers(peaks, gap_threshold=40, min_cluster_size=2):
    """
    只挑出「雙線」(2 個或以上很近的 peaks),回傳每組中點。
    單線(孤立的 peak)會被忽略 — 因為單線是細格線,不是計數方格邊界。
    """
    if len(peaks) == 0:
        return []
    clusters = []
    cur = [peaks[0]]
    for p in peaks[1:]:
        if p - cur[-1] <= gap_threshold:
            cur.append(p)
        else:
            if len(cur) >= min_cluster_size:
                clusters.append(int(np.median(cur)))
            cur = [p]
    if len(cur) >= min_cluster_size:
        clusters.append(int(np.median(cur)))
    return clusters


def cluster_double_lines(peaks, gap_threshold=40):
    """舊名 — 包含所有 peak(雙線取中點,單線保留)。保留作為 fallback。"""
    if len(peaks) == 0:
        return []
    clusters = []
    cur = [peaks[0]]
    for p in peaks[1:]:
        if p - cur[-1] <= gap_threshold:
            cur.append(p)
        else:
            clusters.append(int(np.median(cur)))
            cur = [p]
    clusters.append(int(np.median(cur)))
    return clusters


# ============================================================
#  尋找計數方格
# ============================================================
# 1mm² 計數方格在當前放大率下的尺寸(像素)— 從 39_23 的雙線距離量出來
SQUARE_SIZE_PX = 640
SQUARE_SIZE_TOL = 30  # 容忍誤差


def find_square_by_size(h_lines, v_lines, img_shape, target_size=640, tolerance=30):
    """
    找「兩條格線剛好距離 target_size」的組合,當作計數方格邊界。
    如果有多組,選最接近圖片中心的。
    回傳 (top, bottom, left, right) 或 None。
    """
    H, W = img_shape[:2]

    # 找水平方向的「上下對」(距離 ~target_size)
    h_pairs = []
    for i, h1 in enumerate(h_lines):
        for h2 in h_lines[i+1:]:
            if abs((h2 - h1) - target_size) <= tolerance:
                h_pairs.append((h1, h2))

    # 找垂直方向的「左右對」
    v_pairs = []
    for i, v1 in enumerate(v_lines):
        for v2 in v_lines[i+1:]:
            if abs((v2 - v1) - target_size) <= tolerance:
                v_pairs.append((v1, v2))

    if not h_pairs or not v_pairs:
        return None

    # 選最接近圖片中心的組合
    img_y_center = H / 2
    img_x_center = W / 2
    best_h = min(h_pairs, key=lambda p: abs((p[0] + p[1]) / 2 - img_y_center))
    best_v = min(v_pairs, key=lambda p: abs((p[0] + p[1]) / 2 - img_x_center))

    return (best_h[0], best_h[1], best_v[0], best_v[1])


def find_counting_square(h_lines, v_lines, img_shape, n_grid_squares=5):
    """
    從偵測到的格線找出「主要計數方格」(包含 n×n 個細格的大格)。

    策略:
    - 假設大格是由 n_grid_squares=5 個小格組成 (1mm² = 5×5 個 0.2mm 小格)
    - 從所有水平/垂直線中挑「跨度最接近圖片中心、且寬度最大」的組合

    回傳 (top, bottom, left, right) 像素座標。
    """
    h, w = img_shape[:2]

    if len(h_lines) < 2 or len(v_lines) < 2:
        return None

    # 簡單策略:取最外圍兩條線當邊界
    top, bottom = h_lines[0], h_lines[-1]
    left, right = v_lines[0], v_lines[-1]

    return top, bottom, left, right


# ============================================================
#  L-shape 規則計數
# ============================================================
def apply_lshape(masks, bounds):
    """
    身體碰邊規則:
      - 身體跟方框有交集才考慮
      - 碰到「右邊」的線(任何像素 x == right 或更右) → 不算
      - 碰到「下邊」的線(任何像素 y == bottom 或更下) → 不算
      - 否則(完全在框內 / 只碰到上邊或左邊)→ 算

    L-shape 標準寫法:壓上邊和左邊的算入,壓下邊和右邊的不算。
    """
    top, bottom, left, right = bounds
    included, excluded, outside = [], [], []
    centroids = {}

    for mask_id in range(1, int(masks.max()) + 1):
        ys, xs = np.where(masks == mask_id)
        if len(ys) == 0:
            continue
        cy, cx = float(ys.mean()), float(xs.mean())
        centroids[mask_id] = (cy, cx)

        # 身體是否與方框有交集?
        in_box_pixels = (ys >= top) & (ys <= bottom) & (xs >= left) & (xs <= right)
        if not in_box_pixels.any():
            outside.append(mask_id)
            continue

        # 是否碰到 right 或 bottom 邊?
        touches_right = (xs == right).any() or ((xs > right) & (ys >= top) & (ys <= bottom)).any()
        touches_bottom = (ys == bottom).any() or ((ys > bottom) & (xs >= left) & (xs <= right)).any()

        if touches_right or touches_bottom:
            excluded.append(mask_id)
        else:
            included.append(mask_id)

    return {
        'included': included,
        'excluded': excluded,
        'outside': outside,
        'centroids': centroids,
    }


# ============================================================
#  視覺化
# ============================================================
def visualize(img, masks, bounds, result, save_path=None, title_extra=""):
    top, bottom, left, right = bounds
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    ax.imshow(img)

    # 計數方格框:上邊和左邊用粗線(算入),下邊和右邊用虛線(排除)
    ax.plot([left, right], [top, top], color='lime', linewidth=4, label='上(算)')
    ax.plot([left, left], [top, bottom], color='lime', linewidth=4, label='左(算)')
    ax.plot([right, right], [top, bottom], color='red', linewidth=3, linestyle='--', label='右(不算)')
    ax.plot([left, right], [bottom, bottom], color='red', linewidth=3, linestyle='--', label='下(不算)')

    # 細胞點
    for mid in result['included']:
        cy, cx = result['centroids'][mid]
        ax.plot(cx, cy, 'o', color='lime', markersize=5, markeredgecolor='black', markeredgewidth=0.5)
    for mid in result['excluded']:
        cy, cx = result['centroids'][mid]
        ax.plot(cx, cy, 'x', color='red', markersize=10, markeredgewidth=2)
    for mid in result['outside']:
        cy, cx = result['centroids'][mid]
        ax.plot(cx, cy, 'o', color='gray', markersize=3, alpha=0.4)

    ax.legend(loc='upper right', fontsize=10)
    n_in = len(result['included'])
    n_ex = len(result['excluded'])
    ax.set_title(f"L-shape 計數: {n_in} 顆  (排除壓下/右邊: {n_ex} 顆) {title_extra}",
                 fontsize=14)
    ax.axis('off')

    if save_path:
        plt.savefig(save_path, dpi=100, bbox_inches='tight')
    return fig


# ============================================================
#  主流程
# ============================================================
def process_image(img_path, seg_path=None, save_dir=None, manual_bounds=None):
    """
    跑單張圖。
    manual_bounds: (top, bottom, left, right) - 手動指定計數方格,跳過自動偵測
    """
    if seg_path is None:
        seg_path = img_path.replace('.jpg', '_seg.npy').replace('.png', '_seg.npy')

    img = imread(img_path)
    seg = np.load(seg_path, allow_pickle=True).item()
    masks = seg['masks']

    if len(img.shape) == 3:
        img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        img_gray = img

    if manual_bounds is None:
        h_peaks, v_peaks, _ = detect_grid_lines(img_gray)
        # 把太接近的 peak 合併,得到所有獨立的格線位置
        h_lines = cluster_double_lines(h_peaks)
        v_lines = cluster_double_lines(v_peaks)
        bounds = find_square_by_size(h_lines, v_lines, img.shape,
                                      target_size=SQUARE_SIZE_PX, tolerance=SQUARE_SIZE_TOL)
        if bounds is None:
            print(f"[WARN] 找不到 ~{SQUARE_SIZE_PX}px 的方框,fallback 用最外圍線")
            bounds = find_counting_square(h_lines, v_lines, img.shape)
    else:
        bounds = manual_bounds

    if bounds is None:
        print("[ERROR] 找不到計數方格")
        return None
    print(f"計數方格 (top, bottom, left, right): {bounds}")

    result = apply_lshape(masks, bounds)
    print(f"\n總細胞數: {int(masks.max())}")
    print(f"L-shape 計入: {len(result['included'])} 顆")
    print(f"L-shape 排除(壓下/右): {len(result['excluded'])} 顆")
    print(f"框外: {len(result['outside'])} 顆")

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, os.path.basename(img_path).replace('.jpg', '_lshape.jpg'))
    else:
        save_path = None

    fig = visualize(img, masks, bounds, result, save_path=save_path)
    return result, fig


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('image', help='路徑 jpg(自動讀同名 _seg.npy)')
    parser.add_argument('--bounds', help='手動指定計數方格 top,bottom,left,right (像素,逗號分隔)')
    parser.add_argument('--save-dir', default=None, help='輸出資料夾(預設同圖檔位置)')
    args = parser.parse_args()

    img_path = args.image
    save_dir = args.save_dir or os.path.dirname(img_path)

    manual_bounds = None
    if args.bounds:
        nums = [int(x) for x in args.bounds.split(',')]
        if len(nums) != 4:
            print("[ERROR] --bounds 要剛好 4 個數字: top,bottom,left,right")
            sys.exit(1)
        manual_bounds = tuple(nums)
        print(f"使用手動指定: {manual_bounds}")

    result, fig = process_image(img_path, save_dir=save_dir, manual_bounds=manual_bounds)
    plt.show()
