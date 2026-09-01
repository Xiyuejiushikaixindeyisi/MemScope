param([string]$BaseUrl = "http://127.0.0.1:8080")
$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
$Sample = Get-Content (Join-Path $RootDir "smoke/sample_locomo_style.json") -Raw | ConvertFrom-Json
Invoke-WebRequest "$BaseUrl/health" -UseBasicParsing | Out-Null
$Session = $Sample.add_phase.sessions[0]
$Add = @{
  request_id = "smoke:locomo:chunk-0"
  user_id = $Sample.isolation.user_id
  session_id = $Session.session_id
  messages = $Session.messages
} | ConvertTo-Json -Depth 20
Invoke-RestMethod "$BaseUrl/add" -Method Post -ContentType "application/json" -Body $Add | ConvertTo-Json -Depth 20
$Item = $Sample.search_items[0]
$Search = @{query=$Item.question; user_id=$Sample.isolation.user_id; top_k=100} | ConvertTo-Json
Invoke-RestMethod "$BaseUrl/search" -Method Post -ContentType "application/json" -Body $Search | ConvertTo-Json -Depth 20
