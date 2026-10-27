$ErrorActionPreference = "Stop"
$RepoPath = "C:\Users\scott\Documents\liberty-basketball-analysis"
Set-Location $RepoPath

# Builder model: must appear in `ollama list`. Change here to swap models
# (e.g. after `ollama pull qwen2.5-coder:32b`, set this to "qwen2.5-coder:32b").
$OllamaModel = "gemma4:cloud"
$env:OLLAMA_API_BASE = "http://127.0.0.1:11434"

# Files the Builder may edit; also the rollback scope on failure.
$BuilderFiles = @("ai_bridge.py", "settings_store.py")
$NewTestFile = "tests/test_ai_bridge.py"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "    LAUNCHING AUTOMATED BASKETBALL AGENT PIPELINE   " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# Preflight: fail fast if the Builder model is not installed
$InstalledModels = (& ollama list) -join "`n"
if ($LASTEXITCODE -ne 0 -or $InstalledModels -notmatch [regex]::Escape($OllamaModel)) {
    Write-Host "[GUARD] Ollama model '$OllamaModel' not found. Run 'ollama list' / 'ollama pull $OllamaModel'. Halting." -ForegroundColor Red
    exit 1
}

$LoopCount = 1

while ($true) {
    Write-Host "`n[LOOP $LoopCount] Invoking Architect (Hermes) inside Ubuntu WSL..." -ForegroundColor Yellow

    $LinuxRepoPath = "/mnt/c/Users/scott/Documents/liberty-basketball-analysis"

    # 1. Define the pristine architectural instruction string
    $PromptText = "Analyze workspace. Read the bottom entries of $LinuxRepoPath/WORKLOG.md and current local git log to anchor your position. Identify the next single additive task block for Stage 2 (TASK-2.2 Possession Detection State Machine). Output the exact architectural code specifications directly into a new file on disk named $LinuxRepoPath/NEXT_TASK.md. Do not edit source files directly."

    # 2. Escape single quotes for the bash single-quoted string below
    $EscapedPrompt = $PromptText -replace "'", "'\''"
    wsl --exec bash --login -c "hermes chat -q '$EscapedPrompt'"

    # 3. Check Windows storage path to verify the blueprint file was generated
    if (-not (Test-Path "$RepoPath\NEXT_TASK.md")) {
        Write-Host "[GUARD] Hermes did not generate NEXT_TASK.md or has signaled phase completion. Halting for User." -ForegroundColor Green
        Break
    }

    Write-Host "[LOOP $LoopCount] Architect wrote plan. Invoking Builder (Aider + $OllamaModel)..." -ForegroundColor Yellow

    # 4. Feed the blueprint into Aider, limited to the files it is allowed to edit
    & aider --model "ollama_chat/$OllamaModel" --message-file "$RepoPath\NEXT_TASK.md" --no-auto-commits --yes --no-show-model-warnings @BuilderFiles $NewTestFile

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[GUARD] Builder (Aider) failed with exit code $LASTEXITCODE. Rolling back and halting." -ForegroundColor Red
        & git checkout HEAD -- @BuilderFiles
        if (-not (git ls-files $NewTestFile)) { Remove-Item $NewTestFile -Force -ErrorAction SilentlyContinue }
        Break
    }

    # Aider can exit 0 without editing anything (e.g. the model hit a usage limit)
    $Changed = & git status --porcelain -- @BuilderFiles $NewTestFile
    if (-not $Changed) {
        Write-Host "[GUARD] Builder made no file changes. Nothing to verify or commit. Halting." -ForegroundColor Red
        Break
    }

    Write-Host "[LOOP $LoopCount] Builder finished code edits. Running Verification Suite..." -ForegroundColor Yellow

    # 5. Run PyTest against the regression baseline plus the new task's tests (if created)
    $TestTargets = @("tests/test_ops_scripts_regression.py")
    if (Test-Path $NewTestFile) { $TestTargets += $NewTestFile }
    & .\.venv\Scripts\python.exe -m pytest @TestTargets -k "not test_panel_latest_write_is_atomic" -q

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[SUCCESS] Verification Passed! Committing stable milestone natively..." -ForegroundColor Green
        & git add @BuilderFiles
        if (Test-Path $NewTestFile) { & git add $NewTestFile }
        & git commit -m "feat: autonomous agent generation loop - task $LoopCount completed successfully"

        # Cleanup the temporary task blueprint file safely
        Remove-Item "$RepoPath\NEXT_TASK.md" -Force -ErrorAction SilentlyContinue

        Write-Host "`n[STOP GATE] Task block completed with 100% stable tests. Standing by for Director authorization." -ForegroundColor DarkYellow

        # Remove or comment out 'Break' below if you want the loop to continue autonomously to the next task
        Break
    } else {
        Write-Host "[FAILURE] PyTest detected code regressions. Rolling back code changes to baseline..." -ForegroundColor Red

        & git checkout HEAD -- @BuilderFiles
        if (-not (git ls-files $NewTestFile)) { Remove-Item $NewTestFile -Force -ErrorAction SilentlyContinue }
        Remove-Item "$RepoPath\NEXT_TASK.md" -Force -ErrorAction SilentlyContinue
        Write-Host "[GUARD] Code safely rolled back to pristine baseline. Halting for User evaluation." -ForegroundColor DarkYellow
        Break
    }

    $LoopCount++
}
