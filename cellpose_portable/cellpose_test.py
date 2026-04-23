"""
CellPose 測試腳本 — 用預訓練模型偵測藻類細胞

安裝：
    pip install cellpose matplotlib

使用：
    D:
    cd D:\Algaeorithm-pilot_backend
    venv\Scripts\activate
    python cellpose_test.py "D:/藻類比賽/資料/0102下-20260324T225901Z-3-001/0102下/20260102144751.jpg" --scale 0.5
    python cellpose_test.py <image_path>
    python cellpose_test.py "D:/藻類比賽/資料/0102下-20260324T225901Z-3-001/0102下/20260102144751.jpg"

可選參數：
    --channel {gray, blue, green}   選擇處理的顏色通道（預設 gray）
    --diameter N                    指定細胞直徑（像素），不給則自動估計
    --scale 0.5                     縮放圖片加速（預設 1.0，CPU 建議 0.5）
"""
import argparse
import os
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
from cellpose import models, plot
from PIL import Image


CHANNEL_MAP = {
    "gray":  [0, 0],
    "red":   [1, 0],
    "green": [2, 0],
    "blue":  [3, 0],
}


def detect_cells(image_path, channel="gray", diameter=None, scale=1.0):
    print(f"[1/3] 載入模型（CellPose 4.x 預設 cpsam）")
    model = models.CellposeModel(gpu=False)

    print(f"[2/3] 讀取圖片：{image_path}")
    img = np.array(Image.open(image_path))
    print(f"      原始尺寸：{img.shape}")

    if scale != 1.0:
        import cv2
        new_w = int(img.shape[1] * scale)
        new_h = int(img.shape[0] * scale)
        img = cv2.resize(img, (new_w, new_h))
        print(f"      縮放後尺寸：{img.shape}")

    print(f"[3/3] 執行偵測（CPU 上可能需要 1-5 分鐘）...")
    t0 = time.time()
    eval_kwargs = {"channels": CHANNEL_MAP[channel]}
    if diameter is not None:
        eval_kwargs["diameter"] = diameter
    result = model.eval(img, **eval_kwargs)
    # v3 回傳 4 個 (masks, flows, styles, diams)，v4 回傳 3 個
    masks = result[0]
    elapsed = time.time() - t0

    n_cells = int(masks.max())
    print(f"\n=== 結果 ===")
    print(f"偵測到 {n_cells} 顆細胞")
    print(f"耗時：{elapsed:.1f} 秒")

    return img, masks, n_cells


def visualize(img, masks, n_cells, output_path="cellpose_result.jpg"):
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))

    axes[0].imshow(img)
    axes[0].set_title("Original", fontsize=14)
    axes[0].axis("off")

    overlay = plot.mask_overlay(img, masks)
    axes[1].imshow(overlay)
    axes[1].set_title(f"Detected: {n_cells} cells", fontsize=14)
    axes[1].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches="tight")
    print(f"\n視覺化已存到：{output_path}")
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="CellPose 藻類細胞偵測")
    parser.add_argument("image_path", help="要偵測的圖片路徑")
    parser.add_argument("--channel", choices=list(CHANNEL_MAP.keys()), default="gray",
                        help="處理的顏色通道（預設 gray）")
    parser.add_argument("--diameter", type=float, default=None,
                        help="細胞直徑（像素）。留空則自動估計")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="縮放比例，0.5 可加速 4 倍（預設 1.0）")
    parser.add_argument("--output", default="cellpose_result.jpg",
                        help="輸出圖片路徑")
    args = parser.parse_args()

    if not os.path.exists(args.image_path):
        print(f"找不到圖片：{args.image_path}")
        sys.exit(1)

    img, masks, n_cells = detect_cells(
        args.image_path,
        channel=args.channel,
        diameter=args.diameter,
        scale=args.scale,
    )
    visualize(img, masks, n_cells, args.output)


if __name__ == "__main__":
    main()
