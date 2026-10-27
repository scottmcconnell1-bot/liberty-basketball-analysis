[CmdletBinding()]
param(
    [int]$MaxRounds = 10,
    [int]$MaxNoProgress = 3,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Repo

$LogPath = Join-Path $Repo 'docs\agent_handoffs\TEAM_LOG.md'
$TeamDir = Join-Path $Repo '.team'
$StopPath = Join-Path $TeamDir 'STOP.md'
$StatusPath = Join-Path $TeamDir 'STATUS.md'
$TaskPath = Join-Path $Repo 'NEXT_TASK.md'
$PreviousTaskPath = Join-Path $TeamDir 'previous_NEXT_TASK.md'
$HermesPromptPath = Join-Path $TeamDir 'prompt_hermes.txt'
$OpenCodePromptPath = Join-Path $TeamDir 'prompt_opencode.txt'
$ClaudePromptPath = Join-Path $TeamDir 'prompt_claude.txt'
$OpenCodePromptArg = 'Read .team/prompt_opencode.txt and follow it exactly.'
$ClaudePromptArg = 'Read .team/prompt_claude.txt and follow it exactly.'
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
$ScoreScript = Join-Path $Repo 'scripts\team_score.py'
$Dash = [char]0x2014
$NewLine = [Environment]::NewLine

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$script:Commits = 0
$script:StartScore = $null
$script:EndScore = $null
$script:RoundsRun = 0
$script:StopReason = ''
$script:Running = $true
$script:RecapPath = ''
$script:StartHash = ''
$script:StopFileText = ''
$script:LastClaudeVerdict = ''
$script:CurrentAgent = 'Loop'
$script:CurrentStep = 'start'
$script:CurrentRound = 0
$script:StepStarted = $null
$script:LastActivity = $null


function Format-Command {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $parts = New-Object System.Collections.Generic.List[string]
    $parts.Add($FilePath)
    foreach ($arg in $Arguments) {
        if ($arg -match '\s') {
            $parts.Add('"' + ($arg -replace '"', '\"') + '"')
        } else {
            $parts.Add($arg)
        }
    }
    return ($parts -join ' ')
}

function Write-TextFile {
    param(
        [string]$Path,
        [string]$Text
    )
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Write-Log {
    param(
        [string]$Agent,
        [string]$What,
        [string]$Body = ''
    )
    $dir = Split-Path -Parent $LogPath
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    if (-not (Test-Path -LiteralPath $LogPath)) {
        [System.IO.File]::WriteAllText($LogPath, '# Team Log' + $NewLine, $Utf8NoBom)
    }
    if ($Body.Length -gt 4000) {
        $Body = $Body.Substring(0, 4000) + ' ...'
    }
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $entry = $NewLine + '### ' + $stamp + ' ' + $Agent + ' ' + $Dash + ' ' + $What + $NewLine
    if ($Body) {
        $entry = $entry + $Body + $NewLine
    }
    [System.IO.File]::AppendAllText($LogPath, $entry, $Utf8NoBom)
}

function Get-GitStatusText {
    try {
        $text = (& $GitExe status --porcelain 2>$null) -join $NewLine
        return [string]$text
    } catch {
        return ''
    }
}

function Write-Status {
    param(
        [string]$Agent = '',
        [string]$Step = '',
        [int]$Round = -1,
        [string]$Prefix = ''
    )
    if ($Agent) {
        $script:CurrentAgent = $Agent
    }
    if ($Step) {
        $script:CurrentStep = $Step
    }
    if ($Round -ge 0) {
        $script:CurrentRound = $Round
    }
    $now = Get-Date
    $startedText = '--:--:--'
    $elapsed = 0
    if ($null -ne $script:StepStarted) {
        $startedText = $script:StepStarted.ToString('HH:mm:ss')
        $elapsed = [int][math]::Floor(($now - $script:StepStarted).TotalMinutes)
    }
    $lastText = '--:--:--'
    if ($null -ne $script:LastActivity) {
        $lastText = $script:LastActivity.ToString('HH:mm:ss')
    }
    $scoreText = 'not scored'
    if ($null -ne $script:EndScore) {
        $scoreText = $script:EndScore | ConvertTo-Json -Compress
    } elseif ($null -ne $script:StartScore) {
        $scoreText = $script:StartScore | ConvertTo-Json -Compress
    }
    $branchText = 'unknown'
    try {
        $branchText = (& $GitExe rev-parse --abbrev-ref HEAD).Trim()
    } catch {
        $branchText = 'unknown'
    }
    $lines = New-Object System.Collections.Generic.List[string]
    if ($Prefix) {
        $lines.Add($Prefix)
    }
    $lines.Add('Now: ' + $script:CurrentAgent + ' ' + $script:CurrentStep + ' (round ' + $script:CurrentRound + ')')
    $lines.Add('Started: ' + $startedText)
    $lines.Add('Elapsed: ' + $elapsed + ' min')
    $lines.Add('Last activity: ' + $lastText)
    $lines.Add('Branch: ' + $branchText)
    $lines.Add('Last score: ' + $scoreText)
    $lines.Add('Updated: ' + $now.ToString('yyyy-MM-dd HH:mm:ss'))
    Write-TextFile -Path $StatusPath -Text (($lines -join $NewLine) + $NewLine)
}

function Resolve-Command {
    param([string]$Name)
    foreach ($ext in @('.exe', '.cmd', '.bat')) {
        $cmd = Get-Command ($Name + $ext) -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd -and $cmd.Source) {
            return $cmd.Source
        }
    }
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }
    return $Name
}

$GitExe = Resolve-Command 'git'
$WslExe = Resolve-Command 'wsl'
$ClaudeExe = Resolve-Command 'claude'
$OpenCodeExe = Resolve-Command 'opencode'

$HermesShLinux = '/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/run_hermes.sh'
$HermesPromptLinux = '/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/prompt_hermes.txt'


function Invoke-Process {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutMinutes = 30,
        [switch]$Force,
        [string]$Agent = 'Loop',
        [string]$Step = 'run',
        [int]$Round = -1
    )
    $display = Format-Command -FilePath $FilePath -Arguments $Arguments
    if ($DryRun -and -not $Force) {
        Write-Host ('DRY RUN: ' + $display)
        Write-Status -Agent $Agent -Step $Step -Round $Round
        return [pscustomobject]@{
            ExitCode = 0
            Output = ('DRY RUN: ' + $display)
            TimedOut = $false
            Stalled = $false
            Command = $display
        }
    }
    $script:StepStarted = Get-Date
    $script:LastActivity = Get-Date
    Write-Status -Agent $Agent -Step $Step -Round $Round
    $request = [pscustomobject]@{
        WorkingDirectory = $Repo
        FilePath = $FilePath
        Arguments = $Arguments
    }
    $job = Start-Job -ScriptBlock {
        param($req)
        Set-Location -LiteralPath $req.WorkingDirectory
        & $req.FilePath @($req.Arguments) 2>&1 | ForEach-Object { $_.ToString() }
        $code = 0
        if ($null -ne $LASTEXITCODE) {
            $code = $LASTEXITCODE
        }
        [pscustomobject]@{ __TeamLoopExitCode = $code }
    } -ArgumentList (,$request)

    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    $lastOutputCount = 0
    $lastGitStatus = Get-GitStatusText
    $lastActivity = Get-Date
    $stalled = $false
    $hardTimeout = $false

    while ($job.State -eq 'Running' -or $job.State -eq 'NotStarted') {
        $finished = Wait-Job -Job $job -Timeout 60
        $outCount = 0
        try {
            if ($job.ChildJobs.Count -gt 0) {
                $outCount = [int]$job.ChildJobs[0].Output.Count
            }
        } catch {
            $outCount = 0
        }
        $gitStatus = Get-GitStatusText
        $active = $false
        if ($outCount -gt $lastOutputCount) {
            $lastOutputCount = $outCount
            $active = $true
        }
        if ($gitStatus -ne $lastGitStatus) {
            $lastGitStatus = $gitStatus
            $active = $true
        }
        if ($active) {
            $lastActivity = Get-Date
        }
        $script:LastActivity = $lastActivity
        Write-Status -Agent $Agent -Step $Step -Round $Round
        if ($finished) {
            break
        }
        if (((Get-Date) - $lastActivity).TotalMinutes -ge 20) {
            $stalled = $true
            break
        }
        if ((Get-Date) -ge $deadline) {
            $hardTimeout = $true
            break
        }
    }

    if ($stalled) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        $reason = 'STALLED: ' + $Agent + ' ' + $Step + ' ' + $Dash + ' no activity for 20 min'
        Write-Status -Agent $Agent -Step $Step -Round $Round -Prefix $reason
        Write-Host $reason
        Stop-Loop $reason
        return [pscustomobject]@{
            ExitCode = -1
            Output = $reason
            TimedOut = $true
            Stalled = $true
            Command = $display
        }
    }

    if ($hardTimeout) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        Write-Host ('TIMEOUT: ' + $display)
        Write-Status -Agent $Agent -Step $Step -Round $Round -Prefix ('TIMEOUT: ' + $Agent + ' ' + $Step)
        return [pscustomobject]@{
            ExitCode = -1
            Output = 'timed out'
            TimedOut = $true
            Stalled = $false
            Command = $display
        }
    }

    $raw = @(Receive-Job -Job $job -ErrorAction SilentlyContinue)
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    Write-Status -Agent $Agent -Step $Step -Round $Round

    $exitCode = -1
    $outputLines = New-Object System.Collections.Generic.List[string]
    foreach ($item in $raw) {
        $prop = $null
        try {
            $prop = $item.PSObject.Properties['__TeamLoopExitCode']
        } catch {
            $prop = $null
        }
        if ($null -ne $prop) {
            $exitCode = [int]$prop.Value
        } else {
            $outputLines.Add([string]$item)
        }
    }
    if ($exitCode -eq -1 -and $outputLines.Count -eq 0) {
        return [pscustomobject]@{
            ExitCode = -1
            Output = 'no output'
            TimedOut = $false
            Stalled = $false
            Command = $display
        }
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($outputLines -join $NewLine)
        TimedOut = $false
        Stalled = $false
        Command = $display
    }
}

function Get-Score {
    $scoreArgs = @($ScoreScript)
    if ($DryRun) {
        Write-Host ('RUN: ' + (Format-Command -FilePath $Python -Arguments $scoreArgs))
    }
    $res = Invoke-Process -FilePath $Python -Arguments $scoreArgs -TimeoutMinutes 30 -Force -Agent 'Score' -Step 'team_score.py' -Round $script:CurrentRound
    if ($res.TimedOut) {
        return [pscustomobject]@{ Failed = $true; Error = 'team_score.py timed out'; ExitCode = -1 }
    }
    if ($res.ExitCode -ne 0) {
        return [pscustomobject]@{
            Failed = $true
            Error = ('team_score.py exited ' + $res.ExitCode + ': ' + $res.Output)
            ExitCode = $res.ExitCode
        }
    }
    $lines = @($res.Output -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
    $parsed = $null
    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        try {
            $parsed = $lines[$i] | ConvertFrom-Json
            break
        } catch {
            $parsed = $null
        }
    }
    if ($null -eq $parsed) {
        return [pscustomobject]@{ Failed = $true; Error = ('could not parse score output: ' + $res.Output); ExitCode = 0 }
    }
    return [pscustomobject]@{ Failed = $false; Score = $parsed; Error = ''; ExitCode = 0 }
}

function Get-PlanFiles {
    param([string]$Path)
    $files = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }
    $inFiles = $false
    foreach ($line in (Get-Content -LiteralPath $Path)) {
        if ($line -match '^\s*##\s+Files\s*$') {
            $inFiles = $true
            continue
        }
        if ($inFiles -and $line -match '^\s*##\s+') {
            break
        }
        if (-not $inFiles) {
            continue
        }
        if ($line -match '^\s*[-*]\s+`([^`]+)`') {
            $files.Add($Matches[1])
            continue
        }
        if ($line -match '^\s*[-*]\s+([^\s(]+)') {
            $files.Add($Matches[1])
        }
    }
    return @($files)
}

function Get-TaskHeading {
    if (-not (Test-Path -LiteralPath $TaskPath)) {
        return 'task'
    }
    foreach ($line in (Get-Content -LiteralPath $TaskPath)) {
        if ($line -match '^#\s+(.+)$') {
            return $Matches[1].Trim()
        }
    }
    return 'task'
}

function Stop-Loop {
    param([string]$Reason)
    if (-not $script:Running) {
        return
    }
    $script:Running = $false
    $script:StopReason = $Reason
    Write-Log -Agent 'Loop' -What ('stopped: ' + $Reason)

    $startText = 'not scored'
    if ($null -ne $script:StartScore) {
        $startText = $script:StartScore | ConvertTo-Json -Compress
    }
    $endText = 'not scored'
    if ($null -ne $script:EndScore) {
        $endText = $script:EndScore | ConvertTo-Json -Compress
    }
    $script:RecapPath = Join-Path (Join-Path $env:USERPROFILE 'Documents') ('Team_Loop_Recap_' + (Get-Date -Format 'yyyyMMdd_HHmm') + '.md')
    $recapLines = New-Object System.Collections.Generic.List[string]
    $recapLines.Add('# Team Loop Recap')
    $recapLines.Add('')
    $recapLines.Add('- Stopped: ' + $Reason)
    $recapLines.Add('- Rounds run: ' + $script:RoundsRun)
    $recapLines.Add('- Commits made: ' + $script:Commits)
    $recapLines.Add('- Start score: ' + $startText)
    $recapLines.Add('- End score: ' + $endText)
    $recapLines.Add('- Open questions for Scott: none recorded by the loop.')
    if ($script:StopFileText) {
        $recapLines.Add('')
        $recapLines.Add('## .team/STOP.md')
        $recapLines.Add('')
        $recapLines.Add($script:StopFileText)
    }
    $recapLines.Add('')
    $recapLines.Add('## Last Claude verdict (first 1500 chars)')
    $recapLines.Add('')
    if ($script:LastClaudeVerdict) {
        $verdictText = $script:LastClaudeVerdict
        if ($verdictText.Length -gt 1500) {
            $verdictText = $verdictText.Substring(0, 1500)
        }
        $recapLines.Add($verdictText)
    } else {
        $recapLines.Add('(none)')
    }
    $recapLines.Add('')
    $recapLines.Add('## Commits this run')
    $recapLines.Add('')
    if ($script:StartHash) {
        $logText = ''
        try {
            $logText = (& $GitExe log --oneline ($script:StartHash + '..HEAD') 2>$null) -join $NewLine
        } catch {
            $logText = ''
        }
        if (-not $logText) {
            $logText = '(none)'
        }
        $recapLines.Add($logText)
    } else {
        $recapLines.Add('(start hash not recorded)')
    }
    $recap = ($recapLines -join $NewLine) + $NewLine
    Write-TextFile -Path $script:RecapPath -Text $recap
    Write-Log -Agent 'Loop' -What 'recap written' -Body $script:RecapPath

    $stoppedAt = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $statusPrefix = 'STOPPED: ' + $Reason + $NewLine + 'Recap: ' + $script:RecapPath + $NewLine + 'Stopped: ' + $stoppedAt
    Write-Status -Agent 'Loop' -Step 'stopped' -Prefix $statusPrefix

    if (-not $DryRun) {
        & $GitExe add -- 'docs/agent_handoffs/TEAM_LOG.md' 2>&1 | Out-Null
        & $GitExe commit -m ('team: loop stop - ' + $Reason) 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $script:Commits++
        }
        Start-Process notepad.exe -ArgumentList @($script:RecapPath)
    } else {
        Write-Host ('DRY RUN: would commit the log and open ' + $script:RecapPath)
    }
    Write-Host ('Stopped: ' + $Reason)
    Write-Host ('Recap: ' + $script:RecapPath)
}

function Undo-PlanFiles {
    param([string[]]$PlanFiles)
    if ($DryRun) {
        Write-Host 'DRY RUN: would roll back the plan files'
        return
    }
    foreach ($f in $PlanFiles) {
        $status = & $GitExe status --porcelain -- $f 2>$null
        if ($status -match '^\?\?') {
            $full = Join-Path $Repo $f
            if (Test-Path -LiteralPath $full) {
                Remove-Item -LiteralPath $full -Force
            }
        } elseif ($status) {
            & $GitExe checkout -- $f 2>$null
        }
    }
}

function Clear-StalePlanFiles {
    $paths = @(
        [pscustomobject]@{ Full = $TaskPath; Rel = 'NEXT_TASK.md'; Name = 'NEXT_TASK.md' },
        [pscustomobject]@{ Full = $StopPath; Rel = '.team/STOP.md'; Name = '.team/STOP.md' }
    )
    foreach ($item in $paths) {
        if (-not (Test-Path -LiteralPath $item.Full)) {
            continue
        }
        $text = Get-Content -LiteralPath $item.Full -Raw
        Write-Log -Agent 'Loop' -What ('clearing stale ' + $item.Name) -Body $text
        if (-not $DryRun) {
            & $GitExe ls-files --error-unmatch -- $item.Rel 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                & $GitExe rm -q --cached -- $item.Rel 2>$null | Out-Null
            }
        }
        Remove-Item -LiteralPath $item.Full -Force
    }
}

function Save-Round {
    param([string[]]$PlanFiles)
    if ($DryRun) {
        Write-Host ('DRY RUN: would git add the plan files plus the log and NEXT_TASK.md, then commit ' + (Get-TaskHeading))
        return $true
    }
    $filesToAdd = New-Object System.Collections.Generic.List[string]
    foreach ($f in $PlanFiles) {
        if ($f) {
            $filesToAdd.Add($f)
        }
    }
    $filesToAdd.Add('docs/agent_handoffs/TEAM_LOG.md')
    if (Test-Path -LiteralPath $TaskPath) {
        $filesToAdd.Add('NEXT_TASK.md')
    }
    $existing = New-Object System.Collections.Generic.List[string]
    foreach ($f in $filesToAdd) {
        if (Test-Path -LiteralPath (Join-Path $Repo $f)) {
            $existing.Add($f)
        }
    }
    $addArgs = @('add', '--') + @($existing)
    $add = Invoke-Process -FilePath $GitExe -Arguments $addArgs -Agent 'Git' -Step 'add' -Round $script:CurrentRound
    if ($add.ExitCode -ne 0) {
        Write-Log -Agent 'Git' -What 'git add failed' -Body $add.Output
        return $false
    }
    $message = 'team: ' + (Get-TaskHeading)
    $commit = Invoke-Process -FilePath $GitExe -Arguments @('commit', '-m', $message) -Agent 'Git' -Step 'commit' -Round $script:CurrentRound
    if ($commit.ExitCode -ne 0) {
        Write-Log -Agent 'Git' -What 'git commit failed' -Body $commit.Output
        return $false
    }
    $script:Commits++
    Write-Log -Agent 'Git' -What 'commit' -Body $message
    return $true
}

function Test-Progress {
    param($Previous, $Current)
    if ($Current.adrian.misses_called_makes -gt 0) {
        return 'regression'
    }
    if (($Current.notus.right -gt $Previous.notus.right) -or ($Current.adrian.right -gt $Previous.adrian.right)) {
        return 'progress'
    }
    return 'none'
}

function Run-Hermes {
    param(
        [string]$Prompt,
        [string]$What
    )
    Write-TextFile -Path $HermesPromptPath -Text $Prompt
    $hermesArgs = @('--exec', 'bash', '-l', $HermesShLinux, $HermesPromptLinux)
    $res = Invoke-Process -FilePath $WslExe -Arguments $hermesArgs -Agent 'Hermes' -Step $What -Round $script:CurrentRound
    if ($DryRun) {
        Write-Log -Agent 'Hermes' -What ('DRY RUN - would ' + $What) -Body (Format-Command -FilePath $WslExe -Arguments $hermesArgs)
    } else {
        Write-Log -Agent 'Hermes' -What $What -Body 'Wrote .team/prompt_hermes.txt and ran hermes chat -q.'
    }
    if ($res.TimedOut) {
        Stop-Loop 'Hermes timed out'
        return $false
    }
    if ($res.ExitCode -ne 0) {
        Stop-Loop ('Hermes failed with exit code ' + $res.ExitCode)
        return $false
    }
    if (-not $DryRun -and $res.Output) {
        Write-Log -Agent 'Hermes' -What 'reply' -Body $res.Output
    }
    return $true
}

function Run-VetPlan {
    $prompt = @'
Read TEAM_RECOVERY.md and CLAUDE.md. You are the Vetter. Vet NEXT_TASK.md against TEAM_RECOVERY.md, CLAUDE.md, AUTHORITY.md, AGENT_OPERATIONAL_PROTOCOL.md, docs/agent_handoffs/ACTIVE.md, OLLAMA.md, and DETECTOR_PROPOSAL_REJECTION.md. Check the Golden Rules: no looser cutoffs, no banned trials, no hard-coded results, and applied_to_core stays false. Stamp the first line of NEXT_TASK.md as VETTED by Claude Code, date: reason, or REJECTED by Claude Code, date: reason. End your reply with a line VERDICT: VETTED or VERDICT: REJECTED.
'@
    $vetArgs = @(
        '-p', $ClaudePromptArg,
        '--allowedTools',
        'Read',
        'Grep',
        'Glob',
        'Bash(git diff:*)',
        'Bash(git log:*)',
        'Edit(NEXT_TASK.md)'
    )
    Write-TextFile -Path $ClaudePromptPath -Text $prompt
    $res = Invoke-Process -FilePath $ClaudeExe -Arguments $vetArgs -Agent 'Claude' -Step 'vet plan' -Round $script:CurrentRound
    if ($DryRun) {
        Write-Log -Agent 'Claude' -What 'DRY RUN - would vet the plan' -Body (Format-Command -FilePath $ClaudeExe -Arguments $vetArgs)
        Write-Host 'DRY RUN: treating the plan as VETTED'
        $script:LastClaudeVerdict = 'DRY RUN: VETTED'
        return 'VETTED'
    }
    Write-Log -Agent 'Claude' -What 'vet plan' -Body 'Ran claude -p to vet NEXT_TASK.md.'
    if ($res.TimedOut) {
        Stop-Loop 'Claude plan vet timed out'
        return $null
    }
    if ($res.ExitCode -ne 0) {
        Stop-Loop ('Claude plan vet failed with exit code ' + $res.ExitCode)
        return $null
    }
    $script:LastClaudeVerdict = $res.Output
    Write-Log -Agent 'Claude' -What 'plan verdict' -Body $res.Output
    if ($res.Output -match 'VERDICT:\s*VETTED') {
        return 'VETTED'
    }
    return 'REJECTED'
}

function Run-VetCode {
    $prompt = @'
Read git diff and git status. Check that only the files in the plan Files section changed. Run the plan tests plus tests/test_ai_bridge.py and tests/test_team_score.py. Run scripts/team_score.py. End your reply with VERDICT: PASS or VERDICT: FAIL: reason.
'@
    $vetArgs = @(
        '-p', $ClaudePromptArg,
        '--allowedTools',
        'Read',
        'Grep',
        'Glob',
        'Bash(git diff:*)',
        'Bash(git status:*)',
        'Bash(.venv/Scripts/python.exe -m pytest:*)',
        'Bash(.venv/Scripts/python.exe scripts/team_score.py)'
    )
    Write-TextFile -Path $ClaudePromptPath -Text $prompt
    $res = Invoke-Process -FilePath $ClaudeExe -Arguments $vetArgs -Agent 'Claude' -Step 'vet code' -Round $script:CurrentRound
    if ($DryRun) {
        Write-Log -Agent 'Claude' -What 'DRY RUN - would vet the code' -Body (Format-Command -FilePath $ClaudeExe -Arguments $vetArgs)
        Write-Host 'DRY RUN: treating the code as PASS'
        $script:LastClaudeVerdict = 'DRY RUN: PASS'
        return [pscustomobject]@{ Verdict = 'PASS'; Reason = '' }
    }
    Write-Log -Agent 'Claude' -What 'vet code' -Body 'Ran claude -p to vet the diff and tests.'
    if ($res.TimedOut) {
        Stop-Loop 'Claude code vet timed out'
        return [pscustomobject]@{ Verdict = 'STOPPED'; Reason = 'timed out' }
    }
    if ($res.ExitCode -ne 0) {
        Stop-Loop ('Claude code vet failed with exit code ' + $res.ExitCode)
        return [pscustomobject]@{ Verdict = 'STOPPED'; Reason = 'failed' }
    }
    $script:LastClaudeVerdict = $res.Output
    Write-Log -Agent 'Claude' -What 'code verdict' -Body $res.Output
    if ($res.Output -match 'VERDICT:\s*PASS') {
        return [pscustomobject]@{ Verdict = 'PASS'; Reason = '' }
    }
    if ($res.Output -match 'VERDICT:\s*FAIL:?\s*(.*)') {
        return [pscustomobject]@{ Verdict = 'FAIL'; Reason = $Matches[1] }
    }
    return [pscustomobject]@{ Verdict = 'FAIL'; Reason = $res.Output }
}

function Run-Code {
    param([string]$Feedback)
    $prompt = @'
Read TEAM_RECOVERY.md and AGENTS.md. You are the Coder. Build NEXT_TASK.md only if it carries a VETTED stamp from Claude Code. Change only the files it names, purely additive, and add the tests it lists. Run the tests with .\.venv\Scripts\python.exe -m pytest the test files the plan lists -q. Do not commit; Claude vets first. Report exactly what you changed.
'@
    if ($Feedback) {
        $safe = $Feedback -replace '[\r\n]+', ' '
        $prompt = $prompt + $NewLine + $NewLine + 'Vetter feedback from the failed attempt: ' + $safe
    }
    Write-TextFile -Path $OpenCodePromptPath -Text $prompt
    $codeArgs = @('run', '-m', 'opencode/deepseek-v4.1-flash-free', $OpenCodePromptArg)
    $res = Invoke-Process -FilePath $OpenCodeExe -Arguments $codeArgs -Agent 'OpenCode' -Step 'code' -Round $script:CurrentRound
    if ($DryRun) {
        Write-Log -Agent 'OpenCode' -What 'DRY RUN - would code' -Body (Format-Command -FilePath $OpenCodeExe -Arguments $codeArgs)
        return [pscustomobject]@{ ExitCode = 0; Output = 'DRY RUN'; TimedOut = $false }
    }
    Write-Log -Agent 'OpenCode' -What 'code' -Body 'Ran opencode run.'
    if ($res.TimedOut) {
        Stop-Loop 'OpenCode timed out'
    } elseif ($res.ExitCode -ne 0) {
        Stop-Loop ('OpenCode failed with exit code ' + $res.ExitCode)
    } elseif ($res.Output) {
        Write-Log -Agent 'OpenCode' -What 'reply' -Body $res.Output
    }
    return $res
}

function Do-Brainstorm {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Log -Agent 'Loop' -What ('brainstorm ' + $stamp)
    if ($DryRun) {
        Write-Host 'DRY RUN: would ask Hermes, OpenCode, and Claude for brainstorm ideas'
        Write-Log -Agent 'Loop' -What 'DRY RUN - brainstorm agent calls skipped'
        return
    }

    $hermesPrompt = @'
You are the Architect. The team is stalled. Read TEAM_RECOVERY.md, AUTHORITY.md, AGENT_OPERATIONAL_PROTOCOL.md, docs/agent_handoffs/ACTIVE.md, and the last 200 lines of docs/agent_handoffs/TEAM_LOG.md. Propose up to 3 ideas that could move the goal in TEAM_RECOVERY.md section 1 forward. For each idea, say why it is not a banned trial or a looser cutoff. Do not edit source files.
'@
    $ideas = New-Object System.Collections.Generic.List[string]

    $ok = Run-Hermes -Prompt $hermesPrompt -What 'brainstorm'
    if (-not $script:Running) { return }
    if ($ok) {
        $ideas.Add('### Hermes')
        $ideas.Add('Hermes brainstorm finished; see the Hermes reply entry above.')
    }

    $openPrompt = @'
Read TEAM_RECOVERY.md and AGENTS.md. The team is stalled. Propose up to 3 ideas that could move the goal in TEAM_RECOVERY.md section 1 forward. For each idea, say why it is not a banned trial or a looser cutoff. Do not edit any files.
'@
    Write-TextFile -Path $OpenCodePromptPath -Text $openPrompt
    $openArgs = @('run', '-m', 'opencode/deepseek-v4.1-flash-free', $OpenCodePromptArg)
    $open = Invoke-Process -FilePath $OpenCodeExe -Arguments $openArgs -Agent 'OpenCode' -Step 'brainstorm' -Round $script:CurrentRound
    Write-Log -Agent 'OpenCode' -What 'brainstorm' -Body 'Ran opencode run for brainstorm ideas.'
    if ($open.TimedOut) {
        Stop-Loop 'OpenCode brainstorm timed out'
        return
    }
    if ($open.ExitCode -ne 0) {
        Stop-Loop ('OpenCode brainstorm failed with exit code ' + $open.ExitCode)
        return
    }
    $ideas.Add('### OpenCode')
    $ideas.Add($open.Output)

    $claudePrompt = @'
Read TEAM_RECOVERY.md, AGENT_OPERATIONAL_PROTOCOL.md, AUTHORITY.md, OLLAMA.md, and docs/agent_handoffs/ACTIVE.md. The team is stalled. Propose up to 3 ideas that could move the goal in TEAM_RECOVERY.md section 1 forward. For each idea, say why it is not a banned trial or a looser cutoff. Mark any idea that breaks the Golden Rules as REJECTED.
'@
    $claudeArgs = @(
        '-p', $ClaudePromptArg,
        '--allowedTools',
        'Read',
        'Grep',
        'Glob'
    )
    Write-TextFile -Path $ClaudePromptPath -Text $claudePrompt
    $claude = Invoke-Process -FilePath $ClaudeExe -Arguments $claudeArgs -Agent 'Claude' -Step 'brainstorm' -Round $script:CurrentRound
    Write-Log -Agent 'Claude' -What 'brainstorm' -Body 'Ran claude -p for brainstorm ideas.'
    if ($claude.TimedOut) {
        Stop-Loop 'Claude brainstorm timed out'
        return
    }
    if ($claude.ExitCode -ne 0) {
        Stop-Loop ('Claude brainstorm failed with exit code ' + $claude.ExitCode)
        return
    }
    $script:LastClaudeVerdict = $claude.Output
    $ideas.Add('### Claude')
    $ideas.Add($claude.Output)

    $entry = $NewLine + '## Brainstorm ' + $stamp + $NewLine + ($ideas -join $NewLine) + $NewLine
    [System.IO.File]::AppendAllText($LogPath, $entry, $Utf8NoBom)
}


# --- Start ---------------------------------------------------------------

$branch = (& $GitExe rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'team/auto') {
    & $GitExe show-ref --verify --quiet 'refs/heads/team/auto' 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $GitExe switch 'team/auto' 2>&1 | Out-Null
    } else {
        & $GitExe switch -c 'team/auto' 2>&1 | Out-Null
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Could not switch to team/auto; refusing to run.'
        exit 1
    }
    $branch = (& $GitExe rev-parse --abbrev-ref HEAD).Trim()
}
if ($branch -eq 'main') {
    Write-Error 'Refusing to run on main. Work must happen on team/auto.'
    exit 1
}

$script:StartHash = (& $GitExe rev-parse HEAD).Trim()
if (-not (Test-Path -LiteralPath $TeamDir)) {
    New-Item -ItemType Directory -Path $TeamDir -Force | Out-Null
}
if (Test-Path -LiteralPath $TaskPath) {
    Write-Log -Agent 'Loop' -What 'moved existing NEXT_TASK.md to .team/previous_NEXT_TASK.md' -Body 'The previous task file was moved aside so a stale plan cannot be reused. Its full text is at .team/previous_NEXT_TASK.md.'
    Move-Item -LiteralPath $TaskPath -Destination $PreviousTaskPath -Force
}

Write-Log -Agent 'Loop' -What 'start' -Body ('Branch: ' + $branch + ' | DryRun: ' + [bool]$DryRun + ' | MaxRounds: ' + $MaxRounds)
Write-Status -Agent 'Loop' -Step 'start' -Round 0

$baseline = Get-Score
if ($baseline.Failed) {
    Stop-Loop ('baseline score failed: ' + $baseline.Error)
    exit 0
}
$script:StartScore = $baseline.Score
$previous = $baseline.Score
Write-Log -Agent 'Score' -What 'baseline' -Body ($baseline.Score | ConvertTo-Json -Compress)

$noProgress = 0

for ($round = 1; $round -le $MaxRounds; $round++) {
    if (-not $script:Running) {
        break
    }
    $script:RoundsRun = $round
    $script:CurrentRound = $round
    Write-Status -Agent 'Loop' -Step ('round ' + $round) -Round $round
    Write-Log -Agent 'Loop' -What ('round ' + $round)

    $roundFiles = @()
    $planAccepted = $false
    $rejections = 0
    $cannotReachBrainstormed = $false

    while (-not $planAccepted) {
        if (-not $script:Running) {
            break
        }

        $hermesPrompt = @'
Work in /mnt/c/Users/scott/Documents/liberty-basketball-analysis. Read TEAM_RECOVERY.md first, then AUTHORITY.md, AGENT_OPERATIONAL_PROTOCOL.md, docs/agent_handoffs/ACTIVE.md, docs/agent_handoffs/HERMES.md, and the git log. You are the Architect. Choose the single smallest additive task that moves the goal in TEAM_RECOVERY.md section 1 forward, obeys the Golden Rules, and crosses no Scott gate. Write it, with the exact files to change and the tests to add, to NEXT_TASK.md. Quote numbers only from commands you ran. If no task fits, do not write NEXT_TASK.md; say why. Do not edit source files.

Read the last 200 lines of docs/agent_handoffs/TEAM_LOG.md.

Include a ## Files section listing every file to change.

If the goal is reached or no task fits, write .team/STOP.md whose first line is exactly one of GOAL_REACHED, SCOTT_GATE, CANNOT_REACH, followed by the reason, instead of NEXT_TASK.md.
'@
        Clear-StalePlanFiles
        $planned = Run-Hermes -Prompt $hermesPrompt -What 'plan'
        if (-not $script:Running) {
            break
        }
        if (-not $planned) {
            break
        }

        if (Test-Path -LiteralPath $StopPath) {
            $firstLine = Get-Content -LiteralPath $StopPath -TotalCount 1
            $first = ''
            if ($null -ne $firstLine) {
                $first = $firstLine.Trim()
            }
            $body = Get-Content -LiteralPath $StopPath -Raw
            if ($null -eq $body) {
                $body = ''
            }
            Write-Log -Agent 'Hermes' -What ('STOP ' + $first) -Body $body
            if ($first -eq 'GOAL_REACHED' -or $first -eq 'SCOTT_GATE') {
                $script:StopFileText = $body
                Stop-Loop $first
                break
            }
            if ($first -eq 'CANNOT_REACH') {
                if ($cannotReachBrainstormed) {
                    $script:StopFileText = $body
                    Stop-Loop 'CANNOT_REACH after brainstorm'
                    break
                }
                Do-Brainstorm
                $cannotReachBrainstormed = $true
                continue
            }
            $script:StopFileText = $body
            Stop-Loop ('unknown STOP marker: ' + $first)
            break
        }

        if (-not (Test-Path -LiteralPath $TaskPath)) {
            if ($DryRun) {
                Write-Log -Agent 'Loop' -What 'DRY RUN - no NEXT_TASK.md because Hermes was not called; continuing with an empty plan'
            } else {
                Stop-Loop 'Hermes wrote no NEXT_TASK.md and no .team/STOP.md'
                break
            }
        }

        $planFiles = @(Get-PlanFiles -Path $TaskPath)
        if ($planFiles.Count -eq 0) {
            Write-Log -Agent 'Claude' -What 'plan has no Files section'
        }

        $verdict = Run-VetPlan
        if (-not $script:Running) {
            break
        }
        if ($null -eq $verdict) {
            break
        }
        if ($verdict -eq 'VETTED') {
            $planAccepted = $true
            $roundFiles = $planFiles
            break
        }

        $rejections++
        Write-Log -Agent 'Claude' -What ('plan rejected (' + $rejections + ' of 2)')
        if ($rejections -ge 2) {
            Do-Brainstorm
            if (-not $script:Running) {
                break
            }
            $rejections = 0
        }
    }

    if (-not $script:Running -or -not $planAccepted) {
        break
    }

    $codeAccepted = $false
    $codeTries = 0
    $feedback = ''
    while (-not $codeAccepted) {
        if (-not $script:Running) {
            break
        }
        $codeResult = Run-Code -Feedback $feedback
        if (-not $script:Running) {
            break
        }
        if ($null -eq $codeResult -or $codeResult.ExitCode -ne 0) {
            break
        }

        $codeVerdict = Run-VetCode
        if (-not $script:Running) {
            break
        }
        if ($null -eq $codeVerdict -or $codeVerdict.Verdict -eq 'STOPPED') {
            break
        }
        if ($codeVerdict.Verdict -eq 'PASS') {
            $codeAccepted = $true
            break
        }

        $codeTries++
        Write-Log -Agent 'Claude' -What ('code rejected (' + $codeTries + ' of 2)') -Body $codeVerdict.Reason
        if ($codeTries -ge 2) {
            Undo-PlanFiles -PlanFiles $roundFiles
            Write-Log -Agent 'Git' -What 'rolled back plan files'
            break
        }
        $feedback = $codeVerdict.Reason
    }

    if (-not $script:Running) {
        break
    }

    if ($codeAccepted) {
        if (-not (Save-Round -PlanFiles $roundFiles)) {
            Stop-Loop 'git add or commit failed'
            break
        }
    } else {
        Write-Log -Agent 'Loop' -What 'round counted as no progress'
    }

    $current = Get-Score
    if ($current.Failed) {
        Stop-Loop ('score failed: ' + $current.Error)
        break
    }
    $script:EndScore = $current.Score
    Write-Log -Agent 'Score' -What ('round ' + $round + ' end') -Body ($current.Score | ConvertTo-Json -Compress)

    if ($current.Score.goal_reached) {
        Stop-Loop 'GOAL_REACHED'
        break
    }
    if ($current.Score.adrian.misses_called_makes -gt 0) {
        Stop-Loop ('regression: Adrian misses called makes = ' + $current.Score.adrian.misses_called_makes)
        break
    }

    $progress = Test-Progress -Previous $previous -Current $current.Score
    if ($progress -eq 'progress') {
        $noProgress = 0
    } else {
        $noProgress++
    }
    $previous = $current.Score

    if ($noProgress -ge $MaxNoProgress) {
        Stop-Loop ('no progress for ' + $MaxNoProgress + ' rounds')
        break
    }

    if ($DryRun) {
        Write-Log -Agent 'Loop' -What 'DRY RUN - would clear STOP.md and NEXT_TASK.md'
        Stop-Loop 'dry run completed round 1'
        break
    }

    if ($codeAccepted) {
        if (Test-Path -LiteralPath $StopPath) {
            Remove-Item -LiteralPath $StopPath -Force
        }
        if (Test-Path -LiteralPath $TaskPath) {
            Remove-Item -LiteralPath $TaskPath -Force
        }
        Write-Log -Agent 'Loop' -What 'cleared STOP.md and NEXT_TASK.md'
    }
}

if ($script:Running) {
    Stop-Loop ('MaxRounds ' + $MaxRounds + ' reached')
}

exit 0
