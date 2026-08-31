# Install Mango Studio plugin into the local Roblox Plugins folder.
# Run from anywhere; resolves paths relative to this script.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here "plugin\src\MangoPlugin.luau"
if (-not (Test-Path $src)) {
    throw "Plugin source not found: $src"
}

$plugins = Join-Path $env:LOCALAPPDATA "Roblox\Plugins"
New-Item -ItemType Directory -Force -Path $plugins | Out-Null
$dest = Join-Path $plugins "MangoPlugin.luau"
Copy-Item -Force $src $dest
Write-Host "Installed: $dest"
Write-Host "Restart Roblox Studio (or reload plugins) and open the Mango toolbar button."
Write-Host "Then start the host: .\Start-StudioHost.ps1"
