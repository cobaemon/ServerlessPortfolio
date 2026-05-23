<#
.SYNOPSIS
Finalizes the current vA.B.C work branch, merges it into dev, and switches to vA.B.(C+1).

.DESCRIPTION
This script is a guarded Git workflow for Codex-assisted branch finalization.
It performs the following operations only after explicit confirmation:

1. Validate that the current branch is vA.B.C.
2. Compute the next branch by incrementing only C.
3. Stop if the next branch already exists.
4. Stop if protected source-of-truth documents are changed.
5. Commit uncommitted changes only when changes exist.
6. Generate a commit message with title, purpose, summary, scope, branch processing, and verification notes.
7. Switch to dev and merge the source branch with --no-ff.
8. Create and switch to the next work branch from dev.

This script intentionally does not push, force-push, rebase, reset --hard, clean, squash merge,
use --no-verify, or overwrite existing branches.

.PARAMETER ConfirmExecution
Required explicit execution switch. The script stops unless this switch is provided.

.PARAMETER IntegrationBranch
The integration branch. Defaults to dev.

.EXAMPLE
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\branch-finalize-next.ps1 -ConfirmExecution
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$ConfirmExecution,

    [Parameter(Mandatory = $false)]
    [ValidatePattern('^[A-Za-z0-9._/-]+$')]
    [Alias('MainBranch')]
    [string]$IntegrationBranch = 'dev'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$ProtectedPaths = @(
    '.kiro/specs/kaguya-project/requirements.md',
    '.kiro/specs/kaguya-project/requirements_source.txt',
    '.kiro/specs/kaguya-project/design.md',
    '.kiro/specs/kaguya-project/overall_design_source.txt',
    '.kiro/specs/kaguya-project/detailed_design_source.txt',
    '.kiro/specs/kaguya-project/tasks.md'
)

function Invoke-GitCommand {
    <#
    .SYNOPSIS
    Runs a Git command and stops when Git returns a non-zero exit code.

    .PARAMETER GitArguments
    Arguments passed to the git executable.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArguments
    )

    $output = & git @GitArguments 2>&1
    $exitCode = $LASTEXITCODE

    if ($output) {
        $output | ForEach-Object { Write-Output ([string]$_) }
    }

    if ($exitCode -ne 0) {
        throw "STOP: git $($GitArguments -join ' ') failed with exit code $exitCode."
    }
}

function Invoke-GitOutput {
    <#
    .SYNOPSIS
    Runs a Git command and returns stdout/stderr as output lines.

    .PARAMETER GitArguments
    Arguments passed to the git executable.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArguments
    )

    $output = & git @GitArguments 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        $joinedOutput = (($output | ForEach-Object { [string]$_ }) -join "`n").Trim()
        throw "STOP: git $($GitArguments -join ' ') failed with exit code $exitCode. Output: $joinedOutput"
    }

    return @($output)
}

function Test-GitOk {
    <#
    .SYNOPSIS
    Runs a Git command and returns true only when Git returns exit code 0.

    .PARAMETER GitArguments
    Arguments passed to the git executable.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArguments
    )

    & git @GitArguments > $null 2>&1
    return ($LASTEXITCODE -eq 0)
}

function Get-GitText {
    <#
    .SYNOPSIS
    Runs a Git command and returns trimmed text.

    .PARAMETER GitArguments
    Arguments passed to the git executable.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArguments
    )

    $lines = Invoke-GitOutput -GitArguments $GitArguments
    return (($lines | ForEach-Object { [string]$_ }) -join "`n").Trim()
}

function Convert-ToRepositoryPath {
    <#
    .SYNOPSIS
    Converts a Git path to slash-separated repository form.

    .PARAMETER Path
    A path emitted by Git.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return $Path.Replace('\', '/').Trim()
}

function Get-ChangedRepositoryPaths {
    <#
    .SYNOPSIS
    Returns changed, staged, and untracked repository paths.
    #>
    $pathMap = @{}
    $commands = @()
    $commands += ,@('diff', '--name-only')
    $commands += ,@('diff', '--name-only', '--cached')
    $commands += ,@('ls-files', '--others', '--exclude-standard')

    foreach ($command in $commands) {
        $paths = Invoke-GitOutput -GitArguments $command

        foreach ($path in $paths) {
            $normalizedPath = Convert-ToRepositoryPath -Path ([string]$path)

            if (-not [string]::IsNullOrWhiteSpace($normalizedPath)) {
                $pathMap[$normalizedPath] = $true
            }
        }
    }

    return @($pathMap.Keys)
}

function Assert-NoProtectedDocumentChange {
    <#
    .SYNOPSIS
    Stops when protected source-of-truth documents are changed, staged, or untracked.
    #>
    $protectedMap = @{}

    foreach ($protectedPath in $ProtectedPaths) {
        $protectedMap[$protectedPath] = $true
    }

    $changedPaths = Get-ChangedRepositoryPaths

    foreach ($changedPath in $changedPaths) {
        if ($protectedMap.ContainsKey($changedPath)) {
            throw "STOP: protected document change detected: $changedPath"
        }
    }
}

function Assert-CleanWorkingTree {
    <#
    .SYNOPSIS
    Stops when the working tree is not clean.

    .PARAMETER Context
    Human-readable context for the failure message.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Context
    )

    $status = Get-GitText -GitArguments @('status', '--porcelain=v1')

    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "STOP: working tree is not clean after $Context. Status:`n$status"
    }
}

function Get-NextBranchName {
    <#
    .SYNOPSIS
    Returns the next vA.B.C branch name by incrementing only C.

    .PARAMETER BranchName
    Current branch name in vA.B.C format.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$BranchName
    )

    $match = [regex]::Match($BranchName, '^v(?<Major>[0-9]+)\.(?<Minor>[0-9]+)\.(?<Patch>[0-9]+)$')

    if (-not $match.Success) {
        throw "STOP: current branch is not in vA.B.C format: $BranchName"
    }

    $major = [int]$match.Groups['Major'].Value
    $minor = [int]$match.Groups['Minor'].Value
    $patch = [int]$match.Groups['Patch'].Value

    return "v$major.$minor.$($patch + 1)"
}

function Convert-ToChangeStatusLabel {
    <#
    .SYNOPSIS
    Converts a git name-status code into a Japanese status label.

    .PARAMETER StatusCode
    Status code returned by git diff --name-status.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$StatusCode
    )

    if ($StatusCode -like 'A*') { return '追加' }
    if ($StatusCode -like 'M*') { return '更新' }
    if ($StatusCode -like 'D*') { return '削除' }
    if ($StatusCode -like 'R*') { return 'リネーム' }
    if ($StatusCode -like 'C*') { return 'コピー' }
    return '変更'
}

function Get-ChangeCategory {
    <#
    .SYNOPSIS
    Classifies a repository path into a commit-message summary category.

    .PARAMETER RepositoryPath
    Slash-separated repository path.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    if ($RepositoryPath -eq 'README.md' -or $RepositoryPath -like 'docs/*') {
        return 'ドキュメント'
    }

    if ($RepositoryPath -eq 'AGENTS.md') {
        return 'ブランチ運用手順'
    }

    if ($RepositoryPath -like 'scripts/*' -or $RepositoryPath -like 'buildspec*' -or $RepositoryPath -eq 'samconfig.toml') {
        return '運用スクリプト'
    }

    if ($RepositoryPath -like 'config/*' -or $RepositoryPath -like 'portfolio/*' -or $RepositoryPath -like 'templates/*') {
        return 'Django アプリケーション'
    }

    if ($RepositoryPath -like '*.yaml' -or $RepositoryPath -like '*.yml') {
        return 'AWS/SAM 定義'
    }

    return 'その他'
}

function Convert-NameStatusToChangeInfo {
    <#
    .SYNOPSIS
    Converts one git diff --name-status line into structured change information.

    .PARAMETER NameStatusLine
    One line returned by git diff --cached --name-status.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$NameStatusLine
    )

    $columns = @($NameStatusLine -split "`t")
    $statusCode = $columns[0]
    $path = $NameStatusLine

    if ($columns.Count -ge 3) {
        $path = [string]$columns[2]
    } elseif ($columns.Count -ge 2) {
        $path = [string]$columns[1]
    }

    $repositoryPath = Convert-ToRepositoryPath -Path $path

    return [pscustomobject]@{
        Status = Convert-ToChangeStatusLabel -StatusCode $statusCode
        Path = $repositoryPath
        Category = Get-ChangeCategory -RepositoryPath $repositoryPath
    }
}

function New-ChangeSummaryBullets {
    <#
    .SYNOPSIS
    Builds purpose-oriented commit summary bullets from staged change information.

    .PARAMETER Changes
    Structured staged change information.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Changes
    )

    $categoryOrder = @(
        'ブランチ運用手順',
        '運用スクリプト',
        'ドキュメント',
        'Django アプリケーション',
        'AWS/SAM 定義',
        'その他'
    )
    $bullets = @()

    foreach ($category in $categoryOrder) {
        $categoryChanges = @($Changes | Where-Object { $_.Category -eq $category })

        if ($categoryChanges.Count -eq 0) {
            continue
        }

        $statusCounts = @{}

        foreach ($change in $categoryChanges) {
            if (-not $statusCounts.ContainsKey($change.Status)) {
                $statusCounts[$change.Status] = 0
            }

            $statusCounts[$change.Status] += 1
        }

        $statusSummary = (($statusCounts.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name) $($_.Value)件" }) -join '、')
        $bullets += "- $category`: $statusSummary"
    }

    return $bullets
}

function New-AutoCommitMessageFile {
    <#
    .SYNOPSIS
    Generates a commit message file under .git with purpose, summary, scope, branch processing, and verification notes.

    .PARAMETER SourceBranch
    Branch being finalized.

    .PARAMETER IntegrationBranchName
    Branch receiving the merge.

    .PARAMETER NextBranch
    Branch to create after merging.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceBranch,

        [Parameter(Mandatory = $true)]
        [string]$IntegrationBranchName,

        [Parameter(Mandatory = $true)]
        [string]$NextBranch
    )

    $messagePath = Get-GitText -GitArguments @('rev-parse', '--git-path', 'branch-finalize-next-commit-message.txt')
    $nameStatusLines = Invoke-GitOutput -GitArguments @('diff', '--cached', '--name-status')
    $statText = Get-GitText -GitArguments @('diff', '--cached', '--stat')
    $changes = @()

    foreach ($lineObject in $nameStatusLines) {
        $line = ([string]$lineObject).Trim()

        if (-not [string]::IsNullOrWhiteSpace($line)) {
            $changes += Convert-NameStatusToChangeInfo -NameStatusLine $line
        }
    }

    if ($changes.Count -eq 0) {
        throw 'STOP: staged changes exist, but no name-status lines were available for commit message generation.'
    }

    $summaryBullets = New-ChangeSummaryBullets -Changes $changes
    $changedFileCount = @($changes | Select-Object -ExpandProperty Path -Unique).Count
    $changedCategories = (($changes | Select-Object -ExpandProperty Category -Unique | Sort-Object) -join '、')

    $commitMessage = @(
        "chore: finalize $SourceBranch",
        '',
        '対応目的:',
        "$SourceBranch の未コミット変更を $IntegrationBranchName へ統合し、次の作業ブランチ $NextBranch を作成できる状態にする。",
        '',
        'コミット内容の概要:',
        "$changedCategories を対象とする $changedFileCount 件の変更を、ブランチ完了処理に必要なまとまりとして確定する。",
        '',
        '対応範囲:'
    )

    foreach ($bullet in $summaryBullets) {
        $commitMessage += $bullet
    }

    $commitMessage += @(
        '',
        '差分統計:',
        $statText,
        '',
        '完了処理:',
        "- commit: $SourceBranch の未コミット変更を確定",
        "- merge: $SourceBranch を $IntegrationBranchName へ --no-ff で統合",
        "- next branch: $IntegrationBranchName から $NextBranch を作成",
        '',
        'ブランチ処理:',
        "- source branch: $SourceBranch",
        "- target branch: $IntegrationBranchName",
        "- next branch: $NextBranch",
        '',
        '検証:',
        '- git status --porcelain=v1 による作業ツリー状態確認',
        '- git diff --cached --name-status によるステージ済み変更分類',
        '- 保護対象ドキュメント変更チェック',
        '- branch-finalize-next.ps1 の停止条件に基づく Git 操作制御',
        '',
        '原則確認:',
        '- 第一原則: staged diff と git status に基づく事実確認を行った。',
        '- 第二原則: 既存の branch-finalize-next 設計に沿って処理する。',
        '- 第三原則: フォールバック、未使用コード、無関係な変更を含めない。',
        '- 第四原則: 明示された branch-finalize-next 手順のみを実行する。',
        '- 共通解釈規則: 指示対象を拡張または縮小せず、保護対象ドキュメント変更を停止条件にする。',
        '- 実行前制御: ConfirmExecution、ブランチ形式、次ブランチ不存在、作業ツリー差分を確認する。',
        '- 報告制御: 実行結果、ブランチ、commit、message path、作業ツリー状態を出力する。',
        '- 実装制御: 既存スクリプト内の制御だけで commit と merge を実行する。',
        '- スコープ変更なし: 現在ブランチの完了処理以外を対象にしない。',
        '- 外部資産: 外部モジュール、パッケージ、ツールその他の資産を追加しない。'
    )

    Set-Content -LiteralPath $messagePath -Encoding utf8NoBOM -Value $commitMessage
    return $messagePath
}

function New-MergeMessage {
    <#
    .SYNOPSIS
    Builds a merge commit message for branch finalization.

    .PARAMETER SourceBranch
    Branch being merged.

    .PARAMETER IntegrationBranchName
    Target integration branch.

    .PARAMETER NextBranch
    Next branch to create after merge.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceBranch,

        [Parameter(Mandatory = $true)]
        [string]$IntegrationBranchName,

        [Parameter(Mandatory = $true)]
        [string]$NextBranch
    )

    return @(
        "merge: $SourceBranch into $IntegrationBranchName",
        '',
        "$SourceBranch の完了済み作業を $IntegrationBranchName へ統合する。",
        '',
        'ブランチ処理:',
        "- source branch: $SourceBranch",
        "- target branch: $IntegrationBranchName",
        "- next branch: $NextBranch"
    ) -join "`n"
}

if (-not $ConfirmExecution.IsPresent) {
    throw 'STOP: explicit execution was not confirmed. Pass -ConfirmExecution.'
}

if (-not (Test-GitOk -GitArguments @('rev-parse', '--is-inside-work-tree'))) {
    throw 'STOP: current directory is not inside a Git work tree.'
}

$repositoryRoot = Get-GitText -GitArguments @('rev-parse', '--show-toplevel')
Set-Location -LiteralPath $repositoryRoot

if (-not (Test-GitOk -GitArguments @('show-ref', '--verify', '--quiet', "refs/heads/$IntegrationBranch"))) {
    throw "STOP: integration branch does not exist locally: $IntegrationBranch"
}

$currentBranch = Get-GitText -GitArguments @('branch', '--show-current')

if ([string]::IsNullOrWhiteSpace($currentBranch)) {
    throw 'STOP: detached HEAD is not allowed.'
}

if ($currentBranch -eq $IntegrationBranch) {
    throw "STOP: current branch is $IntegrationBranch. Run this from a vA.B.C work branch."
}

$nextBranch = Get-NextBranchName -BranchName $currentBranch

if (Test-GitOk -GitArguments @('show-ref', '--verify', '--quiet', "refs/heads/$nextBranch")) {
    throw "STOP: next branch already exists: $nextBranch"
}

Assert-NoProtectedDocumentChange

$statusBeforeCommit = Get-GitText -GitArguments @('status', '--porcelain=v1')
$commitCreated = $false
$commitSha = 'none'
$commitMessagePath = 'none'

if (-not [string]::IsNullOrWhiteSpace($statusBeforeCommit)) {
    Invoke-GitCommand -GitArguments @('add', '-A')
    Assert-NoProtectedDocumentChange

    $stagedFiles = Get-GitText -GitArguments @('diff', '--cached', '--name-only')

    if ([string]::IsNullOrWhiteSpace($stagedFiles)) {
        throw 'STOP: git add -A completed, but no staged changes were found. Empty commits are forbidden.'
    }

    $commitMessagePath = New-AutoCommitMessageFile -SourceBranch $currentBranch -IntegrationBranchName $IntegrationBranch -NextBranch $nextBranch
    Invoke-GitCommand -GitArguments @('commit', '-F', $commitMessagePath)

    $commitCreated = $true
    $commitSha = Get-GitText -GitArguments @('rev-parse', '--short', 'HEAD')
} else {
    Write-Output 'INFO: working tree is clean. No commit was created.'
}

Assert-CleanWorkingTree -Context 'commit handling'

Invoke-GitCommand -GitArguments @('switch', $IntegrationBranch)

try {
    $mergeMessage = New-MergeMessage -SourceBranch $currentBranch -IntegrationBranchName $IntegrationBranch -NextBranch $nextBranch
    $previousBranchFinalizeMarker = $env:AGENTS_BRANCH_FINALIZE_NEXT
    $env:AGENTS_BRANCH_FINALIZE_NEXT = '1'
    Invoke-GitCommand -GitArguments @('merge', '--no-ff', $currentBranch, '-m', $mergeMessage)
} catch {
    $mergeFailure = $_.Exception.Message

    if (Test-GitOk -GitArguments @('rev-parse', '-q', '--verify', 'MERGE_HEAD')) {
        & git merge --abort > $null 2>&1
        $abortExitCode = $LASTEXITCODE

        if ($abortExitCode -ne 0) {
            throw "STOP: merge failed and git merge --abort also failed. Original error: $mergeFailure abortExitCode=$abortExitCode"
        }
    }

    throw "STOP: merge failed. Conflict or merge error was not auto-resolved. Original error: $mergeFailure"
} finally {
    if ($null -eq $previousBranchFinalizeMarker) {
        Remove-Item Env:\AGENTS_BRANCH_FINALIZE_NEXT -ErrorAction SilentlyContinue
    } else {
        $env:AGENTS_BRANCH_FINALIZE_NEXT = $previousBranchFinalizeMarker
    }
}

Assert-CleanWorkingTree -Context 'merge handling'

Invoke-GitCommand -GitArguments @('switch', '-c', $nextBranch, $IntegrationBranch)

$finalBranch = Get-GitText -GitArguments @('branch', '--show-current')

if ($finalBranch -ne $nextBranch) {
    throw "STOP: final branch mismatch. expected=$nextBranch actual=$finalBranch"
}

Assert-CleanWorkingTree -Context 'final branch creation'

Write-Output 'DONE: branch-finalize-next completed.'
Write-Output "source_branch=$currentBranch"
Write-Output "integration_branch=$IntegrationBranch"
Write-Output "next_branch=$nextBranch"
Write-Output "commit_created=$commitCreated"
Write-Output "commit_sha=$commitSha"
Write-Output "commit_message_path=$commitMessagePath"
Write-Output "final_branch=$finalBranch"
