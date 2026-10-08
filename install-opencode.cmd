@echo off
setlocal

if "%USERPROFILE%"=="" (
  echo error: USERPROFILE unset -- refusing to install 1>&2
  exit /b 1
)

set "CONFIG_ROOT=%USERPROFILE%\.config\opencode"

set "SKILL_DST=%CONFIG_ROOT%\skills\vulnhunt"
set "COMMAND_DST=%CONFIG_ROOT%\commands\vulnhunt.md"
set "AGENT_DIR=%CONFIG_ROOT%\agents"
set "PROFILE_DST=%CONFIG_ROOT%\vulnhunt.static.json"

if not exist "%CONFIG_ROOT%\skills" mkdir "%CONFIG_ROOT%\skills"
if not exist "%CONFIG_ROOT%\commands" mkdir "%CONFIG_ROOT%\commands"
if not exist "%AGENT_DIR%" mkdir "%AGENT_DIR%"
if exist "%SKILL_DST%" rmdir /s /q "%SKILL_DST%"

xcopy "%~dp0vulnhunt" "%SKILL_DST%\" /e /i /q /y >nul
if errorlevel 1 exit /b 1
copy /y "%~dp0opencode\commands\vulnhunt.md" "%COMMAND_DST%" >nul
if errorlevel 1 exit /b 1
copy /y "%~dp0opencode\agents\vulnhunt-orchestrator.md" "%AGENT_DIR%\vulnhunt-orchestrator.md" >nul
if errorlevel 1 exit /b 1
copy /y "%~dp0opencode\agents\vulnhunt-worker.md" "%AGENT_DIR%\vulnhunt-worker.md" >nul
if errorlevel 1 exit /b 1
copy /y "%~dp0opencode\opencode.vulnhunt.json" "%PROFILE_DST%" >nul
if errorlevel 1 exit /b 1

echo Installed OpenCode VulnHunter scanner:
echo   skill:   %SKILL_DST%
echo   command: %COMMAND_DST%
echo   agents:  %AGENT_DIR%\vulnhunt-{orchestrator,worker}.md
echo   profile: %PROFILE_DST%
echo Do not run OpenCode inside an untrusted checkout. Use a sanitized copy.
