# 依存関係の自動デプロイスクリプト
# 既存のCloudFront Origin Access Controlを自動検出して再利用します

param(
    [string]$Env = "prod",
    [string]$StackName = "cobaemon-portfolio-dependencies-prod",
    [string]$Profile = "aws_portfolio_profile"
)

Write-Host "=== 依存関係の自動デプロイを開始 ===" -ForegroundColor Green

# 既存のOACを検索
$oacName = "OAC-for-cobaemon-serverless-portfolio-$Env-static"
Write-Host "既存のCloudFront Origin Access Controlを検索中: $oacName" -ForegroundColor Yellow

try {
    # AWS CLIで既存のOAC一覧を取得
    $oacList = aws cloudfront list-origin-access-controls --profile $Profile --output json | ConvertFrom-Json
    
    # 環境に応じたOAC名でマッチング
    $existingOAC = $oacList.OriginAccessControlList.Items | Where-Object { $_.Name -eq $oacName }
    
    if ($existingOAC) {
        Write-Host "既存のOACを発見: $($existingOAC.Id)" -ForegroundColor Green
        Write-Host "既存のOACを再利用してデプロイします..." -ForegroundColor Cyan
        
        # 既存OAC IDを指定してデプロイ
        $deployCommand = "sam deploy --template-file dependencies.yaml --stack-name $StackName --parameter-overrides Env=$Env ExistingOACId=$($existingOAC.Id) --capabilities CAPABILITY_IAM --profile $Profile"
    } else {
        Write-Host "既存のOACが見つからないため、新規作成します" -ForegroundColor Yellow
        
        # 新規作成でデプロイ
        $deployCommand = "sam deploy --template-file dependencies.yaml --stack-name $StackName --parameter-overrides Env=$Env --capabilities CAPABILITY_IAM --profile $Profile"
    }
    
    Write-Host "実行コマンド: $deployCommand" -ForegroundColor Cyan
    Invoke-Expression $deployCommand
    
    Write-Host "=== デプロイ完了 ===" -ForegroundColor Green
    
} catch {
    Write-Host "エラーが発生しました: $_" -ForegroundColor Red
    Write-Host "手動でデプロイしてください" -ForegroundColor Yellow
    exit 1
} 