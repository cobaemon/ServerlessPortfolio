<#
.SYNOPSIS
Audits staged Git operations against the repository AGENTS.md rules.

.DESCRIPTION
This hook runner performs only deterministic checks that can be verified from
the repository state or the commit message supplied by Git. It stops the Git
operation when required AGENTS.md markers are missing, when deliverable
documents include evidence labels, or when a commit message lacks a title and
body.

.PARAMETER Mode
Git hook mode. Use pre-commit for staged-content checks and commit-msg for
commit-message checks.

.PARAMETER CommitMessagePath
Path to the commit message file passed by Git commit-msg.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('pre-commit', 'commit-msg')]
    [string]$Mode,

    [Parameter(Mandatory = $false)]
    [string]$CommitMessagePath
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$RequiredAgentsMarkers = @(
    '# 絶対遵守規則',
    '事実のみ調査すること',
    '事実のみ報告すること',
    'すべての報告にエビデンスを追記すること',
    '不明点や曖昧な点があれば、作業前に必ず確認すること',
    '明示的に許可がない限り、作業を行わないこと',
    '指示を曲解しないこと',
    'エビデンスがない内容を、事実として扱わないこと',
    'Hook制御'
)

$DeliverableDocumentPatterns = @(
    '^README\.md$',
    '^docs/'
)

function Invoke-GitOutput {
    <#
    .SYNOPSIS
    Runs a Git command and returns its output lines.

    .PARAMETER GitArguments
    Arguments passed to Git.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArguments
    )

    $output = & git @GitArguments 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        $joinedOutput = (($output | ForEach-Object { [string]$_ }) -join "`n").Trim()
        throw "AGENTS HOOK STOP: git $($GitArguments -join ' ') failed with exit code $exitCode. Output: $joinedOutput"
    }

    return @($output | ForEach-Object { [string]$_ })
}

function Get-RepositoryRoot {
    <#
    .SYNOPSIS
    Returns the absolute repository root path.
    #>
    return (Invoke-GitOutput -GitArguments @('rev-parse', '--show-toplevel') | Select-Object -First 1)
}

function Assert-AgentsRulesPresent {
    <#
    .SYNOPSIS
    Stops when AGENTS.md is missing required source-of-truth markers.

    .PARAMETER RepositoryRoot
    Absolute repository root path.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $agentsPath = Join-Path -Path $RepositoryRoot -ChildPath 'AGENTS.md'

    if (-not (Test-Path -LiteralPath $agentsPath -PathType Leaf)) {
        throw 'AGENTS HOOK STOP: AGENTS.md is missing.'
    }

    $agentsText = Get-Content -LiteralPath $agentsPath -Raw -Encoding utf8

    foreach ($marker in $RequiredAgentsMarkers) {
        if (-not $agentsText.Contains($marker)) {
            throw "AGENTS HOOK STOP: AGENTS.md is missing required marker: $marker"
        }
    }
}

function Get-StagedPaths {
    <#
    .SYNOPSIS
    Returns staged paths that are added, copied, modified, renamed, or type-changed.
    #>
    $lines = Invoke-GitOutput -GitArguments @('diff', '--cached', '--name-only', '--diff-filter=ACMRT')
    return @($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Test-IsDeliverableDocument {
    <#
    .SYNOPSIS
    Returns true when a repository path is a deliverable Markdown document.

    .PARAMETER RepositoryPath
    Slash-separated repository-relative path.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    foreach ($pattern in $DeliverableDocumentPatterns) {
        if ($RepositoryPath -match $pattern) {
            return $true
        }
    }

    return $false
}

function Assert-DeliverableDocumentsHaveNoEvidenceLabels {
    <#
    .SYNOPSIS
    Stops when staged deliverable docs include evidence labels.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    $paths = @($StagedPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

    if ($paths.Count -eq 0) {
        return
    }

    foreach ($path in $paths) {
        $normalizedPath = $path.Replace('\', '/')

        if (-not (Test-IsDeliverableDocument -RepositoryPath $normalizedPath)) {
            continue
        }

        $stagedContent = Invoke-GitOutput -GitArguments @('show', ":$normalizedPath")
        $matchedLines = @($stagedContent | Select-String -Pattern '(^|\s)(エビデンス|Evidence)\s*[:：]' -SimpleMatch:$false)

        if ($matchedLines.Count -gt 0) {
            throw "AGENTS HOOK STOP: deliverable document contains an evidence label: $normalizedPath"
        }
    }
}

function Assert-CommitMessageHasTitleAndBody {
    <#
    .SYNOPSIS
    Stops when the commit message lacks a title or explanatory body.

    .PARAMETER MessagePath
    Commit message file path passed by Git.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$MessagePath
    )

    if (-not (Test-Path -LiteralPath $MessagePath -PathType Leaf)) {
        throw "AGENTS HOOK STOP: commit message file is missing: $MessagePath"
    }

    $messageLines = Get-Content -LiteralPath $MessagePath -Encoding utf8
    $effectiveLines = @($messageLines | Where-Object { $_ -notmatch '^\s*#' })
    $nonEmptyLines = @($effectiveLines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

    if ($nonEmptyLines.Count -lt 2) {
        throw 'AGENTS HOOK STOP: commit message must contain both a title and a body.'
    }

    $title = $nonEmptyLines[0].Trim()
    $bodyLines = @($nonEmptyLines | Select-Object -Skip 1)
    $bodyText = ($bodyLines -join "`n").Trim()

    if ([string]::IsNullOrWhiteSpace($title)) {
        throw 'AGENTS HOOK STOP: commit message title is empty.'
    }

    if ([string]::IsNullOrWhiteSpace($bodyText)) {
        throw 'AGENTS HOOK STOP: commit message body is empty.'
    }

    if ($bodyText -eq $title) {
        throw 'AGENTS HOOK STOP: commit message body must not duplicate only the title.'
    }

    $bodyHasRequiredContext = (
        $bodyText.Contains('目的') -or
        $bodyText.Contains('概要') -or
        $bodyText.Contains('理由') -or
        $bodyText.Contains('対応') -or
        $bodyText.Contains('統合') -or
        $bodyText.Contains('検証')
    )

    if (-not $bodyHasRequiredContext) {
        throw 'AGENTS HOOK STOP: commit message body must describe purpose, summary, reason, handling, integration, or verification.'
    }
}

$repositoryRoot = Get-RepositoryRoot
Set-Location -LiteralPath $repositoryRoot
Assert-AgentsRulesPresent -RepositoryRoot $repositoryRoot

if ($Mode -eq 'pre-commit') {
    $stagedPaths = Get-StagedPaths
    Assert-DeliverableDocumentsHaveNoEvidenceLabels -StagedPaths $stagedPaths
    Write-Output 'AGENTS HOOK PASS: pre-commit checks completed.'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($CommitMessagePath)) {
    throw 'AGENTS HOOK STOP: commit-msg mode requires CommitMessagePath.'
}

Assert-CommitMessageHasTitleAndBody -MessagePath $CommitMessagePath
Write-Output 'AGENTS HOOK PASS: commit-msg checks completed.'
exit 0
