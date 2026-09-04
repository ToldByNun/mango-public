# Install Mango Studio plugin into the local Roblox Plugins folder.
# Studio loads *.lua (and .rbxm) from PluginsDir — NOT *.luau.
# Run from anywhere; resolves paths relative to this script.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here "plugin\src\MangoPlugin.luau"
if (-not (Test-Path $src)) {
    # Fall back if renamed to .lua in repo
    $src = Join-Path $here "plugin\src\MangoPlugin.lua"
}
if (-not (Test-Path $src)) {
    throw "Plugin source not found under plugin\src\"
}

# Prefer Studio's configured PluginsDir when available
$plugins = Join-Path $env:LOCALAPPDATA "Roblox\Plugins"
$settings = Join-Path $env:LOCALAPPDATA "Roblox\GlobalSettings_13.xml"
if (Test-Path $settings) {
    $xml = Get-Content -Raw $settings
    if ($xml -match 'name="PluginsDir">([^<]+)<') {
        $configured = $Matches[1].Trim() -replace '/', '\'
        if ($configured) { $plugins = $configured }
    }
}

New-Item -ItemType Directory -Force -Path $plugins | Out-Null

# Remove stale .luau copy — Studio ignores it as a local plugin
$stale = Join-Path $plugins "MangoPlugin.luau"
if (Test-Path $stale) {
    Remove-Item -Force $stale
    Write-Host "Removed stale: $stale (Studio does not load .luau plugins)"
}

$dest = Join-Path $plugins "MangoPlugin.lua"
Copy-Item -Force $src $dest
Write-Host "Installed: $dest"
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Fully quit Roblox Studio (File > Quit), then reopen."
Write-Host "  2. Plugins tab should show a 'Mango' toolbar button."
Write-Host "  3. Start the host: MangoStudio.cmd or Start-StudioHost.cmd"
Write-Host "  4. If still missing: Plugins > Manage Plugins, or check Output for errors."
