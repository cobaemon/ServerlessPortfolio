<#
.SYNOPSIS
Audits staged Git operations against the repository AGENTS.md rules.

.DESCRIPTION
This hook runner performs only deterministic checks that can be verified from
the repository state or the commit message supplied by Git. It stops the Git
operation when required AGENTS.md markers are missing, when deliverable
documents include evidence labels, or when a commit message lacks a title and
body. Protected branch push blocking is opt-in for AI-controlled shells so a
human operator is not blocked by the repository hook.

.PARAMETER Mode
Git hook mode. Use pre-commit for staged-content checks and commit-msg for
commit-message checks. Use pre-push to guard protected branch pushes.

.PARAMETER CommitMessagePath
Path to the commit message file passed by Git commit-msg.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('pre-commit', 'commit-msg', 'pre-push')]
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
    'Hook制御',
    '未コミットテンプレートを staging に直接適用して検証完了扱いにしないこと',
    '実環境への実害が発生したインシデントは侵害以上に分類すること'
)

$DeliverableDocumentPatterns = @(
    '^README\.md$',
    '^docs/'
)

$IncidentRecordPattern = '^docs/incidents/[0-9]{8}_[0-9]{6}_Incident\.md$'

$ProtectedBranches = @(
    'dev',
    'main'
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

function Assert-IncidentRecordCycleDocuments {
    <#
    .SYNOPSIS
    Stops staged incident records that do not include corrective hook and document scope.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    $paths = @($StagedPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $hasIncidentRecord = $false

    foreach ($path in $paths) {
        $normalizedPath = $path.Replace('\', '/')

        if ($normalizedPath -notlike 'docs/incidents/*') {
            continue
        }

        if ($normalizedPath -eq 'docs/incidents/README.md') {
            continue
        }

        if ($normalizedPath -notmatch $IncidentRecordPattern) {
            throw "AGENTS HOOK STOP: incident record filename must match yyyyMMdd_HHmmss_Incident.md: $normalizedPath"
        }

        $hasIncidentRecord = $true
        $stagedContent = Invoke-GitOutput -GitArguments @('show', ":$normalizedPath")
        $text = ($stagedContent -join "`n")

        if ($text -notmatch '(?m)^INC-[0-9]{8}-[0-9]{3}-(致命的|侵害|重大|違反)\s*$') {
            throw "AGENTS HOOK STOP: incident record must start with INC-yyyyMMdd-NNN-level: $normalizedPath"
        }

        Assert-IncidentLevelMatchesImpact -Text $text -RepositoryPath $normalizedPath
        Assert-IncidentCorrectiveSectionDocumented -Text $text -Heading '対応策としてのフック修正：' -RepositoryPath $normalizedPath
        Assert-IncidentCorrectiveSectionDocumented -Text $text -Heading '対応策としての関連ドキュメント修正：' -RepositoryPath $normalizedPath
    }

    if (-not $hasIncidentRecord) {
        return
    }

    $normalizedStagedPaths = @($paths | ForEach-Object { $_.Replace('\', '/') })

    if ($normalizedStagedPaths -notcontains 'scripts/agents-compliance-check.ps1') {
        throw 'AGENTS HOOK STOP: incident records must be committed with hook corrective changes in scripts/agents-compliance-check.ps1.'
    }

    if ($normalizedStagedPaths -notcontains 'AGENTS.md') {
        throw 'AGENTS HOOK STOP: incident records must be committed with related procedure documentation changes in AGENTS.md.'
    }
}

function Assert-StagingVerificationClaimsIncludeSourceRevision {
    <#
    .SYNOPSIS
    Stops AI progress docs from claiming staging verification without source revision evidence.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    $paths = @($StagedPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

    foreach ($path in $paths) {
        $normalizedPath = $path.Replace('\', '/')

        if ($normalizedPath -notlike 'docs/ai-progress/*.md') {
            continue
        }

        $stagedContent = Invoke-GitOutput -GitArguments @('show', ":$normalizedPath")
        $text = ($stagedContent -join "`n")
        $claimsStagingVerification = (
            $text -match 'staging pipeline' -and
            (
                $text -match 'Succeeded' -or
                $text -match 'UPDATE_COMPLETE' -or
                $text -match '200 OK'
            )
        )

        if (-not $claimsStagingVerification) {
            continue
        }

        if ($text -notmatch 'source revision') {
            throw "AGENTS HOOK STOP: staging verification claims must include source revision evidence: $normalizedPath"
        }
    }
}

function Get-MarkdownSectionBody {
    <#
    .SYNOPSIS
    Returns the body of a level-2 Markdown section.

    .PARAMETER Text
    Markdown text to inspect.

    .PARAMETER Heading
    Level-2 heading text without the leading hashes.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Heading
    )

    $escapedHeading = [regex]::Escape($Heading)
    $match = [regex]::Match($Text, "(?ms)^##\s+$escapedHeading\s*\r?\n(?<body>.*?)(?=^##\s+|\z)")

    if (-not $match.Success) {
        return $null
    }

    return $match.Groups['body'].Value.Trim()
}

function Assert-IncidentCorrectiveSectionDocumented {
    <#
    .SYNOPSIS
    Stops incident records whose corrective section is empty or marked unimplemented.

    .PARAMETER Text
    Incident record Markdown text.

    .PARAMETER Heading
    Required level-2 heading text.

    .PARAMETER RepositoryPath
    Incident record path used in error messages.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Heading,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    $sectionBody = Get-MarkdownSectionBody -Text $Text -Heading $Heading

    if ($null -eq $sectionBody) {
        throw "AGENTS HOOK STOP: incident record must include corrective action section '$Heading': $RepositoryPath"
    }

    if ([string]::IsNullOrWhiteSpace($sectionBody)) {
        throw "AGENTS HOOK STOP: incident record corrective action section must not be empty '$Heading': $RepositoryPath"
    }

    if ($sectionBody -match '(?m)^\s*未実施') {
        throw "AGENTS HOOK STOP: incident record corrective action section must not be marked unimplemented '$Heading': $RepositoryPath"
    }
}

function Assert-IncidentLevelMatchesImpact {
    <#
    .SYNOPSIS
    Stops incident records that classify actual environment impact below intrusion level.

    .PARAMETER Text
    Incident record Markdown text.

    .PARAMETER RepositoryPath
    Incident record path used in error messages.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    $levelMatch = [regex]::Match($Text, '(?m)^INC-[0-9]{8}-[0-9]{3}-(?<level>致命的|侵害|重大|違反)\s*$')

    if (-not $levelMatch.Success) {
        return
    }

    $level = $levelMatch.Groups['level'].Value
    $hasActualEnvironmentImpact = (
        $Text.Contains('実害') -or
        ($Text -match 'staging pipeline stack.*UPDATE_COMPLETE') -or
        ($Text -match 'staging IAM inline policy.*更新') -or
        ($Text -match '未コミット.*staging.*直接適用') -or
        ($Text -match '実環境.*変更')
    )

    if ($hasActualEnvironmentImpact -and $level -notin @('致命的', '侵害')) {
        throw "AGENTS HOOK STOP: incident records with actual environment impact must be classified as 致命的 or 侵害: $RepositoryPath"
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

function Get-CurrentBranch {
    <#
    .SYNOPSIS
    Returns the current Git branch name.
    #>
    $branch = (Invoke-GitOutput -GitArguments @('branch', '--show-current') | Select-Object -First 1).Trim()

    if ([string]::IsNullOrWhiteSpace($branch)) {
        throw 'AGENTS HOOK STOP: detached HEAD is not allowed for protected operations.'
    }

    return $branch
}

function Test-IsProtectedBranch {
    <#
    .SYNOPSIS
    Returns true when a branch is protected by repository workflow rules.

    .PARAMETER BranchName
    Branch name without refs/heads/.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$BranchName
    )

    return ($ProtectedBranches -contains $BranchName)
}

function Test-IsBranchFinalizeContext {
    <#
    .SYNOPSIS
    Returns true when branch-finalize-next has explicitly marked this Git operation.
    #>
    return ($env:AGENTS_BRANCH_FINALIZE_NEXT -eq '1')
}

function Assert-DirectCommitBranchAllowed {
    <#
    .SYNOPSIS
    Stops direct commits on protected branches unless branch-finalize-next marked the operation.
    #>
    $branch = Get-CurrentBranch

    if ((Test-IsProtectedBranch -BranchName $branch) -and -not (Test-IsBranchFinalizeContext)) {
        throw "AGENTS HOOK STOP: direct commits on protected branch '$branch' are forbidden. Use a vA.B.C work branch and branch-finalize-next."
    }
}

function Assert-ProtectedBranchCommitMessageAllowed {
    <#
    .SYNOPSIS
    Stops protected branch commit messages unless created by branch-finalize-next.

    .PARAMETER MessagePath
    Commit message file path passed by Git.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$MessagePath
    )

    $branch = Get-CurrentBranch

    if (-not (Test-IsProtectedBranch -BranchName $branch)) {
        return
    }

    if (-not (Test-IsBranchFinalizeContext)) {
        throw "AGENTS HOOK STOP: commit-msg on protected branch '$branch' is forbidden outside branch-finalize-next."
    }

    $message = Get-Content -LiteralPath $MessagePath -Raw -Encoding utf8

    if ($message -notmatch '(?m)^merge: v[0-9]+\.[0-9]+\.[0-9]+ into dev$') {
        throw "AGENTS HOOK STOP: protected branch '$branch' accepts only branch-finalize-next merge messages."
    }
}

function Convert-RefToBranchName {
    <#
    .SYNOPSIS
    Converts a Git ref path to a branch name when possible.

    .PARAMETER RefName
    Git ref such as refs/heads/dev.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$RefName
    )

    if ($RefName -like 'refs/heads/*') {
        return $RefName.Substring('refs/heads/'.Length)
    }

    return $RefName
}

function Assert-ProtectedPushAllowed {
    <#
    .SYNOPSIS
    Stops AI-controlled pushes to protected branches unless explicitly enabled.
    #>
    $stdinText = [Console]::In.ReadToEnd()

    if ([string]::IsNullOrWhiteSpace($stdinText)) {
        return
    }

    $blockedBranches = @()

    foreach ($line in ($stdinText -split "`n")) {
        $trimmed = $line.Trim()

        if ([string]::IsNullOrWhiteSpace($trimmed)) {
            continue
        }

        $columns = @($trimmed -split '\s+')

        if ($columns.Count -lt 4) {
            continue
        }

        $remoteRef = [string]$columns[2]
        $remoteBranch = Convert-RefToBranchName -RefName $remoteRef

        if (Test-IsProtectedBranch -BranchName $remoteBranch) {
            $blockedBranches += $remoteBranch
        }
    }

    $uniqueBlockedBranches = @($blockedBranches | Sort-Object -Unique)

    if ($uniqueBlockedBranches.Count -eq 0) {
        return
    }

    if ($env:AGENTS_AI_PROTECTED_PUSH_GUARD -ne '1') {
        Write-Output "AGENTS HOOK WARN: protected branch push detected but not blocked for human-operated shell: $($uniqueBlockedBranches -join ', ')"
        return
    }

    if ($env:AGENTS_ALLOW_PROTECTED_PUSH -eq '1') {
        Write-Output "AGENTS HOOK PASS: AI protected branch push explicitly allowed for: $($uniqueBlockedBranches -join ', ')"
        return
    }

    throw "AGENTS HOOK STOP: AI protected branch push is forbidden without AGENTS_ALLOW_PROTECTED_PUSH=1: $($uniqueBlockedBranches -join ', ')"
}

$repositoryRoot = Get-RepositoryRoot
Set-Location -LiteralPath $repositoryRoot
Assert-AgentsRulesPresent -RepositoryRoot $repositoryRoot

if ($Mode -eq 'pre-commit') {
    Assert-DirectCommitBranchAllowed
    $stagedPaths = Get-StagedPaths
    Assert-DeliverableDocumentsHaveNoEvidenceLabels -StagedPaths $stagedPaths
    Assert-StagingVerificationClaimsIncludeSourceRevision -StagedPaths $stagedPaths
    Assert-IncidentRecordCycleDocuments -StagedPaths $stagedPaths
    Write-Output 'AGENTS HOOK PASS: pre-commit checks completed.'
    exit 0
}

if ($Mode -eq 'pre-push') {
    Assert-ProtectedPushAllowed
    Write-Output 'AGENTS HOOK PASS: pre-push checks completed.'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($CommitMessagePath)) {
    throw 'AGENTS HOOK STOP: commit-msg mode requires CommitMessagePath.'
}

Assert-CommitMessageHasTitleAndBody -MessagePath $CommitMessagePath
Assert-ProtectedBranchCommitMessageAllowed -MessagePath $CommitMessagePath
Write-Output 'AGENTS HOOK PASS: commit-msg checks completed.'
exit 0
