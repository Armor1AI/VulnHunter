@echo off
setlocal

if "%USERPROFILE%"=="" (
  echo error: USERPROFILE unset -- refusing to uninstall 1>&2
  exit /b 1
)

if "%XDG_CONFIG_HOME%"=="" (
  set "CONFIG_ROOT=%USERPROFILE%\.config\opencode"
) else (
  set "CONFIG_ROOT=%XDG_CONFIG_HOME%\opencode"
)

if exist "%CONFIG_ROOT%\skills\vulnhunt" rmdir /s /q "%CONFIG_ROOT%\skills\vulnhunt"
if exist "%CONFIG_ROOT%\commands\vulnhunt.md" del /q "%CONFIG_ROOT%\commands\vulnhunt.md"
if exist "%CONFIG_ROOT%\agents\vulnhunt-orchestrator.md" del /q "%CONFIG_ROOT%\agents\vulnhunt-orchestrator.md"
if exist "%CONFIG_ROOT%\agents\vulnhunt-worker.md" del /q "%CONFIG_ROOT%\agents\vulnhunt-worker.md"
if exist "%CONFIG_ROOT%\vulnhunt.static.json" del /q "%CONFIG_ROOT%\vulnhunt.static.json"
echo Uninstalled OpenCode VulnHunter scanner.
