@echo off
chcp 65001 >nul
title 대학 입학설명회 자동신청 봇

echo.
echo ================================================
echo  대학 입학설명회 자동신청 봇
echo ================================================
echo.

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo.
    echo 지금 바로 설치하세요:
    echo 1. https://www.python.org/downloads 접속
    echo 2. Download Python 버튼 클릭
    echo 3. 설치 시 "Add Python to PATH" 체크 필수!
    echo 4. 설치 완료 후 이 파일 다시 실행
    echo.
    pause
    start https://www.python.org/downloads
    exit /b
)

echo [OK] Python 설치 확인
echo.

:: 패키지 설치
echo [설치중] 필요한 패키지 설치 중... (최초 1회만)
pip install playwright pyyaml -q
playwright install chromium

echo.
echo [완료] 설치 완료!
echo.
echo ================================================
echo  봇 시작합니다. 이 창을 닫지 마세요!
echo  고려대: 오전 10시 자동신청
echo ================================================
echo.

python bot.py

pause
