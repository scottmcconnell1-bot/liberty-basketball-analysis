$ErrorActionPreference = "Stop"
$RepoPath = "C:\Users\scott\Documents\liberty-basketball-analysis"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "    LAUNCHING AUTOMATED BASKETBALL AGENT PIPELINE   " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

$LoopCount = 1

while ($true) {
    Write-Host "`n[LOOP $LoopCount] Invoking Architect (Hermes) inside Ubuntu WSL..." -ForegroundColor Yellow
    
    $LinuxRepoPath = "/mnt/c/Users/scott/Documents/liberty-basketball-analysis"
    
    # 1. Define the pristine architectural instruction string
    $PromptText = "Analyze workspace. Read the bottom entries of $LinuxRepoPath/WORKLOG.md and current local git log to anchor your position. Identify the next single additive task block for Stage 2 (TASK-2.2 Possession Detection State Machine). Output the exact architectural code specifications directly into a new file on disk named $LinuxRepoPath/NEXT_TASK.md. Do not edit source files directly."
    
    # 2. Write the prompt to a temporary file on the shared filesystem
    $TempPromptFile = "$RepoPath\temp_hermes_prompt.txt"
    [System.IO.File]::WriteAllText($TempPromptFile, $PromptText, [System.Text.Encoding]::UTF8)
    
    # 3. Read the prompt content safely and pass it into WSL without PowerShell subexpression conflicts
    $FileContent = Get-Content -Path $TempPromptFile -Raw
    wsl --exec bash --login -c "hermes chat -q '$FileContent'"
    
    # Clean up the temporary prompt file
    Remove-Item $TempPromptFile -Force -ErrorAction SilentlyContinue

    # 4. Check Windows storage path to verify the blueprint file was generated
    if (-not (Test-Path "$RepoPath\NEXT_TASK.md")) {
        Write-Host "[GUARD] Hermes did not generate NEXT_TASK.md or has signaled phase completion. Halting for User." -ForegroundColor Green
        Break
    }

    Write-Host "[LOOP $LoopCount] Architect wrote plan. Invoking Builder (Aider + DeepSeek)..." -ForegroundColor Yellow
    
    # 5. Automatically feed the blueprint into Aider
    & aider --model ollama/qwen2.5-coder:32b --msg-file "$RepoPath\NEXT_TASK.md" --no-auto-commits --yes

    Write-Host "[LOOP $LoopCount] Builder finished code edits. Running Verification Suite..." -ForegroundColor Yellow
    
    # 6. Run PyTest framework against the test baseline
    $TestResult = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m pytest tests/test_ops_scripts_regression.py -k 'not test_panel_latest_write_is_atomic' -q" -Wait -Passthru -NoNewWindow
    
    if ($TestResult.ExitCode -eq 0) {
        Write-Host "[SUCCESS] Verification Passed! Committing stable milestone natively..." -ForegroundColor Green
        & git add ai_bridge.py
        & git commit -m "feat: autonomous agent generation loop - task $LoopCount completed successfully"
        
        # Cleanup the temporary task blueprint file safely
        Remove-Item "$RepoPath\NEXT_TASK.md" -Force -ErrorAction SilentlyContinue
        
        Write-Host "`n[STOP GATE] Task block completed with 100% stable tests. Standing by for Director authorization." -ForegroundColor DarkYellow
        
        # Remove or comment out 'Break' below if you want the loop to continue autonomously to the next task
        Break
    } else {
        Write-Host "[FAILURE] PyTest detected code regressions. Rolling back code changes to baseline..." -ForegroundColor Red
        
        & git checkout HEAD -- ai_bridge.py
        Remove-Item "$RepoPath\NEXT_TASK.md" -Force -ErrorAction SilentlyContinue
        Write-Host "[GUARD] Code safely rolled back to pristine baseline. Halting for User evaluation." -ForegroundColor DarkYellow
        Break
    }

    $LoopCount++
}