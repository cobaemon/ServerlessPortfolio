# 依存関係の手動デプロイスクリプト
# 通常は CodePipeline から自動デプロイされるため使用する必要はありません。
# 既存のCloudFront Origin Access Control と S3 バケットを検出して再利用します。

param(
    [string]$Env = "prod",
    [string]$StackName = "cobaemon-portfolio-dependencies-prod",
    [string]$Profile = "aws_portfolio_profile"
)

Write-Host "=== 依存関係の自動デプロイを開始 ===" -ForegroundColor Green

# 既存のOACとバケットを検索
$oacName = "OAC-for-cobaemon-serverless-portfolio-$Env-static"
$bucketName = "cobaemon-serverless-portfolio-$Env-static"
Write-Host "既存のCloudFront Origin Access Controlを検索中: $oacName" -ForegroundColor Yellow
Write-Host "既存のS3バケットを検索中: $bucketName" -ForegroundColor Yellow

try {
    # AWS CLIで既存のOAC一覧を取得
    $oacList = aws cloudfront list-origin-access-controls --profile $Profile --output json | ConvertFrom-Json

    # 環境に応じたOAC名でマッチング
    $existingOAC = $oacList.OriginAccessControlList.Items | Where-Object { $_.Name -eq $oacName }

    # 既存のS3バケットがあるか確認
    aws s3api head-bucket --bucket $bucketName --profile $Profile 2>$null
    if ($LASTEXITCODE -eq 0) {
        $existingBucketName = $bucketName
        Write-Host "既存のS3バケットを発見: $existingBucketName" -ForegroundColor Green
    } else {
        $existingBucketName = $null
        Write-Host "S3バケットは存在しません。新規作成します" -ForegroundColor Yellow
    }
    
    $paramOverrides = "Env=$Env"
    if ($existingOAC) {
        Write-Host "既存のOACを発見: $($existingOAC.Id)" -ForegroundColor Green
        Write-Host "既存のOACを再利用してデプロイします..." -ForegroundColor Cyan
        $paramOverrides += " ExistingOACId=$($existingOAC.Id)"
    } else {
        Write-Host "既存のOACが見つからないため、新規作成します" -ForegroundColor Yellow
    }

    if ($existingBucketName) {
        Write-Host "既存のS3バケットを再利用してデプロイします..." -ForegroundColor Cyan
        $paramOverrides += " ExistingStaticBucketName=$existingBucketName"
    }

    $deployCommand = "sam deploy --template-file dependencies.yaml --stack-name $StackName --parameter-overrides $paramOverrides --capabilities CAPABILITY_IAM --profile $Profile"
    
    Write-Host "実行コマンド: $deployCommand" -ForegroundColor Cyan
    Invoke-Expression $deployCommand
    
    Write-Host "=== デプロイ完了 ===" -ForegroundColor Green
    
} catch {
    Write-Host "エラーが発生しました: $_" -ForegroundColor Red
    Write-Host "手動でデプロイしてください" -ForegroundColor Yellow
    exit 1
} 
