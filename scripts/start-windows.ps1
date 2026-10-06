$ErrorActionPreference = "Stop"

$appName = "pm-app"
$imageName = "pm-app"
$rootDir = Resolve-Path "$PSScriptRoot\.."

docker build -t $imageName $rootDir

docker rm -f $appName *>$null

docker run --name $appName --env-file "$rootDir\.env" -v pm-data:/app/backend/data -p 8000:8000 $imageName
