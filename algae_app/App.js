import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  Image,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import {
  Camera,
  useCameraDevice,
  useCameraPermission,
} from 'react-native-vision-camera';
import * as FileSystem from 'expo-file-system/legacy';
import * as MediaLibrary from 'expo-media-library';
import * as ImageManipulator from 'expo-image-manipulator';
import jpeg from 'jpeg-js';

const ALBUM_NAME = 'algae_app';

// ROI 框基礎參數(實際 h 在 runtime 依螢幕比例算,以求像素真正正方形)
const BEAKER_W = 0.30;        // 燒杯框寬度(螢幕比例)
const WHITECARD_W = 0.30;     // 白卡框寬度
const WHITECARD_TALL = 1.5;   // 白卡高度倍率(1.0=正方形, 1.5=垂直長方形)
const BOTTOM_Y = 0.83;        // 兩框底部對齊線
const BEAKER_X = 0.12;
const WHITECARD_X = 0.63;

function nowTimestamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}`;
}

// 色比 + 估計濃度 + OD 寫進檔名
// 例如 photo_..._R045G062B038_CR0480123_CM0492011_O0857.jpg
//   R/G/B  色比 ×100(3 位)
//   CR     R-only 模型估計 cells/mL(7 位零墊)
//   CM     Multi (RGB) 模型估計 cells/mL(7 位零墊)
//   O      OD630 ×1000(4 位零墊,例 0287 = 0.287)
function makeFilename(ts, beakerRGB, whiteRGB) {
  const base = `photo_${ts}`;
  if (!beakerRGB || !whiteRGB) return `${base}.jpg`;
  const ratio = colorRatio(beakerRGB, whiteRGB);
  const pad3 = (n) => String(Math.min(999, Math.max(0, Math.round(n * 100)))).padStart(3, '0');
  const pad7 = (n) => String(Math.min(9999999, Math.max(0, n))).padStart(7, '0');
  const pad4 = (n) => String(Math.min(9999, Math.max(0, Math.round(n * 1000)))).padStart(4, '0');
  const cR = predictCellsPerML_R(ratio);
  const cM = predictCellsPerML_RGB(ratio);
  const od = predictOD630(ratio);
  const tagR = cR != null ? `_CR${pad7(cR)}` : '';
  const tagM = cM != null ? `_CM${pad7(cM)}` : '';
  const tagO = od != null ? `_O${pad4(od)}` : '';
  return `${base}_R${pad3(ratio.r)}G${pad3(ratio.g)}B${pad3(ratio.b)}${tagR}${tagM}${tagO}.jpg`;
}

// 算「色比」= 燒杯RGB / 白卡RGB,這個比例對光照變化不敏感,可當濃度指標
function colorRatio(beaker, white) {
  if (!beaker || !white) return null;
  const safe = (n) => Math.max(n, 1);
  return {
    r: beaker.r / safe(white.r),
    g: beaker.g / safe(white.g),
    b: beaker.b / safe(white.b),
  };
}

// 從色比估算 cells/mL — 兩種線性迴歸並行,讓檔名同時記錄兩個估計值
// 校準資料:6 個稀釋(全 step8 sensitive)× 每比例 3 張取平均 = N=6
// 訓練日期 2026-05-04,小球藻;換樣本 / 換手機 → 重跑 step9_calibration.py 換係數

// 模型 A:只用紅光(Beer-Lambert 紅光單變數,海報好講)
// R² = 0.9862  RMSE ~ 3,137 cells/mL
// 註:係數來自舊體積常數(25 張=1 μL)迴歸後 ÷10,對應新體積(25 張=10 μL)
function predictCellsPerML_R(ratio) {
  if (!ratio) return null;
  const r = Math.max(0.01, Math.min(1.0, ratio.r));
  const cells = (-144133) * r + 115754;
  return Math.max(0, Math.round(cells));
}

// 模型 B:三變數直接線性(R+G+B,精度略高)
// R² = 0.9919  RMSE ~ 2,4xx cells/mL
// 註:係數來自舊體積常數(25 張=1 μL)迴歸後 ÷10,對應新體積(25 張=10 μL)
function predictCellsPerML_RGB(ratio) {
  if (!ratio) return null;
  const clip = (n) => Math.max(0.01, Math.min(1.0, n));
  const cells = 187108 * clip(ratio.r)
              + (-165821) * clip(ratio.g)
              + (-219701) * clip(ratio.b)
              + 155749;
  return Math.max(0, Math.round(cells));
}

// === OD 預測(色比 → 分光光度計吸光值)===
// 校準資料:0504 + 0506 兩天合併,每比例 3 張取平均(R² 詳見下方)
// G 通道為主要預測子(藻反射綠光,動態範圍最線性)
function _odLinear(ratio, aR, aG, aB, d) {
  if (!ratio) return null;
  const c = (n) => Math.max(0.01, Math.min(1.0, n));
  return Math.max(0, aR * c(ratio.r) + aG * c(ratio.g) + aB * c(ratio.b) + d);
}
// OD630(N=20,R²=0.977)
function predictOD630(ratio) { return _odLinear(ratio,  1.9327, -2.4670, -2.0551,  2.2357); }
// OD647(N=20,R²=0.976)— 葉綠素 b 吸收
function predictOD647(ratio) { return _odLinear(ratio,  2.0620, -2.5132, -2.1233,  2.2189); }
// OD664(N=10,R²=0.993)— 葉綠素 a 吸收峰
function predictOD664(ratio) { return _odLinear(ratio,  0.7424, -2.4442, -0.9197,  2.4060); }
// OD750(N=10,R²=0.991)— 近紅外,反映混濁度
function predictOD750(ratio) { return _odLinear(ratio,  0.7361, -2.4088, -0.7677,  2.2804); }

// 葉綠素 a / b 濃度(Lichtenthaler 1987,80% 丙酮萃取係數,單位 μg/mL)
//   Chl-a = 12.25·OD664 − 2.85·OD647
//   Chl-b = 20.31·OD647 − 4.91·OD664
//   Total = Chl-a + Chl-b
// 注意:這組係數假設「丙酮萃取後讀 OD」;直接拍燒杯不萃取也可估個大概,
// 但絕對值會偏離真實植物萃取液數字,主要看「相對變化」就夠用。
function predictChlorophyllA(ratio) {
  const od664 = predictOD664(ratio);
  const od647 = predictOD647(ratio);
  if (od664 == null || od647 == null) return null;
  return Math.max(0, 12.25 * od664 - 2.85 * od647);
}
function predictChlorophyllB(ratio) {
  const od664 = predictOD664(ratio);
  const od647 = predictOD647(ratio);
  if (od664 == null || od647 == null) return null;
  return Math.max(0, 20.31 * od647 - 4.91 * od664);
}
function predictChlorophyllTotal(ratio) {
  const a = predictChlorophyllA(ratio);
  const b = predictChlorophyllB(ratio);
  if (a == null || b == null) return null;
  return a + b;
}

// 從檔名解出所有資料(不用碰 EXIF / DB,單純 regex 解析)
// 對應 makeFilename:photo_<ts>_R<3>G<3>B<3>_CR<7>_CM<7>_O<4>.jpg
function parseFilename(filename) {
  const m = filename.match(
    /^photo_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_R(\d{3})G(\d{3})B(\d{3})(?:_CR(\d{7}))?(?:_CM(\d{7}))?(?:_O(\d{4}))?\.jpg$/
  );
  if (!m) return null;
  const ratio = { r: parseInt(m[2]) / 100, g: parseInt(m[3]) / 100, b: parseInt(m[4]) / 100 };
  return {
    filename,
    ts: m[1].replace('_', ' ').replace(/-/g, (x, i) => (i === 10 || i === 13 ? ':' : '-')),
    ratio,
    cellsR: m[5] ? parseInt(m[5]) : null,
    cellsRGB: m[6] ? parseInt(m[6]) : null,
    od630: m[7] ? parseInt(m[7]) / 1000 : null,
    // 衍生指標(現算,因為舊檔可能沒包這些)
    od664: predictOD664(ratio),
    chla: predictChlorophyllA(ratio),
    chlb: predictChlorophyllB(ratio),
  };
}

function formatCells(n) {
  if (n == null) return '—';
  // 1,234,567 千分位逗號;太大用科學記號
  if (n >= 10_000_000) return n.toExponential(2).replace('e+', '×10^');
  return n.toLocaleString('en-US');
}

async function getActualSize(uri) {
  const meta = await ImageManipulator.manipulateAsync(uri, [], { base64: false });
  return { width: meta.width, height: meta.height };
}

// 把螢幕 frac 座標 → 照片 frac 座標 (vision-camera 預設 resizeMode='cover')
function screenFracToPhotoFrac(frac, screenAspect, photoAspect) {
  if (photoAspect > screenAspect) {
    // 照片相對螢幕更寬 → 左右各被裁
    const visibleW = screenAspect / photoAspect;
    const visibleX = (1 - visibleW) / 2;
    return {
      x: visibleX + frac.x * visibleW,
      y: frac.y,
      w: frac.w * visibleW,
      h: frac.h,
    };
  } else {
    // 照片相對螢幕更高 → 上下各被裁
    const visibleH = photoAspect / screenAspect;
    const visibleY = (1 - visibleH) / 2;
    return {
      x: frac.x,
      y: visibleY + frac.y * visibleH,
      w: frac.w,
      h: frac.h * visibleH,
    };
  }
}

async function extractAvgRGB(uri, photoW, photoH, frac, label) {
  const originX = Math.max(0, Math.min(Math.round(frac.x * photoW), photoW - 1));
  const originY = Math.max(0, Math.min(Math.round(frac.y * photoH), photoH - 1));
  const width = Math.max(1, Math.min(Math.round(frac.w * photoW), photoW - originX));
  const height = Math.max(1, Math.min(Math.round(frac.h * photoH), photoH - originY));
  const crop = { originX, originY, width, height };
  console.log(`[${label}] bitmap=${photoW}x${photoH}, crop=`, crop);
  try {
    const cropped = await ImageManipulator.manipulateAsync(
      uri,
      [{ crop }, { resize: { width: 16, height: 16 } }],
      {
        format: ImageManipulator.SaveFormat.JPEG,
        base64: true,
        compress: 0.95,
      }
    );
    console.log(`[${label}] cropped=${cropped.width}x${cropped.height}, b64 len=${cropped.base64?.length}`);
    const bin = atob(cropped.base64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const decoded = jpeg.decode(arr, { useTArray: true });
    const data = decoded.data;
    let r = 0, g = 0, b = 0;
    const pix = data.length / 4;
    for (let i = 0; i < data.length; i += 4) {
      r += data[i];
      g += data[i + 1];
      b += data[i + 2];
    }
    const result = {
      r: Math.round(r / pix),
      g: Math.round(g / pix),
      b: Math.round(b / pix),
    };
    console.log(`[${label}] RGB =`, result);
    return result;
  } catch (e) {
    console.error(`[${label}] extract failed:`, e?.message ?? String(e));
    return null;
  }
}

async function saveToAlbum(uri) {
  try {
    const asset = await MediaLibrary.createAssetAsync(uri);
    const album = await MediaLibrary.getAlbumAsync(ALBUM_NAME);
    if (album == null) {
      await MediaLibrary.createAlbumAsync(ALBUM_NAME, asset, false);
    } else {
      await MediaLibrary.addAssetsToAlbumAsync([asset], album, false);
    }
    return true;
  } catch {
    return false;
  }
}

export default function App() {
  const [screen, setScreen] = useState('home');
  if (screen === 'camera') return <CameraScreen onBack={() => setScreen('home')} />;
  if (screen === 'history') return <HistoryScreen onBack={() => setScreen('home')} />;
  return (
    <HomeScreen
      onStartCamera={() => setScreen('camera')}
      onOpenHistory={() => setScreen('history')}
    />
  );
}

function HomeScreen({ onStartCamera, onOpenHistory }) {
  return (
    <View style={styles.homeRoot}>
      <View style={styles.homeTop}>
        <Text style={styles.homeTitle}>algae-cv</Text>
        <Text style={styles.homeSubtitle}>藻類比色 · 顏色 → 濃度估計</Text>
      </View>

      <View style={{ gap: 14 }}>
        <TouchableOpacity
          style={styles.bigBtn}
          onPress={onStartCamera}
          activeOpacity={0.85}
        >
          <Text style={styles.bigBtnIcon}>📸</Text>
          <Text style={styles.bigBtnText}>進入相機</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.bigBtn, styles.bigBtnSecondary]}
          onPress={onOpenHistory}
          activeOpacity={0.85}
        >
          <Text style={styles.bigBtnIcon}>📋</Text>
          <Text style={styles.bigBtnText}>歷史紀錄</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.homeHint}>
        <Text style={styles.hintTitle}>使用方式</Text>
        <Text style={styles.hintText}>① 燒杯放綠框內</Text>
        <Text style={styles.hintText}>② 白紙 / 白卡放黃框內</Text>
        <Text style={styles.hintText}>③ 按快門 → 自動存相簿 + 顯示 RGB</Text>
      </View>

      <StatusBar style="dark" />
    </View>
  );
}

function CameraScreen({ onBack }) {
  const { hasPermission, requestPermission } = useCameraPermission();
  const device = useCameraDevice('back');
  const cameraRef = useRef(null);
  const win = useWindowDimensions();
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null);
  const [focusPoint, setFocusPoint] = useState(null);

  const handleFocus = useCallback(async (event) => {
    if (!cameraRef.current) return;
    const { locationX, locationY } = event.nativeEvent;
    setFocusPoint({ x: locationX, y: locationY });
    try {
      await cameraRef.current.focus({ x: locationX, y: locationY });
      console.log(`焦點鎖定 @ ${locationX.toFixed(0)}, ${locationY.toFixed(0)}`);
    } catch (e) {
      console.error('focus failed:', e?.message ?? String(e));
    }
    setTimeout(() => setFocusPoint(null), 1500);
  }, []);

  // 把 width 比例轉成 height 比例,使框在螢幕「像素上」是正方形
  const squareH = (wFrac) => wFrac * (win.width / win.height);
  const beakerH = squareH(BEAKER_W);
  const whiteH = squareH(WHITECARD_W) * WHITECARD_TALL;
  const BEAKER_FRAC = { x: BEAKER_X, y: BOTTOM_Y - beakerH, w: BEAKER_W, h: beakerH };
  const WHITECARD_FRAC = { x: WHITECARD_X, y: BOTTOM_Y - whiteH, w: WHITECARD_W, h: whiteH };

  useEffect(() => {
    if (!hasPermission) requestPermission();
    MediaLibrary.requestPermissionsAsync();
  }, [hasPermission, requestPermission]);

  const capture = useCallback(async () => {
    if (!cameraRef.current || busy) return;
    setBusy(true);
    try {
      const photo = await cameraRef.current.takePhoto({
        flash: 'off',
        enableShutterSound: false,
      });
      const ts = nowTimestamp();
      const tempName = `temp_${ts}.jpg`;
      console.log(`=== capture ===`);
      const tempDest = `${FileSystem.documentDirectory}${tempName}`;
      const src = photo.path.startsWith('file://')
        ? photo.path
        : `file://${photo.path}`;
      await FileSystem.copyAsync({ from: src, to: tempDest });

      setLast({
        uri: null,
        name: '處理中...',
        beaker: null,
        white: null,
        albumOk: null,
        processing: true,
      });

      const { width: actualW, height: actualH } = await getActualSize(tempDest);
      const screenAspect = win.width / win.height;
      const photoAspect = actualW / actualH;
      console.log(`screen ${win.width}x${win.height} (aspect ${screenAspect.toFixed(3)}), photo ${actualW}x${actualH} (aspect ${photoAspect.toFixed(3)})`);
      const beakerMapped = screenFracToPhotoFrac(BEAKER_FRAC, screenAspect, photoAspect);
      const whiteMapped = screenFracToPhotoFrac(WHITECARD_FRAC, screenAspect, photoAspect);
      const beakerRGB = await extractAvgRGB(tempDest, actualW, actualH, beakerMapped, '燒杯');
      const whiteRGB = await extractAvgRGB(tempDest, actualW, actualH, whiteMapped, '白卡');

      // 把色比寫進最終檔名,然後改名 + 存相簿
      const finalName = makeFilename(ts, beakerRGB, whiteRGB);
      const finalDest = `${FileSystem.documentDirectory}${finalName}`;
      await FileSystem.moveAsync({ from: tempDest, to: finalDest });
      const albumOk = await saveToAlbum(finalDest);
      console.log(`saved as ${finalName}`);

      setLast({
        uri: finalDest,
        name: finalName,
        beaker: beakerRGB,
        white: whiteRGB,
        albumOk,
        processing: false,
      });

      try {
        await FileSystem.deleteAsync(src, { idempotent: true });
      } catch {}
    } catch (e) {
      Alert.alert('拍照失敗', String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }, [busy, win]);

  if (!hasPermission) {
    return (
      <View style={styles.center}>
        <Text style={styles.message}>需要相機權限才能拍照</Text>
        <TouchableOpacity onPress={requestPermission} style={styles.permBtn}>
          <Text>授權相機</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={onBack} style={[styles.permBtn, styles.permBtnSecondary]}>
          <Text style={{ color: 'white' }}>返回首頁</Text>
        </TouchableOpacity>
        <StatusBar style="light" />
      </View>
    );
  }

  if (!device) {
    return (
      <View style={styles.center}>
        <Text style={styles.message}>找不到後鏡頭</Text>
        <TouchableOpacity onPress={onBack} style={[styles.permBtn, styles.permBtnSecondary]}>
          <Text style={{ color: 'white' }}>返回首頁</Text>
        </TouchableOpacity>
        <StatusBar style="light" />
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <Camera
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={true}
        photo={true}
      />

      <Pressable style={StyleSheet.absoluteFill} onPress={handleFocus} />

      {focusPoint && (
        <View
          pointerEvents="none"
          style={[
            styles.focusIndicator,
            { left: focusPoint.x - 30, top: focusPoint.y - 30 },
          ]}
        />
      )}

      <TouchableOpacity
        style={styles.backBtn}
        onPress={onBack}
        activeOpacity={0.7}
      >
        <Text style={styles.backBtnText}>← 返回</Text>
      </TouchableOpacity>

      <View pointerEvents="none" style={[styles.overlay, fracToStyle(BEAKER_FRAC)]}>
        <View style={[styles.roiBox, { borderColor: '#00ff66' }]} />
        <Text style={[styles.roiLabel, { backgroundColor: 'rgba(0,80,30,0.75)' }]}>燒杯</Text>
      </View>

      <View pointerEvents="none" style={[styles.overlay, fracToStyle(WHITECARD_FRAC)]}>
        <View style={[styles.roiBox, { borderColor: '#ffff00' }]} />
        <Text style={[styles.roiLabel, { backgroundColor: 'rgba(80,80,0,0.75)' }]}>白卡</Text>
      </View>

      <View style={styles.controls}>
        <TouchableOpacity
          onPress={capture}
          disabled={busy}
          activeOpacity={0.7}
          style={[styles.shutter, busy && styles.shutterBusy]}
        >
          <View style={styles.shutterInner} />
        </TouchableOpacity>
      </View>

      {last && (
        <View style={styles.infoPanel}>
          <Image source={{ uri: last.uri }} style={styles.previewImg} />
          <View style={styles.infoText}>
            <Text style={styles.infoName} numberOfLines={1}>
              {last.name}
            </Text>
            <Text style={styles.infoLine}>
              {last.processing
                ? '📁 儲存中...'
                : last.albumOk
                ? '📁 已存到「algae_app」相簿'
                : '📁 已存 app 內(相簿失敗)'}
            </Text>
            {last.processing ? (
              <Text style={styles.infoLine}>🔬 RGB 計算中...</Text>
            ) : (
              <>
                <Text style={[styles.infoLine, { color: '#ffff66' }]}>
                  白卡: {last.white ? `(${last.white.r}, ${last.white.g}, ${last.white.b})` : '失敗'}
                </Text>
                <Text style={[styles.infoLine, { color: '#66ff99' }]}>
                  燒杯: {last.beaker ? `(${last.beaker.r}, ${last.beaker.g}, ${last.beaker.b})` : '失敗'}
                </Text>
                {(() => {
                  const ratio = colorRatio(last.beaker, last.white);
                  if (!ratio) return null;
                  const cR = predictCellsPerML_R(ratio);
                  const cM = predictCellsPerML_RGB(ratio);
                  const od630 = predictOD630(ratio);
                  const od664 = predictOD664(ratio);
                  const chla = predictChlorophyllA(ratio);
                  const chlb = predictChlorophyllB(ratio);
                  return (
                    <>
                      <Text style={[styles.infoLine, styles.ratioLine]}>
                        🎯 色比 R:{ratio.r.toFixed(2)}  G:{ratio.g.toFixed(2)}  B:{ratio.b.toFixed(2)}
                      </Text>
                      <Text style={[styles.infoLine, styles.cellsLine]}>
                        🦠 cells/mL  R:{formatCells(cR)}  RGB:{formatCells(cM)}
                      </Text>
                      <Text style={[styles.infoLine, styles.odLine]}>
                        🌈 OD630 {od630.toFixed(2)}  OD664 {od664.toFixed(2)}
                      </Text>
                      <Text style={[styles.infoLine, styles.chlaLine]}>
                        🍃 Chl-a {chla.toFixed(1)}  Chl-b {chlb.toFixed(1)} μg/mL
                      </Text>
                    </>
                  );
                })()}
              </>
            )}
          </View>
        </View>
      )}

      <StatusBar style="light" />
    </View>
  );
}

// ==========================================================================
//  歷史紀錄畫面:列出 documentDirectory 裡所有 photo_*.jpg,從檔名解出資料
// ==========================================================================
function HistoryScreen({ onBack }) {
  const [photos, setPhotos] = useState([]);
  const [sortBy, setSortBy] = useState('time');  // 'time' | 'cells'
  const [selected, setSelected] = useState(null); // for full screen modal
  const [loading, setLoading] = useState(true);

  const loadPhotos = useCallback(async () => {
    setLoading(true);
    try {
      const files = await FileSystem.readDirectoryAsync(FileSystem.documentDirectory);
      const parsed = files
        .filter((f) => f.startsWith('photo_') && f.endsWith('.jpg'))
        .map((f) => {
          const data = parseFilename(f);
          if (!data) return null;
          return { ...data, uri: FileSystem.documentDirectory + f };
        })
        .filter(Boolean);
      setPhotos(parsed);
    } catch (e) {
      console.error('list photos failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadPhotos(); }, [loadPhotos]);

  const sorted = [...photos].sort((a, b) => {
    if (sortBy === 'cells') {
      return (b.cellsRGB ?? 0) - (a.cellsRGB ?? 0);
    }
    return b.filename.localeCompare(a.filename);  // 新到舊
  });

  const handleDelete = async (item) => {
    Alert.alert('刪除這張?', item.filename, [
      { text: '取消', style: 'cancel' },
      {
        text: '刪除',
        style: 'destructive',
        onPress: async () => {
          try {
            await FileSystem.deleteAsync(item.uri, { idempotent: true });
            setSelected(null);
            loadPhotos();
          } catch (e) {
            Alert.alert('刪除失敗', String(e?.message ?? e));
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.historyRoot}>
      <View style={styles.historyHeader}>
        <TouchableOpacity onPress={onBack} style={styles.historyBack}>
          <Text style={styles.historyBackText}>← 返回</Text>
        </TouchableOpacity>
        <Text style={styles.historyTitle}>歷史紀錄 ({photos.length})</Text>
        <TouchableOpacity
          style={styles.sortBtn}
          onPress={() => setSortBy(sortBy === 'time' ? 'cells' : 'time')}
        >
          <Text style={styles.sortBtnText}>
            {sortBy === 'time' ? '⏱ 時間' : '🔢 濃度'}
          </Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.center}>
          <Text>載入中...</Text>
        </View>
      ) : photos.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyText}>還沒有照片</Text>
          <Text style={styles.emptyHint}>回首頁按「進入相機」拍幾張就會出現</Text>
        </View>
      ) : (
        <FlatList
          data={sorted}
          keyExtractor={(item) => item.filename}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={styles.histItem}
              onPress={() => setSelected(item)}
              activeOpacity={0.7}
            >
              <Image source={{ uri: item.uri }} style={styles.histThumb} />
              <View style={styles.histText}>
                <Text style={styles.histTime}>{item.ts}</Text>
                <Text style={styles.histRatio}>
                  R:{item.ratio.r.toFixed(2)} G:{item.ratio.g.toFixed(2)} B:{item.ratio.b.toFixed(2)}
                </Text>
                <Text style={styles.histCells}>
                  🦠 {formatCells(item.cellsRGB ?? item.cellsR)} cells/mL
                </Text>
                <Text style={styles.histOd}>
                  🌈 OD630 {item.od630?.toFixed(2) ?? '—'}  🍃 Chl-a {item.chla?.toFixed(1) ?? '—'}
                </Text>
              </View>
            </TouchableOpacity>
          )}
          contentContainerStyle={{ paddingVertical: 8 }}
        />
      )}

      {/* 全螢幕詳細 Modal */}
      <Modal visible={selected != null} animationType="slide" onRequestClose={() => setSelected(null)}>
        {selected && (
          <View style={styles.detailRoot}>
            <View style={styles.detailHeader}>
              <TouchableOpacity onPress={() => setSelected(null)} style={styles.historyBack}>
                <Text style={styles.historyBackText}>← 關閉</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => handleDelete(selected)} style={styles.deleteBtn}>
                <Text style={styles.deleteBtnText}>🗑 刪除</Text>
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={styles.detailScroll}>
              <Image source={{ uri: selected.uri }} style={styles.detailImg} resizeMode="contain" />
              <Text style={styles.detailFilename}>{selected.filename}</Text>
              <Text style={styles.detailLine}>📅 {selected.ts}</Text>
              <View style={styles.detailDivider} />
              <Text style={styles.detailSection}>色比</Text>
              <Text style={styles.detailRow}>R:  {selected.ratio.r.toFixed(3)}</Text>
              <Text style={styles.detailRow}>G:  {selected.ratio.g.toFixed(3)}</Text>
              <Text style={styles.detailRow}>B:  {selected.ratio.b.toFixed(3)}</Text>
              <View style={styles.detailDivider} />
              <Text style={styles.detailSection}>cells/mL 預測</Text>
              <Text style={styles.detailRow}>R-only:   {formatCells(selected.cellsR)}</Text>
              <Text style={styles.detailRow}>RGB:      {formatCells(selected.cellsRGB)}</Text>
              <View style={styles.detailDivider} />
              <Text style={styles.detailSection}>OD 預測</Text>
              <Text style={styles.detailRow}>OD630:  {selected.od630?.toFixed(3) ?? '—'}</Text>
              <Text style={styles.detailRow}>OD664:  {selected.od664?.toFixed(3) ?? '—'}</Text>
              <View style={styles.detailDivider} />
              <Text style={styles.detailSection}>葉綠素</Text>
              <Text style={styles.detailRow}>Chl-a:  {selected.chla?.toFixed(2) ?? '—'} μg/mL</Text>
              <Text style={styles.detailRow}>Chl-b:  {selected.chlb?.toFixed(2) ?? '—'} μg/mL</Text>
            </ScrollView>
          </View>
        )}
      </Modal>

      <StatusBar style="dark" />
    </View>
  );
}


function fracToStyle(frac) {
  return {
    left: `${frac.x * 100}%`,
    top: `${frac.y * 100}%`,
    width: `${frac.w * 100}%`,
    height: `${frac.h * 100}%`,
  };
}

const styles = StyleSheet.create({
  // 首頁
  homeRoot: {
    flex: 1,
    backgroundColor: '#f5f7f9',
    padding: 24,
    justifyContent: 'space-between',
  },
  homeTop: {
    marginTop: 80,
    alignItems: 'center',
  },
  homeTitle: {
    fontSize: 42,
    fontWeight: '800',
    color: '#1d4d3a',
  },
  homeSubtitle: {
    fontSize: 13,
    color: '#666',
    marginTop: 6,
  },
  bigBtn: {
    backgroundColor: '#00b07a',
    borderRadius: 16,
    paddingVertical: 28,
    paddingHorizontal: 32,
    alignItems: 'center',
    elevation: 4,
    shadowColor: '#00b07a',
    shadowOpacity: 0.3,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
  },
  bigBtnSecondary: {
    backgroundColor: '#0f8b6e',
    shadowColor: '#0f8b6e',
  },
  bigBtnIcon: {
    fontSize: 36,
  },
  bigBtnText: {
    fontSize: 22,
    fontWeight: '700',
    color: 'white',
    marginTop: 4,
  },
  homeHint: {
    backgroundColor: 'white',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
  },
  hintTitle: {
    fontSize: 12,
    color: '#999',
    marginBottom: 8,
    fontWeight: '600',
  },
  hintText: {
    fontSize: 13,
    color: '#333',
    marginVertical: 2,
  },

  // 相機
  root: { flex: 1, backgroundColor: 'black' },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'black',
    padding: 20,
  },
  message: { color: 'white', fontSize: 16, marginBottom: 12 },
  permBtn: {
    backgroundColor: 'white',
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 4,
  },
  permBtnSecondary: {
    backgroundColor: '#666',
    marginTop: 12,
  },
  backBtn: {
    position: 'absolute',
    top: 50,
    left: 12,
    backgroundColor: 'rgba(0,0,0,0.6)',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 6,
    zIndex: 10,
  },
  focusIndicator: {
    position: 'absolute',
    width: 60,
    height: 60,
    borderRadius: 30,
    borderWidth: 2,
    borderColor: '#ffffff',
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  backBtnText: {
    color: 'white',
    fontSize: 14,
    fontWeight: '600',
  },
  overlay: {
    position: 'absolute',
  },
  roiBox: {
    flex: 1,
    borderWidth: 2,
    borderRadius: 4,
  },
  roiLabel: {
    position: 'absolute',
    top: -22,
    left: 0,
    color: 'white',
    fontSize: 12,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 2,
  },
  ratioLine: {
    color: '#ffaa00',
    fontWeight: '700',
    marginTop: 4,
    paddingTop: 4,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.2)',
  },
  cellsLine: {
    color: '#00ddaa',
    fontWeight: '800',
    fontSize: 13,
    marginTop: 2,
  },
  odLine: {
    color: '#7ec0ff',
    fontWeight: '700',
    fontSize: 12,
    marginTop: 3,
  },
  chlaLine: {
    color: '#a8ff66',
    fontWeight: '800',
    fontSize: 12,
    marginTop: 1,
  },
  controls: {
    position: 'absolute',
    bottom: 30,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  shutter: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 4,
    borderColor: 'white',
    justifyContent: 'center',
    alignItems: 'center',
  },
  shutterBusy: { opacity: 0.4 },
  shutterInner: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: 'white',
  },
  infoPanel: {
    position: 'absolute',
    top: 50,
    left: 100,
    right: 12,
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderRadius: 8,
    padding: 8,
    flexDirection: 'row',
  },
  previewImg: {
    width: 70,
    height: 70,
    borderRadius: 4,
    backgroundColor: '#222',
    marginRight: 10,
  },
  infoText: {
    flex: 1,
    justifyContent: 'center',
  },
  infoName: {
    color: 'white',
    fontSize: 11,
    marginBottom: 4,
    fontWeight: '600',
  },
  infoLine: {
    color: 'white',
    fontSize: 11,
    marginVertical: 1,
  },

  // 歷史紀錄
  historyRoot: { flex: 1, backgroundColor: '#f5f7f9' },
  historyHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: 50,
    paddingHorizontal: 12,
    paddingBottom: 10,
    backgroundColor: 'white',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  historyBack: { paddingVertical: 6, paddingHorizontal: 10 },
  historyBackText: { fontSize: 16, color: '#1d4d3a', fontWeight: '600' },
  historyTitle: {
    flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: '#1d4d3a',
  },
  sortBtn: {
    paddingVertical: 6, paddingHorizontal: 10,
    backgroundColor: '#e0f2e7', borderRadius: 6,
  },
  sortBtnText: { color: '#1d4d3a', fontWeight: '600', fontSize: 13 },
  emptyText: { fontSize: 18, color: '#666', marginBottom: 8 },
  emptyHint: { fontSize: 13, color: '#999' },
  histItem: {
    flexDirection: 'row',
    backgroundColor: 'white',
    marginHorizontal: 10,
    marginVertical: 4,
    padding: 10,
    borderRadius: 8,
    elevation: 1,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 3,
  },
  histThumb: {
    width: 80, height: 80, borderRadius: 6,
    backgroundColor: '#222', marginRight: 12,
  },
  histText: { flex: 1, justifyContent: 'center' },
  histTime: { fontSize: 11, color: '#666', marginBottom: 2 },
  histRatio: { fontSize: 12, color: '#aa6a00', marginBottom: 1 },
  histCells: { fontSize: 14, fontWeight: '700', color: '#0f766e' },
  histOd: { fontSize: 11, color: '#444', marginTop: 2 },

  // 全螢幕詳細 Modal
  detailRoot: { flex: 1, backgroundColor: '#fafafa' },
  detailHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingTop: 50, paddingHorizontal: 12, paddingBottom: 8,
    backgroundColor: 'white',
    borderBottomWidth: 1, borderBottomColor: '#e0e0e0',
  },
  deleteBtn: {
    paddingVertical: 6, paddingHorizontal: 12,
    backgroundColor: '#fee2e2', borderRadius: 6,
  },
  deleteBtnText: { color: '#b91c1c', fontWeight: '600', fontSize: 13 },
  detailScroll: { padding: 16 },
  detailImg: {
    width: '100%', aspectRatio: 4/3,
    backgroundColor: '#000', borderRadius: 8, marginBottom: 12,
  },
  detailFilename: {
    fontSize: 11, color: '#666',
    fontFamily: 'monospace', marginBottom: 8,
  },
  detailLine: { fontSize: 13, color: '#444', marginBottom: 4 },
  detailDivider: {
    height: 1, backgroundColor: '#e0e0e0', marginVertical: 10,
  },
  detailSection: {
    fontSize: 12, fontWeight: '700', color: '#1d4d3a',
    marginBottom: 4, letterSpacing: 1,
  },
  detailRow: {
    fontSize: 14, color: '#222',
    fontFamily: 'monospace', marginVertical: 2,
  },
});
