"""
批次跑 L-shape 計數規則

對一個資料夾裡所有 (jpg + _seg.npy) 配對:
  - 自動偵測計數方格(1mm² 中央方格)
  - 套用 L-shape 規則(身體碰上/右算,碰下/左不算)
  - 輸出 CSV + 視覺化結果圖

用法:
    python batch_lshape.py <資料夾路徑> [--out 輸出資料夾]

範例:
    python colabtest/finetune/batch_lshape.py colabtest/labeling_A
    → 會在 colabtest/labeling_A 產生 lshape_results/ 子資料夾
      內含 cell_counts.csv 和每張圖的 _lshape.jpg
"""
import os
import sys
import glob
import argparse
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 不開視窗
import matplotlib.pyplot as plt

# 匯入 count_lshape 的核心函式
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from count_lshape import (
    imread, detect_grid_lines, cluster_double_lines,
    find_square_by_size, find_counting_square,
    apply_lshape, visualize,
    SQUARE_SIZE_PX, SQUARE_SIZE_TOL,
)


def process_folder(folder, out_dir=None):
    folder = os.path.abspath(folder)
    if out_dir is None:
        out_dir = os.path.join(folder, 'lshape_results')
    os.makedirs(out_dir, exist_ok=True)

    # 找出所有 jpg + 對應 _seg.npy
    pairs = []
    for jpg in sorted(glob.glob(os.path.join(folder, '*.jpg'))):
        if '_lshape' in jpg or '_result' in jpg:
            continue  # 跳過視覺化輸出
        seg = jpg.replace('.jpg', '_seg.npy')
        if os.path.exists(seg):
            pairs.append((jpg, seg))

    print(f"找到 {len(pairs)} 組")
    if not pairs:
        print("[ERROR] 沒有 (jpg + _seg.npy) 配對")
        return

    rows = []
    for i, (jpg, seg) in enumerate(pairs, 1):
        name = os.path.basename(jpg)
        print(f"\n[{i}/{len(pairs)}] {name}")

        img = imread(jpg)
        seg_data = np.load(seg, allow_pickle=True).item()
        masks = seg_data['masks']

        # 自動偵測方框
        import cv2
        img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
        h_peaks, v_peaks, _ = detect_grid_lines(img_gray)
        h_lines = cluster_double_lines(h_peaks)
        v_lines = cluster_double_lines(v_peaks)
        bounds = find_square_by_size(h_lines, v_lines, img.shape,
                                     target_size=SQUARE_SIZE_PX,
                                     tolerance=SQUARE_SIZE_TOL)
        if bounds is None:
            print(f"  [WARN] 找不到方框,fallback 用最外圍線")
            bounds = find_counting_square(h_lines, v_lines, img.shape)
        if bounds is None:
            print(f"  [SKIP] 無法決定方框")
            continue

        result = apply_lshape(masks, bounds)
        n_total = int(masks.max())
        n_in = len(result['included'])
        n_ex = len(result['excluded'])
        n_out = len(result['outside'])

        # 從檔名抓「全部 / L-shape」目標數字(若檔名是 「39_23.jpg」)
        target_total, target_lshape = None, None
        try:
            stem = os.path.splitext(name)[0]
            parts = stem.split('_')
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                target_total = int(parts[0])
                target_lshape = int(parts[1])
        except Exception:
            pass

        diff_str = ""
        if target_lshape is not None:
            diff = n_in - target_lshape
            diff_str = f"  目標={target_lshape}  diff={diff:+d}"
        print(f"  總細胞: {n_total}  L-shape: {n_in} 顆 (排除 {n_ex},框外 {n_out}){diff_str}")

        # 視覺化
        out_jpg = os.path.join(out_dir, name.replace('.jpg', '_lshape.jpg'))
        fig = visualize(img, masks, bounds, result, save_path=out_jpg)
        plt.close(fig)

        rows.append({
            '檔名': name,
            '全部數': n_total,
            'L-shape計數': n_in,
            '排除壓左下': n_ex,
            '框外': n_out,
            '方框上': bounds[0],
            '方框下': bounds[1],
            '方框左': bounds[2],
            '方框右': bounds[3],
            '檔名全部數': target_total if target_total is not None else '',
            '檔名L-shape': target_lshape if target_lshape is not None else '',
        })

    # 寫 CSV
    csv_path = os.path.join(out_dir, 'cell_counts.csv')
    if rows:
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n[OK] CSV: {csv_path}")
        print(f"[OK] 視覺化圖: {out_dir}/")

        # 統計摘要
        counts = [r['L-shape計數'] for r in rows]
        print(f"\n=== 統計摘要 ===")
        print(f"  圖片數: {len(rows)}")
        print(f"  L-shape 平均: {sum(counts)/len(counts):.1f}")
        print(f"  L-shape min/max: {min(counts)} / {max(counts)}")

        # 如果檔名有目標,印準確度
        targets = [r['檔名L-shape'] for r in rows if r['檔名L-shape'] != '']
        if targets:
            errs = [abs(r['L-shape計數'] - r['檔名L-shape']) for r in rows if r['檔名L-shape'] != '']
            print(f"  vs 檔名目標 平均絕對誤差: {sum(errs)/len(errs):.2f} 顆")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', help='含 jpg + _seg.npy 的資料夾')
    parser.add_argument('--out', default=None, help='輸出資料夾(預設為 <folder>/lshape_results/)')
    args = parser.parse_args()

    process_folder(args.folder, out_dir=args.out)
