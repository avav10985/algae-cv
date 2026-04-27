# DIY 手機光譜儀 — Public Lab

## 為什麼留這個

我們選了 **🅱️ RGB 色彩分析** 路線(直接用手機相機 RGB 通道,不做光譜儀硬體)做藻類細胞 + 葉綠素濃度估計。

但如果之後 RGB 精度不夠,可以回頭考慮這個 **DIY 光譜儀模組**,加上去得到真正的光譜資料。

## 主要參考

**Public Lab Spectrometer**
- 網址:https://publiclab.org/spectrometry
- 開源的 DIY 光譜儀計畫,完整圖紙、組裝教學、分析軟體
- 用 CD 片當衍射光柵,紙箱遮光殼
- 有他們自家的網頁版分析工具(`Spectral Workbench`)

## 原理摘要

```
光源 → 樣本(燒杯) → CD 衍射光柵 → 手機鏡頭
                       ↑
                 把光分散成彩虹光譜
```

手機拍下「彩虹條紋」後,軟體把它轉成「波長 vs 強度」曲線。

## 葉綠素吸收峰(用光譜儀的話可以精準測)

| 色素 | 主要吸收波長 |
|---|---|
| 葉綠素 a | 430 nm(藍)、663 nm(紅)|
| 葉綠素 b | 460 nm(藍)、645 nm(紅)|

## 標準計算公式(Arnon 1949,實驗室用分光光度計)

```
葉綠素 a (mg/L) = 12.7 × A663 - 2.69 × A645
葉綠素 b (mg/L) = 22.9 × A645 - 4.68 × A663
總葉綠素 (mg/L) = 8.02 × A663 + 20.20 × A645
```
其中 A645、A663 是樣本在 645nm、663nm 的吸光度。

## 我們改用 RGB 的對應關係

手機相機 R/G/B 通道大致對應:
- **R channel**(中心波長 ~610-650 nm)→ 接近葉綠素 a 紅光峰(663 nm)
- **B channel**(中心波長 ~450-490 nm)→ 接近葉綠素 a/b 藍光峰(430-460 nm)
- **G channel**(中心波長 ~520-560 nm)→ 葉綠素吸收較少(綠光)

所以用 R 跟 B 通道的吸光度 + Arnon 公式變體推估,理論上可行。

## 缺點(走光譜儀也躲不掉)

- 手機 sensor 是 **Bayer filter RGB**,不是真正的光譜儀,解析度只有 ~10nm
- 環境光干擾大
- 校正麻煩(每次要對標準光源對位)
- 波長準確度有限

## 何時要回頭考慮 🅰️

如果未來發現 RGB 路線:
1. 對不同光源(日光 vs LED)結果差異太大
2. 對低濃度樣本(<1 mg/L)測不準
3. 葉綠素 a/b 比例分析需要精準波長

可以加 DIY 光譜儀模組(成本約 $5,2-3 小時組裝)。

## 相關資源

- Public Lab 主站:https://publiclab.org/
- Spectral Workbench:https://spectralworkbench.org/
- Beer-Lambert 律 wiki:https://en.wikipedia.org/wiki/Beer%E2%80%93Lambert_law
- Arnon 1949 原論文:Arnon DI (1949). "Copper enzymes in isolated chloroplasts. Polyphenoloxidase in Beta vulgaris." Plant Physiol. 24(1):1-15.
