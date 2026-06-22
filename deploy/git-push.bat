@echo off
setlocal
cd /d "%~dp0.."

where git >nul 2>&1
if errorlevel 1 (
  echo Git не найден. Установите: https://git-scm.com/download/win
  echo После установки перезапустите терминал и снова запустите этот скрипт.
  exit /b 1
)

if not exist .git (
  git init
  git branch -M main
)

git add -A
git status

echo.
echo Создайте пустой репозиторий на GitHub и выполните:
echo   git remote add origin https://github.com/USER/REPO.git
echo   git commit -m "Initial deploy"
echo   git push -u origin main
echo.
echo Затем на сервере можно клонировать:
echo   bash deploy/setup-server.sh https://github.com/USER/REPO.git
echo.
echo Или залить напрямую с ПК:
echo   set SOMETHING_SSH_PASSWORD=ваш_пароль
echo   python deploy/remote_deploy.py --repo https://github.com/USER/REPO.git
