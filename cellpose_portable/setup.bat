@echo off
chcp 65001 > nul
echo ================================================
echo   CellPose 藻類細胞偵測 - 環境安裝
echo ================================================
echo.

REM 檢查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python
    echo 請先到 https://www.python.org/downloads/ 下載安裝 Python 3.11 以上版本
    echo 安裝時記得勾選 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/4] Python 已安裝
python --version

echo.
echo [2/4] 建立虛擬環境 venv ...
if exist venv (
    echo      venv 已存在，跳過建立
) else (
    python -m venv venv
    if errorlevel 1 (
        echo [錯誤] 建立虛擬環境失敗
        pause
        exit /b 1
    )
)

echo.
echo [3/4] 啟動 venv 並安裝套件 （需要網路，約 1-2 GB）...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [錯誤] 套件安裝失敗
    pause
    exit /b 1
)

echo.
echo [4/4] 複製預訓練模型到使用者資料夾（避免再下載 1.15 GB）...
set CELLPOSE_DIR=%USERPROFILE%\.cellpose\models
if not exist "%CELLPOSE_DIR%" mkdir "%CELLPOSE_DIR%"
if exist "cellpose_model\cpsam" (
    if not exist "%CELLPOSE_DIR%\cpsam" (
        copy /Y "cellpose_model\cpsam" "%CELLPOSE_DIR%\cpsam"
        echo      模型已複製到 %CELLPOSE_DIR%\cpsam
    ) else (
        echo      目的地已有模型，跳過複製
    )
) else (
    echo      [警告] 找不到 cellpose_model\cpsam ，第一次執行時會從網路下載 1.15 GB
)

echo.
echo ================================================
echo   安裝完成！
echo   執行 run.bat 來測試
echo ================================================
pause
