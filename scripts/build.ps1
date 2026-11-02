param([Parameter(Mandatory=$true)][string]$Name,[int]$Seed=2,[switch]$Tpg)
$ErrorActionPreference="Stop"
$cmdArgs=@((Join-Path $PSScriptRoot "build.py"),"--name",$Name,"--seed",$Seed)
if($Tpg){ $cmdArgs+="--tpg" }
& "C:\Users\肖永康\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" @cmdArgs
exit $LASTEXITCODE
