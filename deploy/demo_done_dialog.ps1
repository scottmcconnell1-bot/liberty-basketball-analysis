# Liberty Demo — blocking DONE dialog for coaches.
# Exit 0 when DONE is clicked (or form closed). Exit 1 on failure so the bat can fall back.
param(
    [string]$Url = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Liberty Basketball Demo"
    $form.ClientSize = New-Object System.Drawing.Size(460, 200)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true
    $form.ShowInTaskbar = $true

    $label = New-Object System.Windows.Forms.Label
    $label.Text = "Liberty Demo is running at $Url`r`n`r`nClick DONE to stop the server and uninstall all demo files."
    $label.Location = New-Object System.Drawing.Point(24, 20)
    $label.Size = New-Object System.Drawing.Size(412, 72)
    $label.Font = New-Object System.Drawing.Font("Segoe UI", 11)
    $form.Controls.Add($label)

    $btn = New-Object System.Windows.Forms.Button
    $btn.Text = "DONE"
    $btn.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
    $btn.Size = New-Object System.Drawing.Size(220, 56)
    $btn.Location = New-Object System.Drawing.Point(120, 110)
    $btn.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.Add($btn)
    $form.AcceptButton = $btn

    [void]$form.ShowDialog()
    $form.Dispose()
    exit 0
}
catch {
    Write-Host ("DONE dialog failed: " + $_.Exception.Message)
    exit 1
}
