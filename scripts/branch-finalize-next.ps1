<#
.SYNOPSIS
Finalizes the current vA.B.C work branch, merges it into main, and switches to vA.B.(C+1).

.DESCRIPTION
This script is a guarded Git workflow for Codex-assisted branch finalization.
It performs the following operations only after explicit confirmation:

1. Validate that the current branch is vA.B.C.
2. Compute the next branch by incrementing only C.
3. Stop if the next branch already exists.
4. Stop if protected source-of-truth documents are changed.
5. Commit uncommitted changes only when changes exist.
6. Generate a commit message with title, body, bullet-pointed major changes, and verification notes.
7. Switch to main and merge the source branch with --no-ff.
8. Create and switch to the next work branch from main.

This script intentionally does not push, force-push, rebase, reset --hard, clean, squash merge,
use --no-verify, or overwrite existing branches.

.PARAMETER ConfirmExecution
Required explicit execution switch. The script stops unless this switch is provided.

.PARAMETER MainBranch
The integration branch. Defaults to main.

.EXAMPLE
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\branch-finalize-next.ps1 -ConfirmExecution
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$ConfirmExecution,

    [Parameter(Mandatory = $false)]
    [ValidatePattern('^[A-Za-z0-9._/-]+$')]
    [string]$MainBranch = 'main'
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

function Convert-NameStatusToBullet {
    <#
    .SYNOPSIS
    Converts one git diff --name-status line into a Japanese bullet line.

    .PARAMETER NameStatusLine
    One line returned by git diff --cached --name-status.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$NameStatusLine
    )

    $columns = @($NameStatusLine -split "`t")
    $statusCode = $columns[0]
    $statusLabel = '変更'

    if ($statusCode -like 'A*') {
        $statusLabel = '追加'
    } elseif ($statusCode -like 'M*') {
        $statusLabel = '更新'
    } elseif ($statusCode -like 'D*') {
        $statusLabel = '削除'
    } elseif ($statusCode -like 'R*') {
        $statusLabel = 'リネーム'
    } elseif ($statusCode -like 'C*') {
        $statusLabel = 'コピー'
    }

    if ($columns.Count -ge 3) {
        return "- $statusLabel`: $($columns[1]) -> $($columns[2])"
    }

    if ($columns.Count -ge 2) {
        return "- $statusLabel`: $($columns[1])"
    }

    return "- $statusLabel`: $NameStatusLine"
}

function New-AutoCommitMessageFile {
    <#
    .SYNOPSIS
    Generates a commit message file under .git with title, body, major-change bullets, and verification notes.

    .PARAMETER SourceBranch
    Branch being finalized.

    .PARAMETER MainBranchName
    Branch receiving the merge.

    .PARAMETER NextBranch
    Branch to create after merging.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceBranch,

        [Parameter(Mandatory = $true)]
        [string]$MainBranchName,

        [Parameter(Mandatory = $true)]
        [string]$NextBranch
    )

    $messagePath = Get-GitText -GitArguments @('rev-parse', '--git-path', 'branch-finalize-next-commit-message.txt')
    $nameStatusLines = Invoke-GitOutput -GitArguments @('diff', '--cached', '--name-status')
    $statText = Get-GitText -GitArguments @('diff', '--cached', '--stat')
    $bullets = @()

    foreach ($lineObject in $nameStatusLines) {
        $line = ([string]$lineObject).Trim()

        if (-not [string]::IsNullOrWhiteSpace($line)) {
            $bullets += Convert-NameStatusToBullet -NameStatusLine $line
        }
    }

    if ($bullets.Count -eq 0) {
        throw 'STOP: staged changes exist, but no name-status lines were available for commit message generation.'
    }

    $commitMessage = @(
        "chore: finalize $SourceBranch",
        '',
        "$SourceBranch の作業内容を $MainBranchName へ統合するため、ブランチ完了前の未コミット変更を確定する。",
        '',
        '主要対応:'
    )

    foreach ($bullet in $bullets) {
        $commitMessage += $bullet
    }

    $commitMessage += @(
        '',
        '変更概要:',
        $statText,
        '',
        'ブランチ処理:',
        "- source branch: $SourceBranch",
        "- target branch: $MainBranchName",
        "- next branch: $NextBranch",
        '',
        '検証:',
        '- git status --porcelain=v1 による作業ツリー状態確認',
        '- git diff --cached --name-status によるステージ済み変更確認',
        '- 保護対象ドキュメント変更チェック',
        '- branch-finalize-next.ps1 の停止条件に基づく Git 操作制御'
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

    .PARAMETER MainBranchName
    Target integration branch.

    .PARAMETER NextBranch
    Next branch to create after merge.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceBranch,

        [Parameter(Mandatory = $true)]
        [string]$MainBranchName,

        [Parameter(Mandatory = $true)]
        [string]$NextBranch
    )

    return @(
        "merge: $SourceBranch into $MainBranchName",
        '',
        "$SourceBranch の完了済み作業を $MainBranchName へ統合する。",
        '',
        'ブランチ処理:',
        "- source branch: $SourceBranch",
        "- target branch: $MainBranchName",
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

if (-not (Test-GitOk -GitArguments @('show-ref', '--verify', '--quiet', "refs/heads/$MainBranch"))) {
    throw "STOP: main branch does not exist locally: $MainBranch"
}

$currentBranch = Get-GitText -GitArguments @('branch', '--show-current')

if ([string]::IsNullOrWhiteSpace($currentBranch)) {
    throw 'STOP: detached HEAD is not allowed.'
}

if ($currentBranch -eq $MainBranch) {
    throw "STOP: current branch is $MainBranch. Run this from a vA.B.C work branch."
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

    $commitMessagePath = New-AutoCommitMessageFile -SourceBranch $currentBranch -MainBranchName $MainBranch -NextBranch $nextBranch
    Invoke-GitCommand -GitArguments @('commit', '-F', $commitMessagePath)

    $commitCreated = $true
    $commitSha = Get-GitText -GitArguments @('rev-parse', '--short', 'HEAD')
} else {
    Write-Output 'INFO: working tree is clean. No commit was created.'
}

Assert-CleanWorkingTree -Context 'commit handling'

Invoke-GitCommand -GitArguments @('switch', $MainBranch)

try {
    $mergeMessage = New-MergeMessage -SourceBranch $currentBranch -MainBranchName $MainBranch -NextBranch $nextBranch
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
}

Assert-CleanWorkingTree -Context 'merge handling'

Invoke-GitCommand -GitArguments @('switch', '-c', $nextBranch, $MainBranch)

$finalBranch = Get-GitText -GitArguments @('branch', '--show-current')

if ($finalBranch -ne $nextBranch) {
    throw "STOP: final branch mismatch. expected=$nextBranch actual=$finalBranch"
}

Assert-CleanWorkingTree -Context 'final branch creation'

Write-Output 'DONE: branch-finalize-next completed.'
Write-Output "source_branch=$currentBranch"
Write-Output "main_branch=$MainBranch"
Write-Output "next_branch=$nextBranch"
Write-Output "commit_created=$commitCreated"
Write-Output "commit_sha=$commitSha"
Write-Output "commit_message_path=$commitMessagePath"
Write-Output "final_branch=$finalBranch"
