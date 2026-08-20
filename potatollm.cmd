@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="

py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PYTHON_CMD (
  if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python311\python.exe"
)
if not defined PYTHON_CMD (
  if exist "%LocalAppData%\Programs\Python\Python310\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python310\python.exe"
)
if not defined PYTHON_CMD (
  if exist "%LocalAppData%\Programs\Python\Python39\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python39\python.exe"
)

if not defined PYTHON_CMD (
  echo Python 3.9 or newer was not found.
  echo Install Python from https://www.python.org/downloads/ and enable "Add python.exe to PATH",
  echo or install the Python Launcher so this wrapper can run: py -3 potatollm.py selftest
  echo.
  pause
  exit /b 1
)

if "%~1"=="" (
  echo potatollm commands:
  echo   potatollm.cmd selftest
  echo   potatollm.cmd check ^<model^>
  echo   potatollm.cmd bench ^<model^>
  echo   potatollm.cmd table
  echo.
  %PYTHON_CMD% "%~dp0potatollm.py" selftest
) else (
  %PYTHON_CMD% "%~dp0potatollm.py" %*
)

set "STATUS=%ERRORLEVEL%"
echo.
if not "%STATUS%"=="0" echo potatollm finished with errors. See the message above.
pause
exit /b %STATUS%
