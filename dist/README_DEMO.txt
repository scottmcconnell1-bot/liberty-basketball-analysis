Liberty Basketball Analysis - Coach Demo
========================================

Double-click LibertyDemo.exe. It extracts a TEMP copy and runs
install_and_run.bat, which:

  1. Copies the demo to %LOCALAPPDATA%\LibertyBasketballDemo\ (session only)
  2. Creates Desktop URL shortcuts that open http://127.0.0.1:8080
       - Liberty Basketball Demo.lnk
       - Liberty Basketball Demo.url  (InternetShortcut; more reliable for URLs)
     Desktop is resolved via GetFolderPath, %HOME%\Desktop,
     %HOME%\OneDrive\Desktop, and registry User Shell Folders
  3. Relaunches from LocalAppData for the session
  4. Finds Python 3.12/3.13 or installs 3.12 via winget (once)
  5. Creates/reuses LocalAppData\.venv and installs requirements.txt
  6. Starts the app (scripts\launch_liberty.py --no-browser) and opens :8080
  7. On keypress: stops Liberty (PID-based), deletes Desktop shortcuts,
     wipes %LOCALAPPDATA%\LibertyBasketballDemo, deletes TEMP logs

Coach blurb
-----------
Liberty is a local basketball film + tagging workstation for high-school coaches.
This demo lets you click through the dashboard, Film Tool, roster/schedule views,
and reports without cloud signup. It is a local Windows package - no GPU AI
analysis in this build (detector weights omitted to keep the download small).

Build notes (2026-07-18)
------------------------
- Staging: C:\Temp\LibertyDemoPackage\LibertyDemo
- Demo DB: slim film_analysis.db (0.52 MB) - schema + teams/games/roster/events;
  omitted heavy detections/review_items (and credentials). Full source DB was ~123 MB.
- Excluded: .git, .venv, __pycache__, build, dist, .pytest_cache, logs, uploads,
  tag-exports, experiments, benchmarks, .idea, .vscode, videos, large .pt/.task
  weights, media files
- SFX: 7-Zip 7z.sfx + config.txt + LibertyDemo.7z (-t7z; stock sfx requires 7z not zip)
- Session install: %LOCALAPPDATA%\LibertyBasketballDemo (wiped on exit)
- Known caveats:
  * winget Python (if installed) remains after cleanup
  * GPU AI / YOLO inference is not in the demo
  * First run needs network for pip wheels
  * If something already serves port 8080, stop it or change PORT in the bat

Rebuild
-------
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1

Installer source of truth: deploy\install_and_run.bat
