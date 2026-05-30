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
    '忠実であること',
    '誠実であること',
    '策定済みの要件および設計を厳守すること',
    'ゼロトラストセキュリティを厳守すること',
    'SOLID原則を厳守すること',
    'GDPRを厳守すること',
    'クリーンアーキテクチャを厳守すること',
    '外部モジュール、パッケージ、ツールその他の資産を使用する際は、事前にライセンスを確認し、通告し、厳守すること',
    'プロジェクト全体で一貫性を保つこと',
    'プロジェクト全体で整合性を保つこと',
    'フォールバックを行わないこと',
    '未使用コードを残さないこと',
    'ファイルドキュメントを実装すること',
    '関数ドキュメントを実装すること',
    '行コメントを実装すること',
    'プロンプトインジェクション対策として、信頼性のあるサイトのみを参照・アクセスすること',
    '指示に従うこと',
    '指示を曲解しないこと',
    '決めつけを行わないこと',
    '指示文中の語句を、確認なしに一般化、短縮、言い換え、補完しないこと',
    '指示対象を、確認なしに別対象へ拡張しないこと',
    '確認が必要な状態で、確認なしに作業を続行しないこと',
    '要件を1つでも満たしていない状態で、完了、成功、対応済み、問題なしと扱わないこと',
    'エビデンスがない内容を、事実として扱わないこと',
    '自分に都合のよい解釈、作業量を減らす解釈、確認を省略できる解釈を採用しないこと',
    '実行前制御',
    '報告制御',
    '実装制御',
    '制御系0設計',
    '原則は、人間であるユーザーだけが変更できる不可分の領域である',
    '原則は、Git hook、commit、push、ファイル編集、shell 実行、ツール実行の有無に関係なく、すべての応答、判断、作業、報告に常時適用する',
    '制御系ファイル',
    'AI/Codex は、ユーザーが制御系ファイルの作成、編集、削除、移動、上書きを明示指示していない場合、制御系ファイルを変更してはならない',
    '制御は、GitHook制御の単一レイヤへ集約してはならない',
    'Codex/AI は、開発効率化を目的として作業を遂行する',
    '応答前制御',
    '作業前制御',
    'ツール実行前制御',
    'ファイル編集前制御',
    '実行中制御',
    '報告前制御',
    '事後監査制御',
    '質問に対して、別インシデント、別対象、別スコープへ置き換えて回答していないこと',
    '原則遵守と開発効率化要件の両方を満たす作業手順になっていること',
    'ユーザーの目的または開発効率化要件と矛盾する対応案になった',
    '対象インシデントをすり替えず、ユーザーが指摘した対象を固定していること',
    'スコープ変更禁止',
    'Hook 誤判定防止',
    '誤判定によりプロジェクト遅延、トークン、クレジット、pipeline 実行、または追加コストを発生させる制御を追加してはならない',
    'Codex/AI 制御は opt-in 環境変数でのみ強制し、人間ユーザーの手動操作は warning に限定して停止してはならない',
    'Hook制御',
    '未コミットテンプレートを staging に直接適用して検証完了扱いにしないこと',
    '実環境への実害が発生したインシデントは侵害以上に分類すること',
    '検証サイトでの検証または正規手順での作業再開を依頼された場合はbranch-finalize-nextを責任範囲に含めること',
    'AGENTS_ALLOW_EXTERNAL_ASSET_CHANGE=1',
    '侵害以上のインシデントで実環境または `origin/dev` に未承認変更が反映済みの場合',
    '侵害以上のインシデント復旧を反映した場合',
    '事実根拠に基づかない作業判断',
    '制御不備または原則不遵守',
    '発生前に停止できたはずのゲート：',
    '既存再発防止策が効かなかった理由：',
    '再発防止策の検証方法：',
    '自己検知・自己報告の成否：',
    'AGENTS_CONTROL_SYSTEM_CHANGE_AUTHORIZED=1',
    'AGENTS_ALLOW_NON_DEPLOYMENT_PIPELINE_PUSH=1'
)

$PrincipleCommitMessageMarkers = @(
    '原則確認:',
    '第一原則:',
    '第二原則:',
    '第三原則:',
    '第四原則:',
    '共通解釈規則:',
    '制御系0設計:',
    '実行前制御:',
    '報告制御:',
    '実装制御:',
    'スコープ変更なし:',
    '外部資産:'
)

$PrincipleCommitMessageDetailMarkers = @(
    '第一原則:',
    '第二原則:',
    '第三原則:',
    '第四原則:',
    '共通解釈規則:',
    '制御系0設計:',
    '実行前制御:',
    '報告制御:',
    '実装制御:',
    'スコープ変更なし:',
    '外部資産:'
)

$ExternalAssetCommitMessageMarkers = @(
    '外部資産承認:',
    'ライセンス:',
    '通告:',
    'ユーザー明示許可:',
    '対象差分:'
)

$ControlSystemCommitMessageMarkers = @(
    '制御系変更承認:',
    '制御系変更対象:',
    '原則本文変更なし:',
    'ユーザー明示許可:',
    '対象差分:'
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

$ExternalAssetChangeApprovalVariable = 'AGENTS_ALLOW_EXTERNAL_ASSET_CHANGE'
$ExternalAssetCommandPattern = '(?i)\b(apt(-get)?\s+install|yum\s+install|dnf\s+install|apk\s+add|brew\s+install|choco\s+install|winget\s+install|python\s+-m\s+pip\s+install|pip\s+install|npm\s+(install|i)\b|yarn\s+add|pnpm\s+add|curl\s+.*https?://|wget\s+.*https?://)'
$ControlSystemChangeApprovalVariable = 'AGENTS_CONTROL_SYSTEM_CHANGE_AUTHORIZED'
$NonDeploymentPipelinePushApprovalVariable = 'AGENTS_ALLOW_NON_DEPLOYMENT_PIPELINE_PUSH'
$FallbackContinuationPattern = '(?i)(\|\|\s*(echo|true)\b|except\s+[^:]+:\s*pass\b)'
$PipelineTriggerDenylistPatterns = @(
    'docs/**',
    'AGENTS.md',
    '.githooks/**',
    'scripts/agents-compliance-check.ps1',
    'scripts/branch-finalize-next.ps1',
    'README.md',
    'LICENSE',
    '.kiro/**'
)
$DeploymentRuntimeSourcePatterns = @(
    '^pipeline\.yaml$',
    '^buildspec\.yml$',
    '^buildspec-deps\.yml$',
    '^template\.yaml$',
    '^dependencies\.yaml$',
    '^bucketpolicy\.yaml$',
    '^requirements\.txt$',
    '^samconfig\.toml$',
    '^Dockerfile$',
    '^\.dockerignore$',
    '^manage\.py$',
    '^asgi_lambda\.py$',
    '^config/',
    '^portfolio/',
    '^templates/',
    '^locale/',
    '^scripts/generate_static_assets\.py$',
    '^scripts/check_static_manifest\.py$'
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

function Test-EnvironmentFlagSet {
    <#
    .SYNOPSIS
    Returns true only when an environment variable is set to 1.

    .PARAMETER Name
    Environment variable name.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $item = Get-Item -Path "Env:$Name" -ErrorAction SilentlyContinue

    if ($null -eq $item) {
        return $false
    }

    return ($item.Value -eq '1')
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

function Test-IsExternalAssetSensitivePath {
    <#
    .SYNOPSIS
    Returns true when a repository path can execute or define external asset acquisition.

    .PARAMETER RepositoryPath
    Slash-separated repository-relative path.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    return (
        $RepositoryPath -match '(^|/)buildspec[^/]*\.ya?ml$' -or
        $RepositoryPath -match '(^|/)\.github/workflows/[^/]+\.ya?ml$' -or
        $RepositoryPath -match '(^|/)scripts/.+\.(ps1|sh|py)$' -or
        $RepositoryPath -match '(^|/)Dockerfile$' -or
        $RepositoryPath -match '(^|/)requirements[^/]*\.txt$' -or
        $RepositoryPath -match '(^|/)package(-lock)?\.json$' -or
        $RepositoryPath -match '(^|/)(pnpm-lock\.yaml|yarn\.lock)$'
    )
}

function Test-IsControlSystemPath {
    <#
    .SYNOPSIS
    Returns true when a repository path controls AI/Codex behavior or governance.

    .PARAMETER RepositoryPath
    Slash-separated repository-relative path.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    return (
        $RepositoryPath -eq 'AGENTS.md' -or
        $RepositoryPath -like '.githooks/*' -or
        $RepositoryPath -eq 'scripts/agents-compliance-check.ps1' -or
        $RepositoryPath -eq 'scripts/branch-finalize-next.ps1' -or
        $RepositoryPath -eq 'docs/incidents/README.md' -or
        $RepositoryPath -eq 'docs/ai-progress/README.md' -or
        $RepositoryPath -eq 'docs/development-records/README.md' -or
        $RepositoryPath -eq 'docs/index.md'
    )
}

function Get-StagedControlSystemPaths {
    <#
    .SYNOPSIS
    Returns staged paths that modify control-system files.
    #>
    $lines = Invoke-GitOutput -GitArguments @('diff', '--cached', '--name-only', '--diff-filter=ACDMRT')
    $paths = @()

    foreach ($line in $lines) {
        $normalizedPath = ([string]$line).Replace('\', '/').Trim()

        if ([string]::IsNullOrWhiteSpace($normalizedPath)) {
            continue
        }

        if (Test-IsControlSystemPath -RepositoryPath $normalizedPath) {
            $paths += $normalizedPath
        }
    }

    return @($paths | Sort-Object -Unique)
}

function Normalize-LineEndings {
    <#
    .SYNOPSIS
    Normalizes line endings for deterministic text comparison.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    return ($Text -replace "`r`n", "`n" -replace "`r", "`n")
}

function Get-ImmutablePrincipleBlock {
    <#
    .SYNOPSIS
    Returns the immutable AGENTS.md principle block.

    .PARAMETER Text
    AGENTS.md text.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $normalizedText = Normalize-LineEndings -Text $Text
    $match = [regex]::Match($normalizedText, '(?ms)\A(?<block>.*?)(?=^##\s+(制御系0設計|スコープ変更禁止)\s*$)')

    if (-not $match.Success) {
        return $normalizedText
    }

    return $match.Groups['block'].Value.TrimEnd()
}

function Assert-PrincipleContentImmutable {
    <#
    .SYNOPSIS
    Stops staged AGENTS.md changes that alter the immutable principle block.
    #>
    $controlPaths = @(Get-StagedControlSystemPaths)

    if ($controlPaths -notcontains 'AGENTS.md') {
        return
    }

    try {
        $headText = (@(Invoke-GitOutput -GitArguments @('show', 'HEAD:AGENTS.md')) -join "`n")
        $stagedText = (@(Invoke-GitOutput -GitArguments @('show', ':AGENTS.md')) -join "`n")
    }
    catch {
        throw "AGENTS HOOK STOP: AGENTS.md principle block cannot be verified from HEAD and staged content. $($_.Exception.Message)"
    }

    $headPrinciples = Get-ImmutablePrincipleBlock -Text $headText
    $stagedPrinciples = Get-ImmutablePrincipleBlock -Text $stagedText

    if ($headPrinciples -ne $stagedPrinciples) {
        throw 'AGENTS HOOK STOP: AGENTS.md immutable principle block was changed. Only the human user may change principles.'
    }
}

function Assert-ControlSystemChangesAuthorized {
    <#
    .SYNOPSIS
    Stops control-system file changes unless an explicit control-change guard is set.
    #>
    $controlPaths = @(Get-StagedControlSystemPaths)

    if ($controlPaths.Count -eq 0) {
        return
    }

    if (Test-EnvironmentFlagSet -Name $ControlSystemChangeApprovalVariable) {
        Write-Output "AGENTS HOOK PASS: control-system changes explicitly approved by $ControlSystemChangeApprovalVariable."
        return
    }

    throw "AGENTS HOOK STOP: control-system files changed without $ControlSystemChangeApprovalVariable=1. Paths: $($controlPaths -join ', ')"
}

function Get-StagedExternalAssetAcquisitionMatches {
    <#
    .SYNOPSIS
    Returns staged lines that add external asset acquisition commands.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    $paths = @($StagedPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $externalAssetMatches = @()

    foreach ($path in $paths) {
        $normalizedPath = $path.Replace('\', '/')

        if (-not (Test-IsExternalAssetSensitivePath -RepositoryPath $normalizedPath)) {
            continue
        }

        $diffLines = Invoke-GitOutput -GitArguments @('diff', '--cached', '--unified=0', '--no-ext-diff', '--', $normalizedPath)

        foreach ($line in $diffLines) {
            if (-not $line.StartsWith('+') -or $line.StartsWith('+++')) {
                continue
            }

            $addedLine = $line.Substring(1).Trim()

            if ($normalizedPath -eq 'scripts/agents-compliance-check.ps1' -and $addedLine.StartsWith('$ExternalAssetCommandPattern')) {
                continue
            }

            if ($addedLine -match $ExternalAssetCommandPattern) {
                $externalAssetMatches += "${normalizedPath}: $addedLine"
            }
        }
    }

    return @($externalAssetMatches)
}

function Assert-ExternalAssetChangesApproved {
    <#
    .SYNOPSIS
    Stops staged executable/config changes that add external asset acquisition commands without approval.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    $matches = @(Get-StagedExternalAssetAcquisitionMatches -StagedPaths $StagedPaths)

    if ($matches.Count -eq 0) {
        return
    }

    if (Test-EnvironmentFlagSet -Name $ExternalAssetChangeApprovalVariable) {
        Write-Output "AGENTS HOOK PASS: external asset acquisition changes explicitly approved by $ExternalAssetChangeApprovalVariable."
        return
    }

    throw "AGENTS HOOK STOP: staged changes add external asset acquisition commands without $ExternalAssetChangeApprovalVariable=1. Matches: $($matches -join '; ')"
}

function Assert-NoFallbackContinuationAdded {
    <#
    .SYNOPSIS
    Stops staged executable/config changes that add continuation fallback patterns.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    $paths = @($StagedPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $matches = @()

    foreach ($path in $paths) {
        $normalizedPath = $path.Replace('\', '/')

        if (-not (Test-IsExternalAssetSensitivePath -RepositoryPath $normalizedPath)) {
            continue
        }

        $diffLines = Invoke-GitOutput -GitArguments @('diff', '--cached', '--unified=0', '--no-ext-diff', '--', $normalizedPath)

        foreach ($line in $diffLines) {
            if (-not $line.StartsWith('+') -or $line.StartsWith('+++')) {
                continue
            }

            $addedLine = $line.Substring(1).Trim()

            if ($normalizedPath -eq 'scripts/agents-compliance-check.ps1' -and $addedLine.StartsWith('$FallbackContinuationPattern')) {
                continue
            }

            if ($addedLine -match $FallbackContinuationPattern) {
                $matches += "${normalizedPath}: $addedLine"
            }
        }
    }

    if ($matches.Count -gt 0) {
        throw "AGENTS HOOK STOP: staged changes add fallback continuation patterns. Matches: $($matches -join '; ')"
    }
}

function Test-IsDeploymentRuntimeSourcePath {
    <#
    .SYNOPSIS
    Returns true when a path can affect deploy, build, or runtime behavior.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    foreach ($pattern in $DeploymentRuntimeSourcePatterns) {
        if ($RepositoryPath -match $pattern) {
            return $true
        }
    }

    return $false
}

function Test-LineIsInsidePipelineTriggerBlock {
    <#
    .SYNOPSIS
    Returns true when a pipeline.yaml line belongs to the top-level Triggers block.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string[]]$Lines,

        [Parameter(Mandatory = $true)]
        [int]$LineIndex
    )

    $triggerIndent = $null

    for ($index = 0; $index -le $LineIndex; $index += 1) {
        $line = $Lines[$index]

        if ($line -match '^(\s*)Triggers:\s*$') {
            $triggerIndent = $Matches[1].Length
            continue
        }

        if ($null -ne $triggerIndent -and -not [string]::IsNullOrWhiteSpace($line)) {
            $currentIndent = ([regex]::Match($line, '^\s*')).Value.Length
            if ($currentIndent -le $triggerIndent) {
                $triggerIndent = $null
            }
        }
    }

    return ($null -ne $triggerIndent)
}

function Assert-PipelineTriggerDenylistNotReferencedByDeploymentSources {
    <#
    .SYNOPSIS
    Stops deploy/build/runtime sources from adding references to paths excluded from CodePipeline triggers.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    $matches = @()

    foreach ($path in @($StagedPaths)) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $normalizedPath = $path.Replace('\', '/')
        if (-not (Test-IsDeploymentRuntimeSourcePath -RepositoryPath $normalizedPath)) {
            continue
        }

        $stagedContent = @()
        try {
            $stagedContent = @(Invoke-GitOutput -GitArguments @('show', ":$normalizedPath"))
        } catch {
            continue
        }

        for ($index = 0; $index -lt $stagedContent.Count; $index += 1) {
            $line = [string]$stagedContent[$index]

            foreach ($denylistPattern in $PipelineTriggerDenylistPatterns) {
                if (-not $line.Contains($denylistPattern)) {
                    continue
                }

                $isAllowedTriggerDefinition = (
                    $normalizedPath -eq 'pipeline.yaml' -and
                    (Test-LineIsInsidePipelineTriggerBlock -Lines $stagedContent -LineIndex $index)
                )

                if ($isAllowedTriggerDefinition) {
                    continue
                }

                $matches += "${normalizedPath}:$($index + 1): $denylistPattern"
            }
        }
    }

    if ($matches.Count -gt 0) {
        throw "AGENTS HOOK STOP: deploy/build/runtime sources must not reference CodePipeline trigger denylist paths. Matches: $($matches -join '; ')"
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
        Assert-IncidentFactControlDocumented -Text $text -RepositoryPath $normalizedPath
        Assert-IncidentControlDefectHasLayer -Text $text -RepositoryPath $normalizedPath
        Assert-IncidentScopeChangeDocumented -Text $text -RepositoryPath $normalizedPath
        Assert-IncidentDeployScopeBoundaryDocumented -Text $text -RepositoryPath $normalizedPath
        Assert-IncidentGateSectionDocumented -Text $text -RepositoryPath $normalizedPath
        Assert-IncidentAuditSectionsDocumented -Text $text -RepositoryPath $normalizedPath
        Assert-IncidentCorrectiveSectionDocumented -Text $text -Heading '対応策としての制御系修正：' -RepositoryPath $normalizedPath
        Assert-IncidentCorrectiveSectionDocumented -Text $text -Heading '対応策としての関連ドキュメント修正：' -RepositoryPath $normalizedPath
    }

    if (-not $hasIncidentRecord) {
        return
    }

    return
}

function Assert-IncidentFactControlDocumented {
    <#
    .SYNOPSIS
    Stops incident records that mention inference-based failures without documenting fact-control remediation.

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

    $mentionsInferenceFailure = (
        $Text.Contains('推測') -or
        $Text.Contains('憶測') -or
        $Text.Contains('判断ミス')
    )

    if (-not $mentionsInferenceFailure) {
        return
    }

    $hasRequiredFactControl = (
        $Text.Contains('事実確認不足') -and
        $Text.Contains('確認すべきだった事実') -and
        $Text.Contains('再発防止')
    )

    if (-not $hasRequiredFactControl) {
        throw "AGENTS HOOK STOP: incident record with inference-based failure must document fact-control remediation: $RepositoryPath"
    }
}

function Assert-IncidentControlDefectHasLayer {
    <#
    .SYNOPSIS
    Stops control-defect incident records unless a control layer is documented.

    .PARAMETER Text
    Incident record Markdown text.

    .PARAMETER RepositoryPath
    Incident record path used in error messages.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    $mentionsControlDefect = (
        $Text.Contains('制御不備') -or
        $Text.Contains('制御系') -or
        $Text.Contains('制御不備') -or
        $Text.Contains('制御系の設計') -or
        $Text.Contains('原則不遵守') -or
        $Text.Contains('厳守されていない')
    )

    if (-not $mentionsControlDefect) {
        return
    }

    $documentsControlLayer = (
        $Text.Contains('応答前制御') -or
        $Text.Contains('作業前制御') -or
        $Text.Contains('ツール実行前制御') -or
        $Text.Contains('ファイル編集前制御') -or
        $Text.Contains('実行中制御') -or
        $Text.Contains('報告前制御') -or
        $Text.Contains('GitHook制御') -or
        $Text.Contains('事後監査制御') -or
        $Text.Contains('制御区分：')
    )

    if (-not $documentsControlLayer) {
        throw "AGENTS HOOK STOP: control-defect incident record must document the control layer that stops or routes the violation: $RepositoryPath"
    }
}

function Assert-IncidentScopeChangeDocumented {
    <#
    .SYNOPSIS
    Stops scope-change incident records that omit the original scope and narrowed scope.

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

    $mentionsScopeChange = (
        ($Text.Contains('スコープ') -and ($Text.Contains('狭め') -or $Text.Contains('限定'))) -or
        $Text.Contains('指示範囲の不当な限定')
    )

    if (-not $mentionsScopeChange) {
        return
    }

    $hasRequiredScopeControl = (
        $Text.Contains('元の指示範囲') -and
        $Text.Contains('不適切に狭めた範囲') -and
        $Text.Contains('再発防止')
    )

    if (-not $hasRequiredScopeControl) {
        throw "AGENTS HOOK STOP: scope-change incident record must document original scope, narrowed scope, and recurrence prevention: $RepositoryPath"
    }
}

function Assert-IncidentDeployScopeBoundaryDocumented {
    <#
    .SYNOPSIS
    Stops incident records about commit/deploy scope boundaries unless the pending, reflected, and omitted changes are documented.

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

    $mentionsDeployScopeBoundary = (
        $Text.Contains('stash') -or
        $Text.Contains('デプロイ対象') -or
        $Text.Contains('積み残し') -or
        $Text.Contains('対象外変更') -or
        $Text.Contains('保留変更') -or
        (
            $Text.Contains('未反映') -and
            (
                $Text.Contains('保留変更') -or
                $Text.Contains('除外') -or
                $Text.Contains('デプロイ対象') -or
                $Text.Contains('対象外変更')
            )
        ) -or
        (
            $Text.Contains('branch-finalize') -and
            (
                $Text.Contains('保留変更') -or
                $Text.Contains('除外') -or
                $Text.Contains('unstaged') -or
                $Text.Contains('untracked')
            )
        )
    )

    if (-not $mentionsDeployScopeBoundary) {
        return
    }

    $hasDeployScopeBoundary = (
        $Text.Contains('元の保留変更') -and
        $Text.Contains('実際に反映した変更') -and
        $Text.Contains('反映しなかった変更') -and
        $Text.Contains('ユーザー確認の有無') -and
        $Text.Contains('復旧案')
    )

    if (-not $hasDeployScopeBoundary) {
        throw "AGENTS HOOK STOP: incident record about commit/deploy scope boundaries must document pending changes, reflected changes, omitted changes, user confirmation, and recovery proposal: $RepositoryPath"
    }
}

function Assert-IncidentGateSectionDocumented {
    <#
    .SYNOPSIS
    Stops incident records that do not identify the gate that should have stopped the incident.

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

    $sectionBody = Get-MarkdownSectionBody -Text $Text -Heading '発生前に停止できたはずのゲート：'

    if ($null -eq $sectionBody) {
        throw "AGENTS HOOK STOP: incident record must include the gate that should have stopped the incident: $RepositoryPath"
    }

    if ([string]::IsNullOrWhiteSpace($sectionBody)) {
        throw "AGENTS HOOK STOP: incident record gate section must not be empty: $RepositoryPath"
    }

    if ($sectionBody -match '(?m)^\s*(未確認|未実施|不明)') {
        throw "AGENTS HOOK STOP: incident record gate section must be confirmed: $RepositoryPath"
    }
}

function Assert-IncidentAuditSectionsDocumented {
    <#
    .SYNOPSIS
    Stops incident records that omit root-cause audit fields.

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

    $requiredHeadings = @(
        '発生時点：',
        '本来作用すべき制御：',
        '実際に作用した制御：',
        '制御が効かなかった理由：',
        '既存再発防止策が効かなかった理由：',
        '同種過去インシデント：',
        '再発防止策の作用タイミング：',
        '再発防止策の検証方法：',
        '制御区分：',
        '残存リスク：',
        '自己検知・自己報告の成否：'
    )

    foreach ($heading in $requiredHeadings) {
        $sectionBody = Get-MarkdownSectionBody -Text $Text -Heading $heading

        if ($null -eq $sectionBody) {
            throw "AGENTS HOOK STOP: incident record must include audit section '$heading': $RepositoryPath"
        }

        if ([string]::IsNullOrWhiteSpace($sectionBody)) {
            throw "AGENTS HOOK STOP: incident record audit section must not be empty '$heading': $RepositoryPath"
        }

        if ($sectionBody -match '(?m)^\s*(未確認|未実施|不明)') {
            throw "AGENTS HOOK STOP: incident record audit section must be confirmed '$heading': $RepositoryPath"
        }
    }
}

function Assert-DevelopmentRecordsIncludeFactControlSections {
    <#
    .SYNOPSIS
    Stops development records that omit fact-control sections required for investigation records.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    foreach ($path in @($StagedPaths)) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $normalizedPath = $path.Replace('\', '/')
        if ($normalizedPath -notlike 'docs/development-records/*.md') {
            continue
        }

        if ($normalizedPath -eq 'docs/development-records/README.md') {
            continue
        }

        $text = (@(Invoke-GitOutput -GitArguments @('show', ":$normalizedPath")) -join "`n")
        foreach ($heading in @('確認対象', '確認結果', '未確認事項')) {
            $body = Get-MarkdownSectionBody -Text $text -Heading $heading
            if ($null -eq $body -or [string]::IsNullOrWhiteSpace($body)) {
                throw "AGENTS HOOK STOP: development record must include non-empty '$heading' section: $normalizedPath"
            }
        }
    }
}

function Assert-ExternalVerificationClaimsIncludeContext {
    <#
    .SYNOPSIS
    Stops documentation from claiming external verification success without identifying what was verified.

    .PARAMETER StagedPaths
    Staged repository paths.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string[]]$StagedPaths = @()
    )

    foreach ($path in @($StagedPaths)) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $normalizedPath = $path.Replace('\', '/')
        $isTrackedDocumentationScope = (
            $normalizedPath -match '^docs/[^/]+\.md$' -or
            $normalizedPath -match '^docs/ai-progress/[^/]+\.md$' -or
            $normalizedPath -match '^docs/development-records/[^/]+\.md$'
        )

        if (-not $isTrackedDocumentationScope) {
            continue
        }

        $text = (@(Invoke-GitOutput -GitArguments @('show', ":$normalizedPath")) -join "`n")
        $mentionsExternalTarget = (
            $text -match '(?i)(pipeline|stack|site|deploy|deployment|CodePipeline|CodeBuild|CloudFormation)' -or
            $text -match '(外部環境|デプロイ|検証サイト)'
        )
        $claimsVerificationSuccess = (
            $text -match '(?i)(Succeeded|UPDATE_COMPLETE|200 OK)' -or
            $text -match '(検証完了|確認完了|成功)'
        )

        if (-not ($mentionsExternalTarget -and $claimsVerificationSuccess)) {
            continue
        }

        $hasVerificationContext = (
            $text.Contains('確認対象') -and
            $text.Contains('確認結果') -and
            (
                $text -match '(?i)source revision' -or
                $text -match '(?i)execution id' -or
                $text -match '(?i)commit' -or
                $text.Contains('対象差分')
            )
        )

        if (-not $hasVerificationContext) {
            throw "AGENTS HOOK STOP: external verification claims must include target, result, and revision/execution context: $normalizedPath"
        }
    }
}

function Assert-AiWorkGuardAuthorized {
    <#
    .SYNOPSIS
    Stops AI/Codex commits when the opt-in work guard is enabled without explicit authorization.
    #>
    if ($env:AGENTS_AI_WORK_GUARD -ne '1') {
        return
    }

    if ($env:AGENTS_USER_WORK_AUTHORIZED -eq '1') {
        return
    }

    throw 'AGENTS HOOK STOP: AI/Codex work guard requires AGENTS_USER_WORK_AUTHORIZED=1 before committing changes.'
}

function Get-MarkdownSectionBody {
    <#
    .SYNOPSIS
    Returns the body of a Markdown or incident-record section.

    .PARAMETER Text
    Markdown text to inspect.

    .PARAMETER Heading
    Heading text without the leading hashes.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Heading
    )

    $escapedHeading = [regex]::Escape($Heading)
    $plainSectionHeadings = @(
        'タイトル：',
        '背景：',
        '発生インシデントの説明：',
        '定量記録：',
        'なぜ発生したのか：',
        '何に違反したのか：',
        '発生時点：',
        '本来作用すべき制御：',
        '実際に作用した制御：',
        '制御が効かなかった理由：',
        '既存再発防止策が効かなかった理由：',
        '同種過去インシデント：',
        '発生前に停止できたはずのゲート：',
        '再発防止策の作用タイミング：',
        '再発防止策の検証方法：',
        '制御区分：',
        '残存リスク：',
        '自己検知・自己報告の成否：',
        '制御不備または原則不遵守：',
        '対応策としての制御系修正：',
        '対応策としての関連ドキュメント修正：'
    )
    $plainHeadingPattern = (($plainSectionHeadings | ForEach-Object { [regex]::Escape($_) }) -join '|')
    $match = [regex]::Match($Text, "(?ms)^(?:#{1,6}\s+)?$escapedHeading\s*\r?\n(?<body>.*?)(?=^(?:#{1,6}\s+.+|(?:$plainHeadingPattern)\s*)\r?$|\z)")

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
        $Text.Contains('追加コスト') -or
        $Text.Contains('上限超過') -or
        $Text.Contains('クレジット') -or
        $Text.Contains('課金') -or
        $Text.Contains('費用') -or
        ($Text -match 'staging pipeline stack.*UPDATE_COMPLETE') -or
        ($Text -match 'pipeline.*上限') -or
        ($Text -match 'pipeline.*コスト') -or
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

function Get-CommitMessageMarkerBody {
    <#
    .SYNOPSIS
    Returns the same-line body for a commit message marker.

    .PARAMETER Message
    Commit message text.

    .PARAMETER Marker
    Marker text ending with a colon.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [Parameter(Mandatory = $true)]
        [string]$Marker
    )

    $escapedMarker = [regex]::Escape($Marker)
    $match = [regex]::Match($Message, "(?m)^\s*[-*]?\s*$escapedMarker\s*(?<body>.*\S)\s*$")

    if (-not $match.Success) {
        return $null
    }

    return $match.Groups['body'].Value.Trim()
}

function Assert-CommitMessageMarkerBodiesDocumented {
    <#
    .SYNOPSIS
    Stops commit messages whose required marker bodies are empty or explicitly unverified.

    .PARAMETER Message
    Commit message text.

    .PARAMETER Markers
    Detail markers whose same-line body must be documented.

    .PARAMETER Context
    Human-readable context for error messages.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [Parameter(Mandatory = $true)]
        [string[]]$Markers,

        [Parameter(Mandatory = $true)]
        [string]$Context
    )

    $invalidMarkers = @()

    foreach ($marker in $Markers) {
        $body = Get-CommitMessageMarkerBody -Message $Message -Marker $marker

        if ($null -eq $body -or [string]::IsNullOrWhiteSpace($body) -or $body -match '^(未確認|未実施|不明)\s*$') {
            $invalidMarkers += $marker
        }
    }

    if ($invalidMarkers.Count -gt 0) {
        throw "AGENTS HOOK STOP: commit message $Context marker bodies must be documented. Invalid: $($invalidMarkers -join ', ')"
    }
}

function Assert-CommitMessageIncludesPrincipleGate {
    <#
    .SYNOPSIS
    Stops commit messages that do not include the full principle confirmation gate.

    .PARAMETER MessagePath
    Commit message file path passed by Git.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$MessagePath
    )

    $branch = Get-CurrentBranch

    if ((Test-IsProtectedBranch -BranchName $branch) -and (Test-IsBranchFinalizeContext)) {
        return
    }

    $message = Get-Content -LiteralPath $MessagePath -Raw -Encoding utf8
    $missingMarkers = @()

    foreach ($marker in $PrincipleCommitMessageMarkers) {
        if (-not $message.Contains($marker)) {
            $missingMarkers += $marker
        }
    }

    if ($missingMarkers.Count -gt 0) {
        throw "AGENTS HOOK STOP: commit message must include full principle confirmation markers. Missing: $($missingMarkers -join ', ')"
    }

    Assert-CommitMessageMarkerBodiesDocumented -Message $message -Markers $PrincipleCommitMessageDetailMarkers -Context 'principle gate'
}

function Assert-ExternalAssetCommitMessageApproved {
    <#
    .SYNOPSIS
    Stops external asset acquisition changes unless commit message documents approval evidence.

    .PARAMETER MessagePath
    Commit message file path passed by Git.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$MessagePath
    )

    $stagedPaths = Get-StagedPaths
    $matches = @(Get-StagedExternalAssetAcquisitionMatches -StagedPaths $stagedPaths)

    if ($matches.Count -eq 0) {
        return
    }

    $branch = Get-CurrentBranch

    if ((Test-IsProtectedBranch -BranchName $branch) -and (Test-IsBranchFinalizeContext)) {
        return
    }

    $message = Get-Content -LiteralPath $MessagePath -Raw -Encoding utf8
    $missingMarkers = @()

    foreach ($marker in $ExternalAssetCommitMessageMarkers) {
        if (-not $message.Contains($marker)) {
            $missingMarkers += $marker
        }
    }

    if ($missingMarkers.Count -gt 0) {
        throw "AGENTS HOOK STOP: external asset acquisition changes require commit message approval markers. Missing: $($missingMarkers -join ', ') Matches: $($matches -join '; ')"
    }

    Assert-CommitMessageMarkerBodiesDocumented -Message $message -Markers $ExternalAssetCommitMessageMarkers -Context 'external asset approval'
}

function Assert-ControlSystemCommitMessageApproved {
    <#
    .SYNOPSIS
    Stops control-system file changes unless commit message documents explicit approval.

    .PARAMETER MessagePath
    Commit message file path passed by Git.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$MessagePath
    )

    $controlPaths = @(Get-StagedControlSystemPaths)

    if ($controlPaths.Count -eq 0) {
        return
    }

    $branch = Get-CurrentBranch

    if ((Test-IsProtectedBranch -BranchName $branch) -and (Test-IsBranchFinalizeContext)) {
        return
    }

    $message = Get-Content -LiteralPath $MessagePath -Raw -Encoding utf8
    $missingMarkers = @()

    foreach ($marker in $ControlSystemCommitMessageMarkers) {
        if (-not $message.Contains($marker)) {
            $missingMarkers += $marker
        }
    }

    if ($missingMarkers.Count -gt 0) {
        throw "AGENTS HOOK STOP: control-system changes require commit message approval markers. Missing: $($missingMarkers -join ', ') Paths: $($controlPaths -join ', ')"
    }

    Assert-CommitMessageMarkerBodiesDocumented -Message $message -Markers $ControlSystemCommitMessageMarkers -Context 'control-system approval'
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

function Test-IsZeroSha {
    <#
    .SYNOPSIS
    Returns true when a Git SHA field represents the all-zero null object.

    .PARAMETER Sha
    SHA text from pre-push stdin.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Sha
    )

    return ($Sha -match '^0{40}$')
}

function Test-IsNonDeploymentPipelinePath {
    <#
    .SYNOPSIS
    Returns true for repository paths that do not require a deployment pipeline run by themselves.

    .PARAMETER RepositoryPath
    Slash-separated repository-relative path.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryPath
    )

    return (
        $RepositoryPath -eq 'AGENTS.md' -or
        $RepositoryPath -like 'docs/*' -or
        $RepositoryPath -like '.githooks/*' -or
        $RepositoryPath -eq 'scripts/agents-compliance-check.ps1' -or
        $RepositoryPath -eq 'scripts/branch-finalize-next.ps1'
    )
}

function Get-PushedChangePaths {
    <#
    .SYNOPSIS
    Returns changed paths for a pre-push ref update.

    .PARAMETER LocalSha
    Local SHA being pushed.

    .PARAMETER RemoteSha
    Remote SHA before the push.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$LocalSha,

        [Parameter(Mandatory = $true)]
        [string]$RemoteSha
    )

    if (Test-IsZeroSha -Sha $LocalSha) {
        return @()
    }

    if (Test-IsZeroSha -Sha $RemoteSha) {
        return @(Invoke-GitOutput -GitArguments @('diff-tree', '--no-commit-id', '--name-only', '-r', $LocalSha))
    }

    return @(Invoke-GitOutput -GitArguments @('diff', '--name-only', $RemoteSha, $LocalSha))
}

function Assert-AiProtectedPushChangesAreDeployableOrApproved {
    <#
    .SYNOPSIS
    Stops AI protected branch pushes that only contain documentation or development-environment changes.

    .PARAMETER RefUpdates
    Parsed pre-push ref update objects.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [object[]]$RefUpdates = @()
    )

    $protectedUpdates = @($RefUpdates | Where-Object { Test-IsProtectedBranch -BranchName $_.RemoteBranch })

    if ($protectedUpdates.Count -eq 0) {
        return
    }

    $changedPathMap = @{}

    foreach ($update in $protectedUpdates) {
        $paths = Get-PushedChangePaths -LocalSha $update.LocalSha -RemoteSha $update.RemoteSha

        foreach ($path in $paths) {
            $normalizedPath = ([string]$path).Replace('\', '/').Trim()

            if (-not [string]::IsNullOrWhiteSpace($normalizedPath)) {
                $changedPathMap[$normalizedPath] = $true
            }
        }
    }

    $changedPaths = @($changedPathMap.Keys | Sort-Object)

    if ($changedPaths.Count -eq 0) {
        return
    }

    $nonDeploymentOnly = $true

    foreach ($path in $changedPaths) {
        if (-not (Test-IsNonDeploymentPipelinePath -RepositoryPath $path)) {
            $nonDeploymentOnly = $false
            break
        }
    }

    if (-not $nonDeploymentOnly) {
        return
    }

    if (Test-EnvironmentFlagSet -Name $NonDeploymentPipelinePushApprovalVariable) {
        Write-Output "AGENTS HOOK PASS: non-deployment protected branch push explicitly approved by $NonDeploymentPipelinePushApprovalVariable."
        return
    }

    throw "AGENTS HOOK STOP: AI protected branch push contains only non-deployment changes and would trigger an unauthorized pipeline run without $NonDeploymentPipelinePushApprovalVariable=1. Paths: $($changedPaths -join ', ')"
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

    $refUpdates = @()
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

        $localSha = [string]$columns[1]
        $remoteRef = [string]$columns[2]
        $remoteSha = [string]$columns[3]
        $remoteBranch = Convert-RefToBranchName -RefName $remoteRef

        if (Test-IsProtectedBranch -BranchName $remoteBranch) {
            $blockedBranches += $remoteBranch
            $refUpdates += [pscustomobject]@{
                LocalSha = $localSha
                RemoteSha = $remoteSha
                RemoteBranch = $remoteBranch
            }
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
        Assert-AiProtectedPushChangesAreDeployableOrApproved -RefUpdates $refUpdates
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
    Assert-AiWorkGuardAuthorized
    $stagedPaths = Get-StagedPaths
    Assert-PrincipleContentImmutable
    Assert-ControlSystemChangesAuthorized
    Assert-DeliverableDocumentsHaveNoEvidenceLabels -StagedPaths $stagedPaths
    Assert-ExternalAssetChangesApproved -StagedPaths $stagedPaths
    Assert-NoFallbackContinuationAdded -StagedPaths $stagedPaths
    Assert-PipelineTriggerDenylistNotReferencedByDeploymentSources -StagedPaths $stagedPaths
    Assert-DevelopmentRecordsIncludeFactControlSections -StagedPaths $stagedPaths
    Assert-ExternalVerificationClaimsIncludeContext -StagedPaths $stagedPaths
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
Assert-CommitMessageIncludesPrincipleGate -MessagePath $CommitMessagePath
Assert-ExternalAssetCommitMessageApproved -MessagePath $CommitMessagePath
Assert-ControlSystemCommitMessageApproved -MessagePath $CommitMessagePath
Assert-ProtectedBranchCommitMessageAllowed -MessagePath $CommitMessagePath
Write-Output 'AGENTS HOOK PASS: commit-msg checks completed.'
exit 0
