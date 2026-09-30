# Optional external checker -- run this on YOUR OWN Windows machine (must be
# on WPI VPN) via Task Scheduler every 15 minutes, as a supplement to the
# on-VM watchdog. It catches the case the on-VM watchdog cannot: the whole
# VM being unreachable (wiped, powered off, network-partitioned).
#
# Task Scheduler setup:
#   schtasks /create /tn "GenreVMHealthCheck" /tr "powershell.exe -File D:\CS553\musical_genre_illustrator-main\deploy\external_healthcheck.ps1" /sc minute /mo 15
#
# Requires: ssh.exe (OpenSSH client, built into modern Windows) and a
# Discord webhook URL set in $DiscordWebhookUrl below (or as an env var).

$VmHost = "paffenroth-23.dyn.wpi.edu"
$VmPort = 22012
$VmUser = "student-admin"
$KeyPath = "D:\CS553\tmp\mykey"
$DiscordWebhookUrl = $env:DISCORD_WEBHOOK_URL
$StateFile = "$PSScriptRoot\.external_healthcheck.state"

function Notify-Discord($msg) {
    if (-not $DiscordWebhookUrl) { return }
    try {
        Invoke-RestMethod -Uri $DiscordWebhookUrl -Method Post -ContentType "application/json" `
            -Body (@{content = $msg } | ConvertTo-Json) | Out-Null
    } catch {}
}

$prevState = "unknown"
if (Test-Path $StateFile) { $prevState = Get-Content $StateFile -Raw }

$result = & ssh -i $KeyPath -p $VmPort -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new `
    "$VmUser@$VmHost" "systemctl is-active genre-api.service genre-local.service" 2>&1

if ($LASTEXITCODE -ne 0) {
    Set-Content -Path $StateFile -Value "down"
    if ($prevState -ne "down") {
        Notify-Discord "🔴 **External check**: cannot reach the VM at all (SSH failed). It may need to be redeployed from scratch via deploy.sh."
    }
} else {
    Set-Content -Path $StateFile -Value "up"
    if ($prevState -eq "down") {
        Notify-Discord "✅ **External check**: VM is reachable again via SSH."
    }
    Write-Output $result
}
