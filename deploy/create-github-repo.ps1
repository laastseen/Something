# Создаёт репозиторий на GitHub и пушит код.
# Нужен токен: https://github.com/settings/tokens/new?scopes=repo&description=Something-deploy
#   setx GH_TOKEN "ghp_..."   (перезапустите терминал)
#   или: $env:GH_TOKEN = "ghp_..."

param(
    [string]$RepoName = "something-media",
    [string]$Visibility = "public"
)

$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path "$root\.git")) { $root = Split-Path $PSScriptRoot -Parent }
$git = "C:\Program Files\Git\bin\git.exe"
if (-not (Test-Path $git)) { $git = "git" }

$token = $env:GH_TOKEN
if (-not $token) { $token = $env:GITHUB_TOKEN }
if (-not $token) {
    Write-Host "Нет GH_TOKEN. Создайте токен: https://github.com/settings/tokens/new?scopes=repo"
    Write-Host 'Затем: $env:GH_TOKEN = "ghp_ваш_токен"'
    exit 1
}

$headers = @{
    Authorization = "Bearer $token"
    Accept        = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$user = Invoke-RestMethod -Uri "https://api.github.com/user" -Headers $headers
Write-Host "GitHub: $($user.login)"

$body = @{ name = $RepoName; private = ($Visibility -eq "private"); auto_init = $false } | ConvertTo-Json
try {
    $repo = Invoke-RestMethod -Method Post -Uri "https://api.github.com/user/repos" -Headers $headers -Body $body -ContentType "application/json"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 422) {
        $repo = Invoke-RestMethod -Uri "https://api.github.com/repos/$($user.login)/$RepoName" -Headers $headers
        Write-Host "Репозиторий уже существует, пушим в него."
    } else { throw }
}

$remoteUrl = "https://$($user.login):$token@github.com/$($user.login)/$RepoName.git"
Push-Location $root
& $git remote remove origin 2>$null
& $git remote add origin $remoteUrl
& $git push -u origin main
& $git remote set-url origin "https://github.com/$($user.login)/$RepoName.git"
Pop-Location

Write-Host ""
Write-Host "Готово: $($repo.html_url)"
Write-Host "Деплой на VPS:"
Write-Host "  bash deploy/setup-server.sh $($repo.clone_url)"
