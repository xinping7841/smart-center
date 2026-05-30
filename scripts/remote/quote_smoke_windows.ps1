$ErrorActionPreference = "Stop"

Write-Host "WIN_QUOTE_SMOKE_START"

$payload = [ordered]@{
  brace = "{1,2,3}"
  pipe = "a|b|c"
  quote = "a'b`"c"
  unicode = "中文"
}

$json = $payload | ConvertTo-Json -Compress
Write-Host "json=$json"
"alpha", "beta" | ForEach-Object { Write-Host "pipe:$_" }
Write-Host ("single={0} double={1}" -f "a'b", 'c"d')
Write-Host ("cwd={0}" -f (Get-Location).Path)

Write-Host "WIN_QUOTE_SMOKE_DONE"
