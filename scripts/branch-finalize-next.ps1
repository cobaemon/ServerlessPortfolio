<#
.SYNOPSIS
Finalizes a vA.B.C work branch and creates the next vA.B.(C+1) branch.

.DESCRIPTION
This guarded workflow stages all working tree changes, commits them when
present, merges the current work branch into the integration branch with
--no-ff, and creates the next work branch. It never pushes, force-pushes,
rebases, resets, cleans, or bypasses hooks.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$ConfirmExecution,

    [Parameter(Mandatory = $false)]
    [ValidatePattern('^[A-Za-z0-9._/-]+$')]
    [string]$IntegrationBranch = 'dev'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $output = & git @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($output) { $output | ForEach-Object { Write-Output ([string]$_) } }
    if ($exitCode -ne 0) {
        throw "STOP: git $($Arguments -join ' ') failed with exit code $exitCode."
    }
}

function Get-GitText {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $output = & git @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "STOP: git $($Arguments -join ' ') failed with exit code $exitCode. $output"
    }
    return (($output | ForEach-Object { [string]$_ }) -join "`n").Trim()
}

function Assert-NoUnmergedChanges {
    param([Parameter(Mandatory = $true)][string]$Porcelain)

    if (-not $Porcelain) { return }

    $unmerged = @()
    foreach ($line in ($Porcelain -split "`n")) {
        if (-not $line) { continue }
        $indexStatus = $line.Substring(0, 1)
        $workTreeStatus = $line.Substring(1, 1)
        $pairStatus = $line.Substring(0, 2)
        if ($indexStatus -eq 'U' -or $workTreeStatus -eq 'U' -or $pairStatus -in @('AA', 'DD')) {
            $unmerged += $line
        }
    }

    if ($unmerged.Count -gt 0) {
        throw "STOP: unmerged changes exist. Resolve conflicts before branch-finalize-next.`n$($unmerged -join "`n")"
    }
}

function Stage-WorktreeChanges {
    $before = Get-GitText @('status', '--porcelain')
    if (-not $before) { return }

    Assert-NoUnmergedChanges -Porcelain $before

    # branch-finalize-next is the version boundary, so every current worktree change becomes part of this commit.
    Invoke-Git @('add', '--all')

    $after = Get-GitText @('status', '--porcelain')
    Assert-NoUnmergedChanges -Porcelain $after

    $unstagedOrUntracked = @()
    foreach ($line in ($after -split "`n")) {
        if (-not $line) { continue }
        $workTreeStatus = $line.Substring(1, 1)
        if ($line.StartsWith('??') -or $workTreeStatus -ne ' ') {
            $unstagedOrUntracked += $line
        }
    }

    if ($unstagedOrUntracked.Count -gt 0) {
        throw "STOP: git add --all did not stage every worktree change.`n$($unstagedOrUntracked -join "`n")"
    }
}

function New-CommitMessage {
    param(
        [Parameter(Mandatory = $true)][string]$SourceBranch,
        [Parameter(Mandatory = $true)][string]$IntegrationBranch,
        [Parameter(Mandatory = $true)][string]$NextBranch
    )

    $stat = Get-GitText @('diff', '--cached', '--stat')
    if (-not $stat) { $stat = 'No staged diff stat was available.' }
    return @"
制御された作業ブランチを統合

目的: $SourceBranch の staged 変更を $IntegrationBranch へ統合し、次作業ブランチ $NextBranch を作成する。
概要: branch-finalize-next により worktree 全体を staging して commit し、--no-ff merge で統合する。
対応: push、force push、reset、clean、rebase、squash、--no-verify は実行しない。
検証: branch-finalize-next の停止条件と Git 終了コードを確認する。
対象: branch-finalize-next 実行時の worktree 全体。
外部資産: 追加なし。
ユーザー明示許可: STG での検証、検証結果報告、採用基準判定の指示に基づく。
対象差分: worktree 全体を staging した差分。
対象差分:
$stat
"@
}

if (-not $ConfirmExecution) {
    throw 'STOP: -ConfirmExecution is required.'
}

$sourceBranch = Get-GitText @('branch', '--show-current')
if (-not $sourceBranch) { throw 'STOP: detached HEAD is not allowed.' }
if ($sourceBranch -eq $IntegrationBranch) { throw "STOP: current branch is integration branch: $IntegrationBranch" }
if ($sourceBranch -notmatch '^v(\d+)\.(\d+)\.(\d+)$') {
    throw "STOP: current branch must match vA.B.C: $sourceBranch"
}

$major = [int]$Matches[1]
$minor = [int]$Matches[2]
$patch = [int]$Matches[3]
$nextBranch = "v$major.$minor.$($patch + 1)"

$existing = Get-GitText @('branch', '--list', $nextBranch)
if ($existing) { throw "STOP: next branch already exists: $nextBranch" }

Stage-WorktreeChanges

$staged = Get-GitText @('diff', '--cached', '--name-only')
$commitCreated = $false
$commitSha = ''
$messagePath = Get-GitText @('rev-parse', '--git-path', 'branch-finalize-next-commit-message.txt')

if ($staged) {
    $message = New-CommitMessage -SourceBranch $sourceBranch -IntegrationBranch $IntegrationBranch -NextBranch $nextBranch
    Set-Content -LiteralPath $messagePath -Value $message -Encoding UTF8
    Invoke-Git @('commit', '-F', $messagePath)
    $commitCreated = $true
    $commitSha = Get-GitText @('rev-parse', 'HEAD')
}

Invoke-Git @('switch', $IntegrationBranch)
Invoke-Git @('merge', '--no-ff', $sourceBranch)
$mergeSha = Get-GitText @('rev-parse', 'HEAD')
Invoke-Git @('switch', '-c', $nextBranch)
$finalStatus = Get-GitText @('status', '--short')
if (-not $finalStatus) { $finalStatus = 'clean' }

Write-Output "branch-finalize-next completed"
Write-Output "source branch: $sourceBranch"
Write-Output "integration branch: $IntegrationBranch"
Write-Output "next branch: $nextBranch"
Write-Output "commit created: $commitCreated"
Write-Output "commit SHA: $commitSha"
Write-Output "commit message path: $messagePath"
Write-Output "merge SHA: $mergeSha"
Write-Output "final status:"
Write-Output $finalStatus
