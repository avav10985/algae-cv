@echo off
chcp 65001 > nul
echo ================================================
echo   CellPose 藻類細胞偵測 - 執行
echo ================================================
echo.

if not exist venv (
    echo [錯誤] 找不到 venv 資料夾
    echo 請先執行 setup.bat 安裝環境
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM 檢查是否有傳入圖片路徑
if "%~1"=="" (
    echo 使用預設的測試圖片：test_images\sample1.jpg
    echo 若要換別張，用法：run.bat "圖片完整路徑"
    echo.
    python cellpose_test.py "test_images\sample1.jpg" --scale 0.5
) else (
    python cellpose_test.py "%~1" --scale 0.5
)

echo.
echo ================================================
echo   結果已存到 cellpose_result.jpg
echo ================================================
pause
