<#>
.SYNOPSIS
    Aider invocation guard for liberty-basketball-analysis (PowerShell version)
    
.DESCRIPTION
    Prevents common Aider invocation errors:
    - --msg-file (not a valid Aider flag) -> suggests --message-file
    - Malformed pytest -k expressions passed as positional args
    - Missing --message-file when using --message
    
.USAGE
    powershell -File scripts\aider_guard.ps1 [AIDER_ARGS...]
    # Example: powershell -File scripts\aider_guard.ps1 --message-file MSG.md -- -k "not test_foo"
#>

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$VALID_AIDER_FLAGS = @(
    '--message', '-m',
    '--message-file',
    '--file', '-f',
    '--read', '-r',
    '--yes', '-y',
    '--no-auto-commits',
    '--commit',
    '--no-commit',
    '--dry-run',
    '--verbose', '-v',
    '--model',
    '--weak-model',
    '--editor-model',
    '--show-model-warnings',
    '--no-show-model-warnings',
    '--stream',
    '--no-stream',
    '--pretty',
    '--no-pretty',
    '--chat-language',
    '--encoding',
    '--config',
    '--no-config',
    '--load', '-l',
    '--save', '-s',
    '--exit', '-x',
    '--no-input-history',
    '--no-git',
    '--git',
    '--git-ignore',
    '--show-diffs',
    '--no-show-diffs',
    '--attribute-author',
    '--no-attribute-author',
    '--attribute-committer',
    '--no-attribute-committer',
    '--attribute-commit-message-author',
    '--no-attribute-commit-message-author',
    '--commit-message-author',
    '--commit-message-committer'
)

$INVALID_FLAGS = @{
    '--msg-file' = '--message-file'
    '--msg' = '--message'
    '--commit-msg' = '--message'
    '--pytest' = $null  # pytest args go AFTER --
}

function Validate-AiderArgs {
    param([string[]]$InputArgs)
    
    $corrected = @()
    $i = 0
    
    while ($i -lt $InputArgs.Count) {
        $arg = $InputArgs[$i]
        
        # Check for known invalid flags
        if ($INVALID_FLAGS.ContainsKey($arg)) {
            $suggestion = $INVALID_FLAGS[$arg]
            if ($suggestion) {
                Write-Error "Invalid flag: $arg. Did you mean $suggestion?"
                return $null
            } else {
                Write-Error "Invalid flag: $arg. pytest -k expressions go after '--' separator."
                return $null
            }
        }
        
        # Check for pytest -k expressions mistakenly passed as positional args
        if ($arg -match '^-k' -or $arg -match '^--keyword') {
            Write-Error "pytest argument $arg must come after '--' separator (e.g., aider ... -- -k 'not test_foo')"
            return $null
        }
        
        # Validate known flags have their required values
        $flagsWithValues = @('--message', '-m', '--message-file', '--file', '-f', '--read', '-r', 
                             '--model', '--weak-model', '--editor-model', '--chat-language', 
                             '--encoding', '--config', '--load', '-l', '--save', '-s')
        
        if ($flagsWithValues -contains $arg) {
            if ($i + 1 -ge $InputArgs.Count) {
                Write-Error "Flag $arg requires a value"
                return $null
            }
            $corrected += $arg
            $corrected += $InputArgs[$i + 1]
            $i += 2
            continue
        }
        
        # Boolean flags
        if ($arg -match '^--' -or $arg -match '^-') {
            if ($VALID_AIDER_FLAGS -notcontains $arg -and $arg -notmatch '^--') {
                # Warn but don't block
                Write-Warning "Unknown flag: $arg (passing through)"
            }
        }
        
        $corrected += $arg
        $i++
    }
    
    return $corrected
}

# Split at -- separator
$separatorIndex = $Args.IndexOf('--')
if ($separatorIndex -ge 0) {
    $aiderArgs = $Args[0..($separatorIndex - 1)]
    $pytestArgs = $Args[($separatorIndex + 1)..$Args.Count]
} else {
    $aiderArgs = $Args
    $pytestArgs = @()
}

# Validate Aider args
$validatedArgs = Validate-AiderArgs -InputArgs $aiderArgs
if ($null -eq $validatedArgs) {
    exit 2
}

# Build command
$cmd = @('aider') + $validatedArgs
if ($pytestArgs.Count -gt 0) {
    $cmd += '--'
    $cmd += $pytestArgs
}

Write-Host "[AIDER GUARD] Running: $($cmd -join ' ')"

# Execute
& $cmd
exit $LASTEXITCODE