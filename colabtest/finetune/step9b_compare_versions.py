"""
Step 9b: 重測前(step6 原版)vs 重測後(step8 sensitive)兩個版本的校準對比

輸出 2 個 CSV:
  calibration_step6.csv          ← 重測前(step6 原版計數)
  calibration_step8sensitive.csv ← 重測後(step8 sensitive 計數)

每個 CSV 都跑同樣的 3 種模型(R-only、RGB 直接、BL),
所以可以對比「同一份手機色比資料,搭配不同的 cells/mL ground truth」迴歸出來差多少。

用法:
  python colabtest/finetune/step9b_compare_versions.py
"""
import os, glob, csv, re, sys
import numpy as np
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

DATA_FOLDER = r'd:\algae-cv\algae_app\drive-download-20260506T195732Z-3-001'
APP_PHOTOS  = r'd:\algae-cv\algae_app\app拍照\0504'
RATIOS = [1, 3, 5, 8, 9, 10]


def read_final(path):
    if not os.path.exists(path): return None
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r.get('位置','').startswith('⭐'):
                v = r['最終濃度_cells_per_mL']
                return int(v) if v else None


def fit(X, y):
    Xb = np.hstack([X, np.ones((len(X), 1))])
    coef = np.linalg.lstsq(Xb, y, rcond=None)[0]
    pred = Xb @ coef
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
    rmse = np.sqrt(np.mean((y - pred) ** 2))
    return coef, r2, rmse, pred


# --- 讀手機色比(共用,跟 step9 一樣)---
photos = sorted(glob.glob(os.path.join(APP_PHOTOS, '*.jpg')))
phone = {}
for i, p in enumerate(photos):
    ratio = (i // 3) + 1
    if ratio not in RATIOS: continue
    m = re.search(r'_R(\d{3})G(\d{3})B(\d{3})', os.path.basename(p))
    if m:
        phone.setdefault(ratio, []).append(tuple(int(g)/100 for g in m.groups()))


def write_csv(version_name, get_path_fn, out_csv):
    """version_name = 'step6' 或 'step8sensitive';get_path_fn(ratio) → CSV 路徑"""
    cells_data = {r: read_final(get_path_fn(r)) for r in RATIOS}

    # 配對 + 算平均
    X_R, X_lin, X_log, y, ratios_idx = [], [], [], [], []
    for r in RATIOS:
        if cells_data[r] is None or r not in phone: continue
        rows = phone[r]
        R = sum(x[0] for x in rows) / len(rows)
        G = sum(x[1] for x in rows) / len(rows)
        B = sum(x[2] for x in rows) / len(rows)
        X_R.append([R]); X_lin.append([R, G, B])
        X_log.append([-np.log10(R), -np.log10(G), -np.log10(B)])
        y.append(cells_data[r])
        ratios_idx.append(r)

    X_R = np.array(X_R); X_lin = np.array(X_lin); X_log = np.array(X_log)
    y = np.array(y, dtype=float)

    c_R, r2_R, rmse_R, _ = fit(X_R, y)
    c_lin, r2_lin, rmse_lin, _ = fit(X_lin, y)
    c_log, r2_log, rmse_log, _ = fit(X_log, y)

    print(f'\n=== {version_name} ===')
    print(f'  N = {len(y)}')
    for label, c, r2, rmse in [
        ('A R-only',  c_R, r2_R, rmse_R),
        ('B RGB',     c_lin, r2_lin, rmse_lin),
        ('C BL',      c_log, r2_log, rmse_log),
    ]:
        print(f'  {label:<12} R²={r2:.4f}  RMSE={rmse:>8,.0f}')

    # 寫 CSV
    header = ['類型', '比例', '張號', 'R', 'G', 'B',
              '真實cells/mL',
              'A_R-only預測', 'A 殘差',
              'B_RGB預測', 'B 殘差',
              'C_BL預測', 'C 殘差']
    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow([f'# 校準版本: {version_name}'])
        w.writerow(header)
        for r in RATIOS:
            if cells_data[r] is None: continue
            rows = phone[r]; actual = cells_data[r]
            for i, (R0, G0, B0) in enumerate(rows, 1):
                pA = c_R[0]*R0 + c_R[1]
                pB = c_lin[0]*R0 + c_lin[1]*G0 + c_lin[2]*B0 + c_lin[3]
                pC = c_log[0]*(-np.log10(R0)) + c_log[1]*(-np.log10(G0)) + c_log[2]*(-np.log10(B0)) + c_log[3]
                w.writerow(['photo', r, i, round(R0,3), round(G0,3), round(B0,3),
                            actual, round(pA), round(actual-pA),
                            round(pB), round(actual-pB),
                            round(pC), round(actual-pC)])
            R = sum(x[0] for x in rows)/len(rows)
            G = sum(x[1] for x in rows)/len(rows)
            B = sum(x[2] for x in rows)/len(rows)
            pA = c_R[0]*R + c_R[1]
            pB = c_lin[0]*R + c_lin[1]*G + c_lin[2]*B + c_lin[3]
            pC = c_log[0]*(-np.log10(R)) + c_log[1]*(-np.log10(G)) + c_log[2]*(-np.log10(B)) + c_log[3]
            w.writerow(['─avg─', r, '(3張平均)', round(R,3), round(G,3), round(B,3),
                        actual, round(pA), round(actual-pA),
                        round(pB), round(actual-pB),
                        round(pC), round(actual-pC)])
            w.writerow([''] * len(header))

        w.writerow(['─'*8] * len(header))
        w.writerow(['模型', '公式', '', '', '', '', '', 'R²', 'RMSE'])
        w.writerow(['A R-only', f'cells/mL = {c_R[0]:,.0f}*R + {c_R[1]:,.0f}',
                    '', '', '', '', '', round(r2_R, 4), round(rmse_R)])
        w.writerow(['B RGB', f'cells/mL = {c_lin[0]:,.0f}*R + {c_lin[1]:,.0f}*G + {c_lin[2]:,.0f}*B + {c_lin[3]:,.0f}',
                    '', '', '', '', '', round(r2_lin, 4), round(rmse_lin)])
        w.writerow(['C BL', f'cells/mL = {c_log[0]:,.0f}*(-logR) + {c_log[1]:,.0f}*(-logG) + {c_log[2]:,.0f}*(-logB) + {c_log[3]:,.0f}',
                    '', '', '', '', '', round(r2_log, 4), round(rmse_log)])

    print(f'  → {out_csv}')


# 重測前(step6 原版)
write_csv('step6 重測前',
          lambda r: f'{DATA_FOLDER}/{r}/results/cell_counts.csv',
          r'd:\algae-cv\calibration_step6.csv')

# 重測後(step8 sensitive)
write_csv('step8 sensitive 重測後',
          lambda r: f'{DATA_FOLDER}/{r}/results_sensitive/cell_counts_sensitive.csv',
          r'd:\algae-cv\calibration_step8sensitive.csv')

print('\n[OK] 兩個 CSV 都產出來了')
