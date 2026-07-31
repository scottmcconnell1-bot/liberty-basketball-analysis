$path = Resolve-Path "scripts\daily_git_save.ps1"
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($path.Path, [ref]$tokens, [ref]$errors)
if ($errors -and $errors.Count -gt 0) {
  $errors | ForEach-Object { $_.ToString() }
  exit 1
}
Write-Output "PARSE_OK"
