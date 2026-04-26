"""
把 labeling_A/ 或 labeling_B/ 隨機分成 train/test，打包成 zip 傳到 Drive 用。

標注規則對應:
    labeling_A/ = 連在一起算 1 顆(整個分裂雙球當 1 個 mask)
    labeling_B/ = 明顯兩球算 2 顆(分裂雙球各當 1 個 mask)

用法：
    python colabtest/finetune/split_train_test.py A
    python colabtest/finetune/split_train_test.py B

會產生:
    D:\\Algaeorithm-pilot_backend\\colabtest\\cellpose_train_A.zip
    (內含 cellpose_train_A/train/ 和 cellpose_train_A/test/)
"""
import os
import sys
import random
import shutil
import zipfile
from pathlib import Path

N_TEST = 5
SEED = 42

if len(sys.argv) < 2 or sys.argv[1].upper() not in ('A', 'B'):
    print("用法: python split_train_test.py A    (或 B)")
    sys.exit(1)

tag = sys.argv[1].upper()
base = Path(r"D:\Algaeorithm-pilot_backend\colabtest")
src_dir = base / f"labeling_{tag}"
out_name = f"cellpose_train_{tag}"
out_dir = base / out_name
train_dir = out_dir / "train"
test_dir = out_dir / "test"
zip_path = base / f"{out_name}.zip"

if not src_dir.exists():
    print(f"[ERROR] 找不到 {src_dir}")
    sys.exit(1)

# 找出所有有效配對
pairs = []
for jpg in sorted(src_dir.glob("*.jpg")):
    seg = jpg.with_name(jpg.stem + "_seg.npy")
    if seg.exists():
        pairs.append((jpg, seg))
    else:
        print(f"[SKIP] {jpg.name} 沒有對應的 _seg.npy")

print(f"找到 {len(pairs)} 組")
if len(pairs) < N_TEST + 10:
    print(f"[WARN] 資料量偏少({len(pairs)} 組)")

# 隨機切
random.seed(SEED)
random.shuffle(pairs)
test_pairs = pairs[:N_TEST]
train_pairs = pairs[N_TEST:]
print(f"  train: {len(train_pairs)}    test: {len(test_pairs)}")

# 重建輸出資料夾
if out_dir.exists():
    shutil.rmtree(out_dir)
train_dir.mkdir(parents=True)
test_dir.mkdir(parents=True)

# 複製
for jpg, seg in train_pairs:
    shutil.copy2(jpg, train_dir / jpg.name)
    shutil.copy2(seg, train_dir / seg.name)
for jpg, seg in test_pairs:
    shutil.copy2(jpg, test_dir / jpg.name)
    shutil.copy2(seg, test_dir / seg.name)

print(f"\n[test 集挑了這 {N_TEST} 張]")
for jpg, _ in test_pairs:
    print(f"  {jpg.name}")

# 打包
print(f"\n打包 zip...")
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for path in out_dir.rglob('*'):
        if path.is_file():
            zf.write(path, path.relative_to(out_dir.parent))

size_mb = zip_path.stat().st_size / 1024 / 1024
print(f"[OK] 產生 {zip_path}  ({size_mb:.1f} MB)")

print(f"\n========= 下一步 =========")
print(f"1. 把 {zip_path.name} 上傳到 Google Drive 的 MyDrive/")
print(f"2. Colab 第一個 cell 跑解壓:")
print(f"     !unzip -o /content/drive/MyDrive/{zip_path.name} -d /content/drive/MyDrive/")
print(f"3. step3_finetune.py 把這兩行改成:")
print(f"     TRAIN_DIR = '/content/drive/MyDrive/{out_name}/train'")
print(f"     TEST_DIR  = '/content/drive/MyDrive/{out_name}/test'")
print(f"   然後跑 step3_finetune.py")
