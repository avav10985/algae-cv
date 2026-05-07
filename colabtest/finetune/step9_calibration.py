"""
Step 9: 線性迴歸,從色比 R/G/B 算 cells/mL

跑這個之前確認:
  - step6 / step8 對你想用的所有稀釋都跑完了
  - app拍照/0504/ 有 30 張照片(每比例 3 張,順序 1-10)

執行方式(本機,不用 Colab):
  cd d:\algae-cv
  python colabtest/finetune/step9_calibration.py

輸出:
  - calibration_data.csv          配對好的 18 筆資料
  - print: 兩種模型的係數 + R²
  - print: App.js 直接貼的 JS 程式碼
"""
import os, glob, csv, re, sys
import numpy as np

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# ============================================================
#  ⚙️ 設定
# ============================================================
DATA_FOLDER  = r'd:\algae-cv\algae_app\drive-download-20260506T195732Z-3-001'
APP_PHOTOS   = r'd:\algae-cv\algae_app\app拍照\0504'
RATIOS_TO_USE = [1, 3, 5, 8, 9, 10]   # 有顯微鏡計數的比例
OUT_CSV      = r'd:\algae-cv\calibration_data.csv'

# 要不要把 9 號排除(樣本問題)?跑完看 R² 再決定
EXCLUDE_RATIOS = []   # 例如 [9]


# ============================================================
#  1. 讀每個比例的 cells/mL(優先 step8 sensitive)
# ============================================================
def read_final_concentration(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row.get('位置','').startswith('⭐'):
                v = row['最終濃度_cells_per_mL']
                return int(v) if v else None
    return None

cells_data = {}
sources = {}
for r in RATIOS_TO_USE:
    sens_path = os.path.join(DATA_FOLDER, str(r), 'results_sensitive', 'cell_counts_sensitive.csv')
    base_path = os.path.join(DATA_FOLDER, str(r), 'results', 'cell_counts.csv')
    sens_val = read_final_concentration(sens_path)
    base_val = read_final_concentration(base_path)
    if sens_val is not None:
        cells_data[r] = sens_val; sources[r] = 'step8 sensitive'
    elif base_val is not None:
        cells_data[r] = base_val; sources[r] = 'step6'
    else:
        print(f'[WARN] 比例 {r} 兩種版本都找不到')

print('=== 比例 / cells/mL / 來源 ===')
for r in RATIOS_TO_USE:
    if r in cells_data:
        marker = ' (排除)' if r in EXCLUDE_RATIOS else ''
        print(f'  {r:>2}: {cells_data[r]:>10,}  ({sources[r]}){marker}')


# ============================================================
#  2. 讀 app 拍照
# ============================================================
photos = sorted(glob.glob(os.path.join(APP_PHOTOS, '*.jpg')))
phone_data = {}  # ratio -> [(R, G, B), ...]
for i, p in enumerate(photos):
    ratio = (i // 3) + 1   # 第 1-3 張 = 比例 1,4-6 = 比例 2,...
    if ratio not in RATIOS_TO_USE:
        continue
    m = re.search(r'_R(\d{3})G(\d{3})B(\d{3})', os.path.basename(p))
    if not m: continue
    rgb = tuple(int(g)/100 for g in m.groups())
    phone_data.setdefault(ratio, []).append(rgb)

print(f'\n=== App 照片 / 色比平均 ===')
for r in RATIOS_TO_USE:
    if r in phone_data:
        rs = phone_data[r]
        Ravg = sum(x[0] for x in rs)/len(rs)
        Gavg = sum(x[1] for x in rs)/len(rs)
        Bavg = sum(x[2] for x in rs)/len(rs)
        print(f'  {r:>2}: R={Ravg:.3f} G={Gavg:.3f} B={Bavg:.3f}  ({len(rs)} 張)')


# ============================================================
#  3. 配成樣本(N = 比例數 × 3)
# ============================================================
X_lin = []   # 直接 R, G, B
X_log = []   # Beer-Lambert: -log10(R), -log10(G), -log10(B)
y     = []
ratios_per_row = []

for r in RATIOS_TO_USE:
    if r in EXCLUDE_RATIOS or r not in cells_data or r not in phone_data:
        continue
    cells = cells_data[r]
    for (R, G, B) in phone_data[r]:
        X_lin.append([R, G, B])
        X_log.append([-np.log10(R), -np.log10(G), -np.log10(B)])
        y.append(cells)
        ratios_per_row.append(r)

X_lin = np.array(X_lin)
X_log = np.array(X_log)
y     = np.array(y, dtype=float)

print(f'\n=== 訓練集:N = {len(y)} 筆 ===')


# ============================================================
#  4. 線性迴歸(numpy lstsq,不需 sklearn)
# ============================================================
def fit(X, y, name):
    Xb = np.hstack([X, np.ones((len(X), 1))])
    coef, *_ = np.linalg.lstsq(Xb, y, rcond=None)
    y_pred = Xb @ coef
    ss_res = float(np.sum((y - y_pred)**2))
    ss_tot = float(np.sum((y - y.mean())**2))
    r2 = 1 - ss_res/ss_tot if ss_tot else 0
    rmse = float(np.sqrt(np.mean((y - y_pred)**2)))
    return coef, r2, rmse, y_pred

c_lin, r2_lin, rmse_lin, yp_lin = fit(X_lin, y, '直接線性')
c_log, r2_log, rmse_log, yp_log = fit(X_log, y, 'Beer-Lambert')

print(f'\n=== 模型 1:cells/mL = a·R + b·G + c·B + d(直接線性)===')
print(f'  係數: a={c_lin[0]:>14,.0f}  b={c_lin[1]:>14,.0f}  c={c_lin[2]:>14,.0f}  d={c_lin[3]:>14,.0f}')
print(f'  R² = {r2_lin:.4f}    RMSE = {rmse_lin:,.0f} cells/mL')

print(f'\n=== 模型 2:cells/mL = a·(-logR) + b·(-logG) + c·(-logB) + d(Beer-Lambert)===')
print(f'  係數: a={c_log[0]:>14,.0f}  b={c_log[1]:>14,.0f}  c={c_log[2]:>14,.0f}  d={c_log[3]:>14,.0f}')
print(f'  R² = {r2_log:.4f}    RMSE = {rmse_log:,.0f} cells/mL')


# ============================================================
#  5. 殘差分析(看哪個比例 outlier)
# ============================================================
print(f'\n=== 殘差(實際 - 預測,負號=高估)===')
print(f'{"比例":<6}{"實際":>12}{"線性預測":>14}{"線性殘差":>14}{"BL 預測":>14}{"BL 殘差":>14}')
for r in RATIOS_TO_USE:
    if r in EXCLUDE_RATIOS or r not in cells_data: continue
    actual = cells_data[r]
    mask = np.array(ratios_per_row) == r
    if not mask.any(): continue
    p1 = yp_lin[mask].mean()
    p2 = yp_log[mask].mean()
    print(f'{r:<6}{actual:>12,}{p1:>14,.0f}{actual-p1:>14,.0f}{p2:>14,.0f}{actual-p2:>14,.0f}')


# ============================================================
#  6. 寫 calibration_data.csv
# ============================================================
with open(OUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['比例', '真實cells/mL', 'R', 'G', 'B',
                '線性預測', 'BL預測', '線性殘差', 'BL殘差'])
    for i in range(len(y)):
        r = ratios_per_row[i]
        actual = int(y[i])
        R, G, B = X_lin[i]
        p1, p2 = yp_lin[i], yp_log[i]
        w.writerow([r, actual, round(R,3), round(G,3), round(B,3),
                    round(p1), round(p2), round(actual-p1), round(actual-p2)])
print(f'\n[OK] CSV: {OUT_CSV}')


# ============================================================
#  7. 給 App.js 的 JS 程式碼(挑 R² 較高的)
# ============================================================
better = ('直接線性', c_lin, r2_lin) if r2_lin >= r2_log else ('Beer-Lambert', c_log, r2_log)
print(f'\n{"=" * 70}')
print(f'  推薦模型:{better[0]}(R² = {better[2]:.4f})')
print(f'{"=" * 70}')
print('\n  把以下 JS 函式貼到 App.js,拍完照後呼叫即可估濃度:\n')

if better[0] == '直接線性':
    print(f'  function predictCellsPerML(ratio) {{')
    print(f'    // ratio = {{r, g, b}} 從 colorRatio() 拿到的色比')
    print(f'    return ({c_lin[0]:.0f}) * ratio.r')
    print(f'         + ({c_lin[1]:.0f}) * ratio.g')
    print(f'         + ({c_lin[2]:.0f}) * ratio.b')
    print(f'         + ({c_lin[3]:.0f});')
    print(f'  }}')
else:
    print(f'  function predictCellsPerML(ratio) {{')
    print(f'    // ratio = {{r, g, b}} 從 colorRatio() 拿到的色比')
    print(f'    const aR = -Math.log10(ratio.r);')
    print(f'    const aG = -Math.log10(ratio.g);')
    print(f'    const aB = -Math.log10(ratio.b);')
    print(f'    return ({c_log[0]:.0f}) * aR')
    print(f'         + ({c_log[1]:.0f}) * aG')
    print(f'         + ({c_log[2]:.0f}) * aB')
    print(f'         + ({c_log[3]:.0f});')
    print(f'  }}')

print(f'\n{"=" * 70}')
