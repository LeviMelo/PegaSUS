$Root = "C:\Users\Galaxy\LEVI\projects\PegaSUS"
$Dirs = @(
  "src\pegasus_data\config",
  "src\pegasus_data\common",
  "src\pegasus_data\datasus\discovery",
  "src\pegasus_data\datasus\ftp",
  "src\pegasus_data\datasus\inventory",
  "src\pegasus_data\datasus\decode",
  "src\pegasus_data\datasus\profile",
  "src\pegasus_data\datasus\translate",
  "src\pegasus_data\datasus\fetch",
  "src\pegasus_data\datasus\parsers",
  "src\pegasus_data\sidra\catalog",
  "src\pegasus_data\sidra\values",
  "src\pegasus_data\pegasus\canonical",
  "src\pegasus_data\pegasus\registry",
  "src\pegasus_data\pegasus\compiler",
  "scripts",
  "data\raw\datasus\ftp",
  "data\cache",
  "data\catalog",
  "data\compiled\sidra",
  "tests"
)
foreach ($dir in $Dirs) {
  New-Item -ItemType Directory -Path (Join-Path $Root $dir) -Force | Out-Null
}
