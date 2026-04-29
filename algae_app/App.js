import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Image,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {
  Camera,
  useCameraDevice,
  useCameraPermission,
} from 'react-native-vision-camera';
import * as FileSystem from 'expo-file-system';

function timestampFilename() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `photo_${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}.jpg`;
}

export default function App() {
  const { hasPermission, requestPermission } = useCameraPermission();
  const device = useCameraDevice('back');
  const cameraRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null);

  useEffect(() => {
    if (!hasPermission) requestPermission();
  }, [hasPermission, requestPermission]);

  const capture = useCallback(async () => {
    if (!cameraRef.current || busy) return;
    setBusy(true);
    try {
      const photo = await cameraRef.current.takePhoto({
        flash: 'off',
        enableShutterSound: false,
      });
      const filename = timestampFilename();
      const dest = `${FileSystem.documentDirectory}${filename}`;
      const src = photo.path.startsWith('file://')
        ? photo.path
        : `file://${photo.path}`;
      await FileSystem.moveAsync({ from: src, to: dest });
      setLast({ uri: dest, name: filename });
    } catch (e) {
      Alert.alert('拍照失敗', String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }, [busy]);

  if (!hasPermission) {
    return (
      <View style={styles.center}>
        <Text style={styles.message}>需要相機權限才能拍照</Text>
        <TouchableOpacity onPress={requestPermission} style={styles.permBtn}>
          <Text>授權相機</Text>
        </TouchableOpacity>
        <StatusBar style="light" />
      </View>
    );
  }

  if (!device) {
    return (
      <View style={styles.center}>
        <Text style={styles.message}>找不到後鏡頭</Text>
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
        exposure={0}
      />

      <View pointerEvents="none" style={styles.beakerWrap}>
        <View style={styles.beakerFrame}>
          <Text style={styles.frameLabel}>燒杯</Text>
        </View>
      </View>

      <View pointerEvents="none" style={styles.whiteCardRoi}>
        <Text style={styles.frameLabel}>白卡</Text>
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
        <View style={styles.preview}>
          <Image source={{ uri: last.uri }} style={styles.previewImg} />
          <Text style={styles.previewName} numberOfLines={2}>
            {last.name}
          </Text>
        </View>
      )}

      <StatusBar style="light" />
    </View>
  );
}

const styles = StyleSheet.create({
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
  beakerWrap: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
  beakerFrame: {
    width: 240,
    height: 340,
    borderWidth: 2,
    borderColor: '#00ff66',
    borderRadius: 4,
  },
  whiteCardRoi: {
    position: 'absolute',
    bottom: 140,
    left: 24,
    width: 80,
    height: 80,
    borderWidth: 2,
    borderColor: '#ffff00',
    borderRadius: 4,
  },
  frameLabel: {
    position: 'absolute',
    top: -22,
    left: 0,
    color: 'white',
    fontSize: 12,
    backgroundColor: 'rgba(0,0,0,0.6)',
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 2,
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
  preview: {
    position: 'absolute',
    top: 50,
    right: 12,
    width: 92,
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: 6,
    padding: 4,
  },
  previewImg: {
    width: 84,
    height: 84,
    borderRadius: 4,
    backgroundColor: '#222',
  },
  previewName: {
    color: 'white',
    fontSize: 9,
    marginTop: 4,
  },
});
