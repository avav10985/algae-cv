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
#  3. 配成樣本 — 每比例 3 張 RGB 取平均(N = 比例數)
#     避免 pseudo-replication:同一濃度的 3 張不是獨立樣本,
#     當 3 個獨立點塞進迴歸會虛抬 R²。正規做法是取平均。
# ============================================================
X_lin   = []   # 直接 R, G, B(平均後,給 RGB 多變數迴歸用)
X_log   = []   # -log10(R, G, B)(BL 多變數)
X_R     = []   # 只用 R(R-only 單變數)
y       = []
ratios_per_row = []
detail_rows = []  # 每比例 3 張的細節(寫 CSV 用)

for r in RATIOS_TO_USE:
    if r in EXCLUDE_RATIOS or r not in cells_data or r not in phone_data:
        continue
    rows = phone_data[r]
    # 細節:每張存 R/G/B + 真實濃度
    for i, (R0, G0, B0) in enumerate(rows, 1):
        detail_rows.append({
            '類型': 'photo', '比例': r, '張號': i,
            'R': R0, 'G': G0, 'B': B0, '真實cells/mL': cells_data[r],
        })
    # 平均:當 N=6 訓練集
    R = sum(x[0] for x in rows) / len(rows)
    G = sum(x[1] for x in rows) / len(rows)
    B = sum(x[2] for x in rows) / len(rows)
    X_lin.append([R, G, B])
    X_log.append([-np.log10(R), -np.log10(G), -np.log10(B)])
    X_R.append([R])
    y.append(cells_data[r])
    ratios_per_row.append(r)

X_lin = np.array(X_lin)
X_log = np.array(X_log)
X_R   = np.array(X_R)
y     = np.array(y, dtype=float)

print(f'\n=== 訓練集:N = {len(y)} 筆(每比例 3 張取平均)===')


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

c_R,   r2_R,   rmse_R,   yp_R   = fit(X_R,   y, 'R-only')
c_lin, r2_lin, rmse_lin, yp_lin = fit(X_lin, y, 'RGB 直接線性')
c_log, r2_log, rmse_log, yp_log = fit(X_log, y, 'Beer-Lambert')

print(f'\n=== 模型 A:cells/mL = a·R + b(R-only,海報好寫)===')
print(f'  係數: a={c_R[0]:>14,.0f}  b={c_R[1]:>14,.0f}')
print(f'  R² = {r2_R:.4f}    RMSE = {rmse_R:,.0f} cells/mL')

print(f'\n=== 模型 B:cells/mL = a·R + b·G + c·B + d(RGB 直接線性)===')
print(f'  係數: a={c_lin[0]:>14,.0f}  b={c_lin[1]:>14,.0f}  c={c_lin[2]:>14,.0f}  d={c_lin[3]:>14,.0f}')
print(f'  R² = {r2_lin:.4f}    RMSE = {rmse_lin:,.0f} cells/mL')

print(f'\n=== 模型 C:cells/mL = a·(-logR) + b·(-logG) + c·(-logB) + d(Beer-Lambert)===')
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
#  6. 寫 calibration_data.csv(明細 18 筆 + 平均 6 筆 + 模型係數)
# ============================================================
def predict_with(coef, X):
    """X 帶截距套係數出預測值"""
    Xb = np.hstack([X, np.ones((len(X), 1))])
    return Xb @ coef

# 把每張(detail)用模型 A/B/C 算預測
header = ['類型', '比例', '張號', 'R', 'G', 'B',
         '真實cells/mL',
         'A_R-only預測', 'A 殘差',
         'B_RGB預測', 'B 殘差',
         'C_BL預測', 'C 殘差']

with open(OUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(header)

    # === 第 1 區:每張 photo 細節(18 筆)===
    for r in RATIOS_TO_USE:
        if r in EXCLUDE_RATIOS or r not in cells_data or r not in phone_data:
            continue
        rows = phone_data[r]
        actual = cells_data[r]
        for i, (R0, G0, B0) in enumerate(rows, 1):
            pA = c_R[0] * R0 + c_R[1]
            pB = c_lin[0]*R0 + c_lin[1]*G0 + c_lin[2]*B0 + c_lin[3]
            pC = c_log[0]*(-np.log10(R0)) + c_log[1]*(-np.log10(G0)) + c_log[2]*(-np.log10(B0)) + c_log[3]
            w.writerow(['photo', r, i,
                       round(R0,3), round(G0,3), round(B0,3),
                       actual,
                       round(pA), round(actual-pA),
                       round(pB), round(actual-pB),
                       round(pC), round(actual-pC)])

        # === 該比例的平均行(緊接著該濃度 3 張之後)===
        R, G, B = X_lin[ratios_per_row.index(r)]
        idx = ratios_per_row.index(r)
        pA = c_R[0]*R + c_R[1]
        pB = yp_lin[idx]
        pC = yp_log[idx]
        w.writerow(['─avg─', r, '(3張平均)',
                   round(R,3), round(G,3), round(B,3),
                   actual,
                   round(pA), round(actual-pA),
                   round(pB), round(actual-pB),
                   round(pC), round(actual-pC)])
        w.writerow([''] * len(header))   # 空行分隔

    # === 第 2 區:模型係數 + R² ===
    w.writerow(['─' * 8] * len(header))
    w.writerow(['模型', '公式', '', '', '', '', '', 'R²', 'RMSE'])
    w.writerow(['A R-only',
               f'cells/mL = {c_R[0]:,.0f} * R + {c_R[1]:,.0f}',
               '', '', '', '', '', round(r2_R, 4), round(rmse_R)])
    w.writerow(['B RGB 直接',
               f'cells/mL = {c_lin[0]:,.0f}*R + {c_lin[1]:,.0f}*G + {c_lin[2]:,.0f}*B + {c_lin[3]:,.0f}',
               '', '', '', '', '', round(r2_lin, 4), round(rmse_lin)])
    w.writerow(['C BL',
               f'cells/mL = {c_log[0]:,.0f}*(-logR) + {c_log[1]:,.0f}*(-logG) + {c_log[2]:,.0f}*(-logB) + {c_log[3]:,.0f}',
               '', '', '', '', '', round(r2_log, 4), round(rmse_log)])

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
