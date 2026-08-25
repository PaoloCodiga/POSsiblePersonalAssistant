Write-Warning 'This deletes all PPA development data.'
$answer = Read-Host 'Type RESET to continue'
if ($answer -eq 'RESET') { docker compose down -v; docker compose up -d }
