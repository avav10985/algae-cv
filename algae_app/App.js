import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Image,
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

// 大框 — 燒杯佔左 55%×78%,白卡佔右 34%×78%
const BEAKER_FRAC = { x: 0.04, y: 0.10, w: 0.55, h: 0.78 };
const WHITECARD_FRAC = { x: 0.62, y: 0.10, w: 0.34, h: 0.78 };

// 拍照預設集 — 不同光照場景,選一個可保證該情境下兩次拍照數值穩定
const PRESETS = [
  { key: 'auto',   label: '自動',  tag: 'auto',   iso: undefined, exposure: undefined },
  { key: 'iso50',  label: 'ISO50',  tag: 'iso50',  iso: 50,  exposure: 0 },
  { key: 'iso100', label: 'ISO100', tag: 'iso100', iso: 100, exposure: 0 },
  { key: 'iso200', label: 'ISO200', tag: 'iso200', iso: 200, exposure: 0 },
  { key: 'iso400', label: 'ISO400', tag: 'iso400', iso: 400, exposure: 0 },
];

function timestampFilename(tag) {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `photo_${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}_${tag}.jpg`;
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
    return {
      r: Math.round(r / pix),
      g: Math.round(g / pix),
      b: Math.round(b / pix),
    };
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
  return screen === 'home' ? (
    <HomeScreen onStartCamera={() => setScreen('camera')} />
  ) : (
    <CameraScreen onBack={() => setScreen('home')} />
  );
}

function HomeScreen({ onStartCamera }) {
  return (
    <View style={styles.homeRoot}>
      <View style={styles.homeTop}>
        <Text style={styles.homeTitle}>algae-cv</Text>
        <Text style={styles.homeSubtitle}>藻類比色 · 顏色 → 濃度估計</Text>
      </View>

      <TouchableOpacity
        style={styles.bigBtn}
        onPress={onStartCamera}
        activeOpacity={0.85}
      >
        <Text style={styles.bigBtnIcon}>📸</Text>
        <Text style={styles.bigBtnText}>進入相機</Text>
      </TouchableOpacity>

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
  const [presetKey, setPresetKey] = useState('auto');
  const preset = PRESETS.find((p) => p.key === presetKey) || PRESETS[0];

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
      const filename = timestampFilename(preset.tag);
      const dest = `${FileSystem.documentDirectory}${filename}`;
      const src = photo.path.startsWith('file://')
        ? photo.path
        : `file://${photo.path}`;
      await FileSystem.copyAsync({ from: src, to: dest });

      setLast({
        uri: dest,
        name: filename,
        beaker: null,
        white: null,
        albumOk: null,
        processing: true,
      });

      const albumPromise = saveToAlbum(dest);
      const { width: actualW, height: actualH } = await getActualSize(dest);
      const screenAspect = win.width / win.height;
      const photoAspect = actualW / actualH;
      console.log(`screen ${win.width}x${win.height} (aspect ${screenAspect.toFixed(3)}), photo ${actualW}x${actualH} (aspect ${photoAspect.toFixed(3)})`);
      const beakerMapped = screenFracToPhotoFrac(BEAKER_FRAC, screenAspect, photoAspect);
      const whiteMapped = screenFracToPhotoFrac(WHITECARD_FRAC, screenAspect, photoAspect);
      console.log('mapped 燒杯 frac:', beakerMapped);
      console.log('mapped 白卡 frac:', whiteMapped);
      const beakerRGB = await extractAvgRGB(dest, actualW, actualH, beakerMapped, '燒杯');
      const whiteRGB = await extractAvgRGB(dest, actualW, actualH, whiteMapped, '白卡');
      const albumOk = await albumPromise;

      setLast((prev) =>
        prev && prev.uri === dest
          ? { ...prev, beaker: beakerRGB, white: whiteRGB, albumOk, processing: false }
          : prev
      );

      try {
        await FileSystem.deleteAsync(src, { idempotent: true });
      } catch {}
    } catch (e) {
      Alert.alert('拍照失敗', String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }, [busy, win, preset]);

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
        iso={preset.iso}
        exposure={preset.exposure}
      />

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

      <View style={styles.presetBar}>
        {PRESETS.map((p) => {
          const active = p.key === presetKey;
          return (
            <TouchableOpacity
              key={p.key}
              style={[styles.presetBtn, active && styles.presetBtnActive]}
              onPress={() => setPresetKey(p.key)}
              activeOpacity={0.7}
            >
              <Text style={[styles.presetLabel, active && styles.presetLabelActive]}>
                {p.label}
              </Text>
            </TouchableOpacity>
          );
        })}
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
                  白卡 RGB: {last.white ? `(${last.white.r}, ${last.white.g}, ${last.white.b})` : '提取失敗'}
                </Text>
                <Text style={[styles.infoLine, { color: '#66ff99' }]}>
                  燒杯 RGB: {last.beaker ? `(${last.beaker.r}, ${last.beaker.g}, ${last.beaker.b})` : '提取失敗'}
                </Text>
              </>
            )}
          </View>
        </View>
      )}

      <StatusBar style="light" />
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
  presetBar: {
    position: 'absolute',
    bottom: 130,
    left: 12,
    right: 12,
    flexDirection: 'row',
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: 8,
    padding: 4,
  },
  presetBtn: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 4,
  },
  presetBtnActive: {
    backgroundColor: '#00b07a',
  },
  presetLabel: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: 11,
    fontWeight: '600',
  },
  presetLabelActive: {
    color: 'white',
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
});
