Liberty Basketball Analysis - Coach Demo
========================================

Double-click LibertyDemo.exe. It extracts a portable copy and runs
install_and_run.bat, which:

  1. Finds Python 3.12/3.13 (py launcher preferred) or installs 3.12 via winget
  2. Creates a local .venv and installs requirements.txt
  3. Starts the app with the venv Python (scripts\launch_liberty.py --no-browser)
  4. Opens http://127.0.0.1:8080
  5. On keypress: stops only Liberty processes, removes .venv + TEMP log

Coach blurb
-----------
Liberty is a local basketball film + tagging workstation for high-school coaches.
This demo lets you click through the dashboard, Film Tool, roster/schedule views,
and reports without cloud signup. It is a local Windows package - no GPU AI
analysis in this build (detector weights omitted to keep the download small).

Build notes (2026-07-18)
------------------------
- Staging: C:\Temp\LibertyDemoPackage\LibertyDemo
- Demo DB: slim film_analysis.db (~0.52 MB) - schema + teams/games/roster/events;
  omitted heavy detections/review_items (and credentials). Full source DB was ~123 MB.
- Excluded: .git, .venv, __pycache__, build, dist, .pytest_cache, logs, uploads,
  tag-exports, experiments, benchmarks, .idea, .vscode, videos, large .pt/.task
  weights, media files
- SFX: 7-Zip 7z.sfx + config.txt + LibertyDemo.zip
- Known caveats:
  * winget Python (if installed) remains after cleanup
  * GPU AI / YOLO inference is not in the demo
  * First run needs network for pip wheels
  * If something already serves port 8080, stop it or change PORT in the bat

Rebuild
-------
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1

Installer source of truth: deploy\install_and_run.bat
