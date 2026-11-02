param([switch]$Quick)
$ErrorActionPreference="Stop"
$cmdArgs=@((Join-Path $PSScriptRoot "verify_all.py"))
if($Quick){ $cmdArgs+="--quick" }
& "C:\Users\肖永康\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" @cmdArgs
exit $LASTEXITCODE
