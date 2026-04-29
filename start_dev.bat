@echo off
echo === algae_app dev server ===
echo.
echo [1/3] adb devices
adb devices
echo.
echo [2/3] adb reverse tcp:8081 tcp:8081
adb reverse tcp:8081 tcp:8081
if errorlevel 1 (
  echo WARNING: adb reverse failed. Check phone USB connection.
  pause
)
echo.
echo [3/3] starting Metro dev server...
cd /d d:\algae-cv\algae_app
npx expo start --dev-client
