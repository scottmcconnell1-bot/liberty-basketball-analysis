Liberty Basketball Analysis - Coach Demo
========================================

Double-click LibertyDemo.exe. It extracts a TEMP copy and runs
install_and_run.bat, which:

  1. Copies the demo to %LOCALAPPDATA%\LibertyBasketballDemo\ (session only)
  2. Relaunches from LocalAppData for the session (NO Desktop shortcut)
  3. Finds Python 3.12/3.13 or installs 3.12 via winget (once)
  4. Creates/reuses LocalAppData\.venv and installs requirements.txt
  5. Starts the app with DEMO_MODE=1 (scripts\launch_liberty.py --no-browser)
  6. Opens the browser to http://127.0.0.1:8080 (bat start + Start-Process)
  7. Coach clicks DONE in the web app top menu ??? POST /api/demo/done
     schedules TEMP cleanup, stops the server; bat then wipes
     %LOCALAPPDATA%\LibertyBasketballDemo and TEMP LibertyDemo_* leftovers.
     winget Python is NOT uninstalled.

Coach blurb
-----------
Liberty is a local basketball film + tagging workstation for high-school coaches.
This demo lets you click through the dashboard, Film Tool, roster/schedule views,
and reports without cloud signup. It is a local Windows package - no GPU AI
analysis in this build (detector weights omitted to keep the download small).

Build notes (2026-07-19)
------------------------
- Staging: C:\Temp\LibertyDemoPackage\LibertyDemo
- Demo DB: slim film_analysis.db (1.91 MB) - schema + teams/games/roster/events;
  omitted heavy detections/review_items (and credentials). Full source DB was ~123 MB.
- Excluded: .git, .venv, __pycache__, build, dist, .pytest_cache, logs, uploads,
  tag-exports, experiments, benchmarks, .idea, .vscode, videos, large .pt/.task
  weights, media files
- SFX: 7-Zip 7z.sfx + config.txt + LibertyDemo.7z (-t7z; stock sfx requires 7z not zip)
- Session install: %LOCALAPPDATA%\LibertyBasketballDemo (wiped on DONE)
- Exit UX: DONE button in web nav (DEMO_MODE); bat waits for server exit then cleans up
- Known caveats:
  * winget Python (if installed) remains after cleanup
  * GPU AI / YOLO inference is not in the demo
  * First run needs network for pip wheels
  * If something already serves port 8080, stop it or change PORT in the bat

Rebuild
-------
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1

Installer source of truth: deploy\install_and_run.bat + blueprints\demo.py
