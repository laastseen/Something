@echo off
setlocal
cd /d "%~dp0.."

set GIT=C:\Program Files\Git\bin\git.exe
if not exist "%GIT%" set GIT=git

"%GIT%" remote remove origin 2>nul
"%GIT%" remote add origin https://github.com/laastseen/Something.git

echo.
echo Пуш в https://github.com/laastseen/Something
echo Откроется окно входа в GitHub — войдите в аккаунт laastseen.
echo.

"%GIT%" push -u origin main
if errorlevel 1 (
  echo.
  echo Если окно не появилось, создайте токен:
  echo https://github.com/settings/tokens/new?scopes=repo
  echo Затем в PowerShell:
  echo   cd %cd%
  echo   $env:GH_TOKEN = "ghp_ваш_токен"
  echo   git push https://laastseen:$env:GH_TOKEN@github.com/laastseen/Something.git main
  exit /b 1
)

echo.
echo Готово: https://github.com/laastseen/Something
endlocal
