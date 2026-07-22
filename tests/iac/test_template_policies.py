"""IaC スナップショット/ポリシーテスト（`template.yaml` ほか）.

本モジュールは tasks.md 5.5 に対応し、SAM/CloudFormation テンプレート
（`template.yaml` / `dependencies.yaml` / `bucketpolicy.yaml`）が要件・設計で
定めたセキュリティ・コスト・構成上のポリシーを満たすことを、テンプレートを
構造的に解析（パース）して検証する（出典: tasks.md 5.5、design.md「Testing
Strategy > スナップショット/ポリシーテスト（IaC）」）。

検証項目（合成/解析したテンプレートに対して）:
    1. SnapStart 不在（R2-1/R2-2）: いずれのリソースにも `SnapStart` プロパティが
       存在しない（新規 SnapStart-Cached-GB-S を発生させない構成）。
    2. SES IAM 最小権限・ワイルドカード不在（R6-2/R9-3）: Contact_Function の実行
       ロールが `ses:SendEmail` に限定され、Action/Resource に全権限ワイルドカード
       （`*` / `service:*`）を含まず、SES Resource が検証済み identity ARN に限定。
    3. S3 OAC 経由のみ許可（R9-2/R9-6）: バケットポリシーが CloudFront OAC
       （`AWS:SourceArn`）経由のみ許可し、公開直接アクセスをブロックする構成で
       `dependencies.yaml` と整合する。
    4. ResponseHeadersPolicy に CSP と redirect-to-https（R7-1/R7-3）: CloudFront の
       表示 Behavior に CSP を含む ResponseHeadersPolicy が適用され、
       `ViewerProtocolPolicy: redirect-to-https` で HTTPS を強制する。
    5. ContactApi スロットリング設定（R8-6）: `ContactApi` にレート/バースト上限が
       設定されている。
    6. Contact_Function 予約同時実行数上限（R8-6）: `ReservedConcurrentExecutions`
       が設定されている。
    7. WAF リソース既定不在（R8-6）: 合成テンプレートに `AWS::WAFv2::WebACL` /
       `AWS::WAFv2::WebACLAssociation` が既定で含まれない（コメントアウト維持）。

解析方針と「合成テンプレート」についての事実（誠実性のため明記）:
    design.md は「`sam build` 相当の合成テンプレート」を検証対象と記す。SAM の
    `AWS::Serverless::Function` は CloudFormation の Lambda 関数 + IAM ロール等へ
    変換されるが、本モジュールが検証する各ポリシー（SnapStart の有無、
    `Properties.Policies` に記述された SES/SSM の最小権限・ワイルドカード不在、
    ResponseHeadersPolicy、API スロットリング、予約同時実行数、WAF 不在）は
    いずれも「テンプレート原本に明示記述された値」であり、SAM 変換はこれらを
    追加・削除しない（SnapStart は明示指定時のみ付与される。IAM ワイルドカードは
    原本に無ければ変換でも増えない）。したがって原本テンプレートの構造解析は
    上記項目について変換後と等価であり、かつ AWS 認証情報・ネットワーク・Docker
    （実 `sam build`/transform の前提）に依存せず決定的に検証できる。

外部依存とライセンス（第二原則6・着手時ライセンス確認）:
    - PyYAML 6.0.3（MIT License）を使用する。CloudFormation の短縮組込み関数タグ
      （`!Ref` / `!Sub` / `!GetAtt` / `!Equals` / `!Not` / `!FindInMap` / `!If` 等）を
      解釈するため、`yaml.SafeLoader` を継承した専用ローダにマルチコンストラクタを
      登録する（cfn-lint / aws-sam-cli と同一の確立した手法）。ライセンスは
      `requirements-dev.txt` に記載する（`pip show PyYAML` の License 欄 = MIT、
      OSI Approved: MIT License を確認済み。開発・テスト時のみ使用し Lambda 配布物
      には同梱しない）。
    - 標準ライブラリ `unittest` を用いる（既存テスト方式と一貫、
      出典: `contact_function/tests/*`）。

実行コマンド（プロジェクトルートから）:
    python -m unittest tests.iac.test_template_policies -v
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

# ------------------------------------------------------------------------------
# テンプレートファイルの所在（リポジトリルート基準）。
# 本ファイルは tests/iac/ に置かれるため、parents[2] がリポジトリルートである
# （tests/iac/test_template_policies.py -> tests/iac -> tests -> ルート）。
# ------------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_PATH = _REPO_ROOT / "template.yaml"
_DEPENDENCIES_PATH = _REPO_ROOT / "dependencies.yaml"
_BUCKETPOLICY_PATH = _REPO_ROOT / "bucketpolicy.yaml"


class _CfnLoader(yaml.SafeLoader):
    """CloudFormation 短縮組込み関数タグを解釈する SafeLoader サブクラス.

    `yaml.SafeLoader` を基底とし、危険な Python オブジェクト構築を行わない。
    `!Ref` 等の短縮タグを正規表現ではなくノード種別に応じて忠実に辞書表現へ
    変換するためのマルチコンストラクタを別途登録する（登録は本クラス定義直後）。
    """


def _cfn_multi_constructor(
    loader: _CfnLoader, tag_suffix: str, node: yaml.Node
) -> dict[str, Any]:
    """CloudFormation 短縮タグを CloudFormation JSON 形式の辞書へ変換する.

    例: `!Ref X` -> `{"Ref": "X"}`、`!Sub "..."` -> `{"Fn::Sub": "..."}`、
    `!GetAtt A.B` -> `{"Fn::GetAtt": "A.B"}`、`!Equals [a, b]` ->
    `{"Fn::Equals": [a, b]}`。これは cfn-lint / aws-sam-cli と同じ正規化であり、
    以降の検証ロジックは長形式（`Fn::ImportValue` 等の素の辞書）と同一構造で
    扱える。

    Args:
        loader: 解析中のローダ（本サブクラスのインスタンス）。
        tag_suffix: `!` を除いたタグ名（例: "Ref", "Sub", "GetAtt"）。
        node: 対象ノード（スカラ/シーケンス/マッピングのいずれか）。

    Returns:
        dict[str, Any]: CloudFormation JSON 形式の 1 要素辞書。

    Raises:
        yaml.constructor.ConstructorError: 想定外のノード種別を検出した場合。
            フォールバックせず明示的に失敗させる（第三原則3、解析の健全性担保）。
    """
    # `Ref` のみキー名が `Ref`、それ以外は `Fn::<Name>` が CloudFormation の正規形。
    key = "Ref" if tag_suffix == "Ref" else f"Fn::{tag_suffix}"

    # ノード種別に応じて値を忠実に構築する（deep=True で入れ子も完全に解決）。
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    else:
        # 未知のノード種別は握りつぶさず明示的に失敗させる（フォールバック禁止）。
        raise yaml.constructor.ConstructorError(
            None,
            None,
            f"未対応の CloudFormation タグノード種別: !{tag_suffix} ({type(node)!r})",
            node.start_mark,
        )
    return {key: value}


# `!` で始まる全短縮タグを上記コンストラクタで処理する（個別列挙せず網羅する）。
_CfnLoader.add_multi_constructor("!", _cfn_multi_constructor)


def _load_yaml(path: Path) -> dict[str, Any]:
    """指定パスの CloudFormation/SAM テンプレートを解析して辞書で返す.

    Args:
        path: 解析対象テンプレートの絶対パス。

    Returns:
        dict[str, Any]: テンプレートのトップレベルマッピング。

    Raises:
        FileNotFoundError: テンプレートファイルが存在しない場合（フォールバック
            せず明示的に失敗させ、事実として欠落を報告する）。
        TypeError: 解析結果がマッピングでない場合（想定外の構造を握りつぶさない）。
    """
    # ファイル欠落は握りつぶさず明示的に失敗させる（第三原則3、事実報告）。
    if not path.exists():
        raise FileNotFoundError(f"テンプレートが見つからない: {path}")

    # UTF-8 で読み取り、CloudFormation 短縮タグ対応ローダで解析する。
    with path.open(encoding="utf-8") as stream:
        document = yaml.load(stream, Loader=_CfnLoader)

    # トップレベルがマッピングでない場合は想定外構造として明示的に失敗させる。
    if not isinstance(document, dict):
        raise TypeError(
            f"テンプレートのトップレベルがマッピングでない: {path} "
            f"(実際: {type(document)!r})"
        )
    return document


def _resources(template: dict[str, Any]) -> dict[str, Any]:
    """テンプレートの `Resources` セクションを取り出す.

    Args:
        template: 解析済みテンプレート辞書。

    Returns:
        dict[str, Any]: 論理 ID をキーとするリソース定義の辞書。

    Raises:
        KeyError: `Resources` セクションが存在しない場合（明示的に失敗させる）。
        TypeError: `Resources` がマッピングでない場合（想定外を握りつぶさない）。
    """
    # Resources 欠落は握りつぶさず失敗させる（テンプレートとして不正）。
    if "Resources" not in template:
        raise KeyError("テンプレートに Resources セクションが存在しない")
    resources = template["Resources"]
    if not isinstance(resources, dict):
        raise TypeError(f"Resources がマッピングでない (実際: {type(resources)!r})")
    return resources


def _resources_of_type(
    resources: dict[str, Any], cfn_type: str
) -> dict[str, dict[str, Any]]:
    """指定した CloudFormation リソースタイプのリソースを論理 ID 付きで抽出する.

    Args:
        resources: `Resources` セクションの辞書。
        cfn_type: 抽出対象のリソースタイプ（例: "AWS::Serverless::Function"）。

    Returns:
        dict[str, dict[str, Any]]: 論理 ID をキー、リソース定義を値とする辞書。
    """
    # Type が完全一致するリソースのみを収集する（部分一致では判定しない）。
    matched: dict[str, dict[str, Any]] = {}
    for logical_id, body in resources.items():
        if isinstance(body, dict) and body.get("Type") == cfn_type:
            matched[logical_id] = body
    return matched


def _resource_types_with_prefix(
    resources: dict[str, Any], type_prefix: str
) -> list[str]:
    """指定プレフィックスで始まるリソースタイプの論理 ID 一覧を返す.

    WAF リソース（`AWS::WAFv2::` 接頭辞）の存在有無判定に用いる。

    Args:
        resources: `Resources` セクションの辞書。
        type_prefix: 判定するリソースタイプの接頭辞。

    Returns:
        list[str]: 条件に合致した論理 ID の一覧（存在しなければ空）。
    """
    # Type が接頭辞一致するリソースの論理 ID を列挙する。
    return [
        logical_id
        for logical_id, body in resources.items()
        if isinstance(body, dict)
        and isinstance(body.get("Type"), str)
        and body["Type"].startswith(type_prefix)
    ]


def _find_all_keys(obj: Any, target_key: str) -> list[Any]:
    """任意の入れ子構造から指定キー名の値を再帰的にすべて収集する.

    `SnapStart` のようなプロパティがテンプレートのどこにも存在しないことを
    網羅的に検証するために用いる（特定リソースに限定せず全探索する）。

    Args:
        obj: 探索対象（辞書・リスト・スカラのいずれか）。
        target_key: 収集するキー名。

    Returns:
        list[Any]: 見つかった値の一覧（見つからなければ空）。
    """
    # 辞書・リストを再帰的に降下し、target_key に一致する値を集める。
    found: list[Any] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == target_key:
                found.append(value)
            found.extend(_find_all_keys(value, target_key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_all_keys(item, target_key))
    return found


def _as_scalar(value: Any) -> str:
    """スカラ文字列、または単一組込み関数辞書から代表文字列を取り出す.

    `"s3:GetObject"`（素の文字列）や `{"Fn::Sub": "arn:..."}`・`{"Ref": "X"}`
    のような 1 要素辞書から、ポリシー照合に用いる文字列表現を抽出する。

    Args:
        value: 抽出対象（文字列、または `Fn::*` / `Ref` の 1 要素辞書）。

    Returns:
        str: 抽出した文字列表現。

    Raises:
        TypeError: 文字列でも単一組込み関数辞書でもない場合（想定外を握りつぶさない）。
    """
    # 素の文字列はそのまま返す。
    if isinstance(value, str):
        return value
    # 組込み関数の 1 要素辞書（Fn::Sub / Ref 等）は内側の値を文字列化して返す。
    if isinstance(value, dict) and len(value) == 1:
        inner = next(iter(value.values()))
        if isinstance(inner, str):
            return inner
        # Fn::Sub の第2形式（[template, {vars}]）等はテンプレート文字列を採用する。
        if isinstance(inner, list) and inner and isinstance(inner[0], str):
            return inner[0]
    # 上記以外は照合に使えないため明示的に失敗させる（フォールバック禁止）。
    raise TypeError(f"スカラ抽出に失敗した値: {value!r}")


def _as_list(value: Any) -> list[Any]:
    """単一値またはリストを、常にリストへ正規化する.

    IAM の `Action` / `Resource` はスカラとリストの双方が許容されるため、
    照合前に一様なリストへ整える。

    Args:
        value: スカラまたはリスト。

    Returns:
        list[Any]: 正規化したリスト。
    """
    # リストはそのまま、単一値は 1 要素リストへ包む。
    return list(value) if isinstance(value, list) else [value]


def _iter_policy_statements(function_body: dict[str, Any]) -> list[dict[str, Any]]:
    """SAM 関数の `Properties.Policies` からインライン IAM ステートメントを抽出する.

    `Policies` は「管理ポリシー名（文字列）」と「`{Statement: [...]}` 形式の
    インラインポリシー辞書」の混在リストである（出典: SAM `Policies` 仕様、
    template.yaml ContactFunction）。本関数はインラインポリシー辞書に含まれる
    個々のステートメントのみを平坦化して返す（管理ポリシー名の文字列は対象外）。

    Args:
        function_body: `AWS::Serverless::Function` リソース定義。

    Returns:
        list[dict[str, Any]]: IAM ステートメント辞書の一覧。
    """
    # Properties.Policies を取得する（未定義なら空リストとして扱う=ステートメント無し）。
    properties = function_body.get("Properties", {})
    policies = properties.get("Policies", [])
    statements: list[dict[str, Any]] = []
    for policy in _as_list(policies):
        # 管理ポリシー名（例: "AWSLambdaBasicExecutionRole"）は文字列のため対象外。
        if isinstance(policy, dict) and "Statement" in policy:
            for statement in _as_list(policy["Statement"]):
                if isinstance(statement, dict):
                    statements.append(statement)
    return statements


# ------------------------------------------------------------------------------
# テンプレートはモジュール読み込み時に一度だけ解析し、各テストで共有する
# （解析は副作用のない純粋な読み取りであり、テスト間で不変）。
# ------------------------------------------------------------------------------
_TEMPLATE = _load_yaml(_TEMPLATE_PATH)
_TEMPLATE_RESOURCES = _resources(_TEMPLATE)
_DEPENDENCIES = _load_yaml(_DEPENDENCIES_PATH)
_DEPENDENCIES_RESOURCES = _resources(_DEPENDENCIES)
_BUCKETPOLICY = _load_yaml(_BUCKETPOLICY_PATH)
_BUCKETPOLICY_RESOURCES = _resources(_BUCKETPOLICY)

# 論理 ID 定数（テンプレート原本と一致。出典: template.yaml / dependencies.yaml /
# bucketpolicy.yaml。文字列リテラルの散在を避け整合性を保つ）。
_CONTACT_FUNCTION_ID = "ContactFunction"
_CONTACT_API_ID = "ContactApi"
_DJANGO_FUNCTION_ID = "DjangoFunction"
_RESPONSE_HEADERS_POLICY_ID = "DisplayResponseHeadersPolicy"
_CLOUDFRONT_DISTRIBUTION_ID = "CloudFrontDistribution"
_STATIC_BUCKET_ID = "StaticFilesBucket"
_OAC_ID = "CloudFrontOriginAccessControl"
_BUCKET_POLICY_ID = "StaticFilesBucketPolicy"


class SnapStartAbsenceTests(unittest.TestCase):
    """SnapStart 不在の検証（R2-1/R2-2）.

    新規 SnapStart-Cached-GB-S を発生させないため、テンプレートのいずれの
    リソースにも `SnapStart` プロパティが存在しないことを網羅的に検証する
    （出典: design.md「SnapStart 撤廃」、requirements.md R2-1/R2-2、tasks.md 5.1）。
    """

    def test_no_snapstart_property_anywhere(self) -> None:
        """テンプレート全体に `SnapStart` プロパティが一切存在しない（R2-1/R2-2）."""
        # 全入れ子を再帰探索し SnapStart キーの値をすべて集める。
        found = _find_all_keys(_TEMPLATE, "SnapStart")
        self.assertEqual(
            found,
            [],
            msg=f"SnapStart プロパティが検出された（R2-2 違反）: {found!r}",
        )

    def test_lambda_functions_have_no_snapstart(self) -> None:
        """全 Serverless 関数の Properties に SnapStart が無い（R2-1/R2-2 具体確認）."""
        # SAM 関数を列挙し、各 Properties 配下に SnapStart が無いことを確認する。
        functions = _resources_of_type(
            _TEMPLATE_RESOURCES, "AWS::Serverless::Function"
        )
        # DjangoFunction と ContactFunction の 2 関数が存在することを前提とする。
        self.assertIn(_DJANGO_FUNCTION_ID, functions)
        self.assertIn(_CONTACT_FUNCTION_ID, functions)
        for logical_id, body in functions.items():
            with self.subTest(function=logical_id):
                properties = body.get("Properties", {})
                self.assertNotIn(
                    "SnapStart",
                    properties,
                    msg=f"{logical_id}.Properties に SnapStart が存在する（R2-2 違反）",
                )


class SesLeastPrivilegeTests(unittest.TestCase):
    """SES IAM 最小権限・ワイルドカード不在の検証（R6-2/R9-3）.

    Contact_Function の実行ロール（`Properties.Policies` のインライン IAM）が
    `ses:SendEmail` に限定され、Action/Resource に全権限ワイルドカード
    （`*` や `service:*`）を含まず、SES の Resource が検証済み identity ARN に
    限定されていることを検証する（出典: design.md C4、requirements.md R6-2/R9-3）。
    """

    def setUp(self) -> None:
        """ContactFunction のインライン IAM ステートメントを収集する."""
        # ContactFunction が存在することを前提とし、無ければ明示的に失敗させる。
        self.assertIn(
            _CONTACT_FUNCTION_ID,
            _TEMPLATE_RESOURCES,
            msg="ContactFunction が template.yaml に存在しない（tasks.md 5.2 未反映）",
        )
        function_body = _TEMPLATE_RESOURCES[_CONTACT_FUNCTION_ID]
        self.statements = _iter_policy_statements(function_body)
        # インライン IAM ステートメントが 1 つ以上存在すること（SES/SSM 権限付与）。
        self.assertTrue(
            self.statements,
            msg="ContactFunction にインライン IAM ステートメントが存在しない",
        )

    def _allow_actions(self) -> list[str]:
        """Effect=Allow のステートメントに含まれる全 Action を文字列で返す."""
        # 許可ステートメントの Action を平坦化して収集する。
        actions: list[str] = []
        for statement in self.statements:
            if statement.get("Effect") == "Allow" and "Action" in statement:
                actions.extend(_as_scalar(a) for a in _as_list(statement["Action"]))
        return actions

    def _allow_resources(self) -> list[str]:
        """Effect=Allow のステートメントに含まれる全 Resource を文字列で返す."""
        # 許可ステートメントの Resource を平坦化して収集する。
        resources: list[str] = []
        for statement in self.statements:
            if statement.get("Effect") == "Allow" and "Resource" in statement:
                resources.extend(
                    _as_scalar(r) for r in _as_list(statement["Resource"])
                )
        return resources

    def test_ses_send_email_action_present(self) -> None:
        """SES 送信権限として `ses:SendEmail` が付与されている（R6-1/R6-2）."""
        # SES 送信に必要な最小 Action が含まれることを確認する。
        self.assertIn(
            "ses:SendEmail",
            self._allow_actions(),
            msg="ses:SendEmail が付与されていない（R6-2）",
        )

    def test_no_wildcard_action(self) -> None:
        """Action に全権限/サービス全権限ワイルドカードが無い（R9-3）."""
        # "*"（全権限）および "service:*"（サービス全権限）を禁止する。
        for action in self._allow_actions():
            with self.subTest(action=action):
                self.assertNotEqual(
                    action,
                    "*",
                    msg="Action に全権限ワイルドカード '*' が存在する（R9-3 違反）",
                )
                self.assertFalse(
                    action.endswith(":*"),
                    msg=f"Action にサービス全権限ワイルドカードが存在する: {action}（R9-3 違反）",
                )

    def test_no_wildcard_resource(self) -> None:
        """Resource に全リソースワイルドカード `*` が無い（R9-3）."""
        # Resource が "*"（全リソース）でないことを確認する。
        for resource in self._allow_resources():
            with self.subTest(resource=resource):
                self.assertNotEqual(
                    resource,
                    "*",
                    msg="Resource に全リソースワイルドカード '*' が存在する（R9-3 違反）",
                )

    def test_ses_resource_scoped_to_verified_identity(self) -> None:
        """SES の Resource が検証済み identity ARN に限定されている（R6-2/R9-3）.

        `ses:SendEmail` を許可するステートメントの Resource が SES identity ARN
        （`:identity/` を含む ARN）に限定され、`*` でないことを確認する
        （出典: design.md C4、template.yaml ContactFunction の SES ステートメント）。
        """
        # ses:SendEmail を含む許可ステートメントを特定し、その Resource を検査する。
        ses_resources: list[str] = []
        for statement in self.statements:
            if statement.get("Effect") != "Allow":
                continue
            actions = [_as_scalar(a) for a in _as_list(statement.get("Action", []))]
            if "ses:SendEmail" in actions:
                ses_resources.extend(
                    _as_scalar(r) for r in _as_list(statement.get("Resource", []))
                )
        # SES ステートメントに Resource が存在すること。
        self.assertTrue(
            ses_resources,
            msg="ses:SendEmail ステートメントに Resource が存在しない（R6-2）",
        )
        # すべての SES Resource が identity ARN に限定されていること。
        for resource in ses_resources:
            with self.subTest(resource=resource):
                self.assertIn(
                    ":identity/",
                    resource,
                    msg=f"SES Resource が identity ARN に限定されていない: {resource}（R6-2）",
                )


class S3OacOnlyTests(unittest.TestCase):
    """S3 OAC 経由のみ許可の検証（R9-2/R9-6、dependencies.yaml/bucketpolicy.yaml 整合）.

    静的ファイルバケットへのアクセスが CloudFront OAC（`AWS:SourceArn` 条件）経由
    のみ許可され、公開直接アクセスがブロックされる構成であること、および
    `dependencies.yaml`（バケット/OAC）と `bucketpolicy.yaml`（バケットポリシー）が
    バケット名で整合していることを検証する（出典: design.md C1/C5「S3 OAC 限定」、
    requirements.md R9-2/R9-6）。
    """

    def _bucket_policy_statements(self) -> list[dict[str, Any]]:
        """bucketpolicy.yaml のバケットポリシー Statement を取り出す."""
        # StaticFilesBucketPolicy が存在することを前提とする。
        self.assertIn(
            _BUCKET_POLICY_ID,
            _BUCKETPOLICY_RESOURCES,
            msg="StaticFilesBucketPolicy が bucketpolicy.yaml に存在しない",
        )
        policy_doc = _BUCKETPOLICY_RESOURCES[_BUCKET_POLICY_ID]["Properties"][
            "PolicyDocument"
        ]
        return [s for s in _as_list(policy_doc["Statement"]) if isinstance(s, dict)]

    def test_bucket_policy_allows_only_cloudfront_service_principal(self) -> None:
        """バケットポリシーの許可主体が CloudFront サービスに限定される（R9-2/R9-6）."""
        statements = self._bucket_policy_statements()
        # 許可ステートメントが 1 つ以上存在すること。
        allow_statements = [s for s in statements if s.get("Effect") == "Allow"]
        self.assertTrue(
            allow_statements, msg="バケットポリシーに Allow ステートメントが無い"
        )
        for statement in allow_statements:
            with self.subTest(sid=statement.get("Sid")):
                principal = statement.get("Principal")
                # Principal は CloudFront サービスプリンシパルのみ（"*" は禁止）。
                self.assertIsInstance(
                    principal,
                    dict,
                    msg=f"Principal がサービス指定でない: {principal!r}（公開許可の疑い）",
                )
                self.assertEqual(
                    principal.get("Service"),
                    "cloudfront.amazonaws.com",
                    msg=f"Principal が CloudFront サービスに限定されていない: {principal!r}",
                )

    def test_bucket_policy_restricts_to_cloudfront_source_arn(self) -> None:
        """バケットポリシーが `AWS:SourceArn` 条件で CloudFront 経由に限定する（R9-6）."""
        # 許可ステートメントには CloudFront distribution を指す SourceArn 条件が必要。
        for statement in self._bucket_policy_statements():
            if statement.get("Effect") != "Allow":
                continue
            with self.subTest(sid=statement.get("Sid")):
                condition = statement.get("Condition", {})
                string_equals = condition.get("StringEquals", {})
                self.assertIn(
                    "AWS:SourceArn",
                    string_equals,
                    msg="許可条件に AWS:SourceArn（CloudFront 経由限定）が無い（R9-6 違反）",
                )
                # SourceArn は CloudFront ディストリビューション ARN を指すこと。
                source_arn = _as_scalar(string_equals["AWS:SourceArn"])
                self.assertIn(
                    "cloudfront",
                    source_arn,
                    msg=f"AWS:SourceArn が CloudFront を指していない: {source_arn}",
                )

    def test_bucket_policy_action_is_read_only(self) -> None:
        """バケットポリシーの許可 Action が読み取り（s3:GetObject）に限定される（最小権限）."""
        # 配信目的のため読み取り専用であること（書き込み等の広範権限を許さない）。
        for statement in self._bucket_policy_statements():
            if statement.get("Effect") != "Allow":
                continue
            with self.subTest(sid=statement.get("Sid")):
                actions = [
                    _as_scalar(a) for a in _as_list(statement.get("Action", []))
                ]
                self.assertEqual(
                    actions,
                    ["s3:GetObject"],
                    msg=f"バケットポリシー Action が read-only でない: {actions}",
                )

    def test_dependencies_bucket_blocks_public_access(self) -> None:
        """dependencies.yaml のバケットが公開アクセスを完全ブロックする（R9-2/R9-6）."""
        # StaticFilesBucket が存在し、4 種の PublicAccessBlock がすべて true。
        self.assertIn(
            _STATIC_BUCKET_ID,
            _DEPENDENCIES_RESOURCES,
            msg="StaticFilesBucket が dependencies.yaml に存在しない",
        )
        block = _DEPENDENCIES_RESOURCES[_STATIC_BUCKET_ID]["Properties"][
            "PublicAccessBlockConfiguration"
        ]
        for key in (
            "BlockPublicAcls",
            "BlockPublicPolicy",
            "IgnorePublicAcls",
            "RestrictPublicBuckets",
        ):
            with self.subTest(setting=key):
                self.assertTrue(
                    block.get(key),
                    msg=f"PublicAccessBlockConfiguration.{key} が true でない（R9-2 違反）",
                )

    def test_dependencies_defines_oac(self) -> None:
        """dependencies.yaml が S3 用 OAC を定義する（R9-2 整合）."""
        # OAC リソースが存在し、対象タイプが s3 であることを確認する。
        self.assertIn(
            _OAC_ID,
            _DEPENDENCIES_RESOURCES,
            msg="CloudFrontOriginAccessControl が dependencies.yaml に存在しない",
        )
        oac_config = _DEPENDENCIES_RESOURCES[_OAC_ID]["Properties"][
            "OriginAccessControlConfig"
        ]
        self.assertEqual(
            oac_config.get("OriginAccessControlOriginType"),
            "s3",
            msg="OAC の OriginType が s3 でない",
        )

    def test_bucket_name_consistency_between_files(self) -> None:
        """bucketpolicy.yaml と dependencies.yaml のバケット名が整合する（R9-6 整合）.

        bucketpolicy の `Bucket` と dependencies の `StaticFilesBucket.BucketName` が
        同一のバケット名（`cobaemon-serverless-portfolio-${Env}-static`）を指すことで、
        「同一バケットに OAC 限定ポリシーが適用される」整合を担保する。
        """
        # 両ファイルからバケット名スカラを抽出して一致を確認する。
        bucket_from_policy = _as_scalar(
            _BUCKETPOLICY_RESOURCES[_BUCKET_POLICY_ID]["Properties"]["Bucket"]
        )
        bucket_from_dependencies = _as_scalar(
            _DEPENDENCIES_RESOURCES[_STATIC_BUCKET_ID]["Properties"]["BucketName"]
        )
        self.assertEqual(
            bucket_from_policy,
            bucket_from_dependencies,
            msg=(
                "bucketpolicy.yaml と dependencies.yaml のバケット名が不一致"
                f"（policy={bucket_from_policy!r}, deps={bucket_from_dependencies!r}）"
            ),
        )


class CloudFrontSecurityHeaderTests(unittest.TestCase):
    """ResponseHeadersPolicy に CSP、CloudFront に redirect-to-https の検証（R7-1/R7-3）.

    CloudFront の表示 Behavior に CSP を含む ResponseHeadersPolicy が適用され、
    かつ全 Behavior が `ViewerProtocolPolicy: redirect-to-https` で HTTPS を強制する
    ことを検証する（出典: design.md C5/C6、requirements.md R7-1/R7-3/R7-4/R9-1）。
    """

    def _distribution_config(self) -> dict[str, Any]:
        """CloudFrontDistribution の DistributionConfig を取り出す."""
        # CloudFrontDistribution が存在することを前提とする。
        self.assertIn(
            _CLOUDFRONT_DISTRIBUTION_ID,
            _TEMPLATE_RESOURCES,
            msg="CloudFrontDistribution が template.yaml に存在しない",
        )
        return _TEMPLATE_RESOURCES[_CLOUDFRONT_DISTRIBUTION_ID]["Properties"][
            "DistributionConfig"
        ]

    def test_response_headers_policy_contains_csp(self) -> None:
        """ResponseHeadersPolicy が Content-Security-Policy を保持する（R7-1）."""
        # DisplayResponseHeadersPolicy の SecurityHeadersConfig に CSP が含まれること。
        self.assertIn(
            _RESPONSE_HEADERS_POLICY_ID,
            _TEMPLATE_RESOURCES,
            msg="DisplayResponseHeadersPolicy が template.yaml に存在しない",
        )
        policy_config = _TEMPLATE_RESOURCES[_RESPONSE_HEADERS_POLICY_ID][
            "Properties"
        ]["ResponseHeadersPolicyConfig"]
        security_headers = policy_config.get("SecurityHeadersConfig", {})
        self.assertIn(
            "ContentSecurityPolicy",
            security_headers,
            msg="SecurityHeadersConfig に ContentSecurityPolicy が無い（R7-1 違反）",
        )
        # CSP の値（ContentSecurityPolicy.ContentSecurityPolicy）が供給されていること。
        csp_block = security_headers["ContentSecurityPolicy"]
        self.assertIn(
            "ContentSecurityPolicy",
            csp_block,
            msg="ContentSecurityPolicy に CSP 値が設定されていない（R7-1 違反）",
        )

    def test_csp_parameter_default_has_directives_and_no_nonce(self) -> None:
        """CSP パラメータ既定値が CSP ディレクティブを含み nonce を含まない（R7-1/R7-2）.

        ResponseHeadersPolicy の CSP は `ContentSecurityPolicy` パラメータから供給
        される（`{"Ref": "ContentSecurityPolicy"}`）。当該パラメータ既定値が CSP
        ディレクティブ（`default-src`/`script-src`）を含み、静的配信に不適合な
        per-request nonce（`nonce`）を含まない（ハッシュベース）ことを確認する。
        """
        # CSP 値が Ref で ContentSecurityPolicy パラメータを参照していること。
        policy_config = _TEMPLATE_RESOURCES[_RESPONSE_HEADERS_POLICY_ID][
            "Properties"
        ]["ResponseHeadersPolicyConfig"]
        csp_value = policy_config["SecurityHeadersConfig"]["ContentSecurityPolicy"][
            "ContentSecurityPolicy"
        ]
        self.assertEqual(
            csp_value,
            {"Ref": "ContentSecurityPolicy"},
            msg=f"CSP 値が ContentSecurityPolicy パラメータ参照でない: {csp_value!r}",
        )
        # 参照先パラメータの既定値を検査する（テンプレート Parameters セクション）。
        parameters = _TEMPLATE.get("Parameters", {})
        self.assertIn(
            "ContentSecurityPolicy",
            parameters,
            msg="ContentSecurityPolicy パラメータが定義されていない",
        )
        default_csp = parameters["ContentSecurityPolicy"].get("Default", "")
        # CSP の主要ディレクティブを含むこと（CSP として実体を持つ）。
        self.assertIn(
            "default-src",
            default_csp,
            msg="CSP 既定値に default-src が無い（R7-1 違反）",
        )
        self.assertIn(
            "script-src",
            default_csp,
            msg="CSP 既定値に script-src が無い（R7-1 違反）",
        )
        # per-request nonce を含まないこと（ハッシュベース CSP、R7-2）。
        self.assertNotIn(
            "nonce",
            default_csp.lower(),
            msg="CSP 既定値に nonce が含まれる（ハッシュベースでない、R7-2 違反）",
        )

    def test_default_behavior_applies_response_headers_policy(self) -> None:
        """表示 Default Behavior に ResponseHeadersPolicy が適用される（R7-1）."""
        # DefaultCacheBehavior が DisplayResponseHeadersPolicy を参照すること。
        default_behavior = self._distribution_config()["DefaultCacheBehavior"]
        self.assertEqual(
            default_behavior.get("ResponseHeadersPolicyId"),
            {"Ref": _RESPONSE_HEADERS_POLICY_ID},
            msg="表示 Behavior に ResponseHeadersPolicy が適用されていない（R7-1 違反）",
        )

    def test_all_behaviors_redirect_to_https(self) -> None:
        """全 Behavior が redirect-to-https で HTTPS を強制する（R7-3/R7-4/R9-1）."""
        config = self._distribution_config()
        # Default Behavior と追加 CacheBehaviors のすべてを対象とする。
        behaviors: list[dict[str, Any]] = [config["DefaultCacheBehavior"]]
        behaviors.extend(_as_list(config.get("CacheBehaviors", [])))
        for behavior in behaviors:
            # 対象 Behavior の識別子（Default はパスパターンを持たない）。
            label = behavior.get("PathPattern", "DefaultCacheBehavior")
            with self.subTest(behavior=label):
                self.assertEqual(
                    behavior.get("ViewerProtocolPolicy"),
                    "redirect-to-https",
                    msg=f"Behavior {label} が redirect-to-https でない（R7-3 違反）",
                )


class ContactApiThrottlingTests(unittest.TestCase):
    """ContactApi スロットリング設定の検証（R8-6）.

    WAF レートベースルールの代替として、`ContactApi` のメソッド設定にレート上限
    （ThrottlingRateLimit）とバースト上限（ThrottlingBurstLimit）が設定されている
    ことを検証する（出典: design.md C7/「セキュリティ×コスト戦略」、requirements.md R8-6）。
    """

    def test_contact_api_defines_throttling_limits(self) -> None:
        """ContactApi にレート/バースト上限が設定されている（R8-6）."""
        # ContactApi が Serverless::Api として存在することを前提とする。
        self.assertIn(
            _CONTACT_API_ID,
            _TEMPLATE_RESOURCES,
            msg="ContactApi が template.yaml に存在しない（tasks.md 5.2 未反映）",
        )
        api_body = _TEMPLATE_RESOURCES[_CONTACT_API_ID]
        self.assertEqual(
            api_body.get("Type"),
            "AWS::Serverless::Api",
            msg="ContactApi の Type が AWS::Serverless::Api でない",
        )
        # MethodSettings のいずれかにレート/バースト上限が設定されていること。
        method_settings = api_body["Properties"].get("MethodSettings", [])
        self.assertTrue(
            method_settings,
            msg="ContactApi に MethodSettings が無い（スロットリング未設定、R8-6 違反）",
        )
        # レート/バースト上限が正の数値として設定された設定が 1 つ以上あること。
        has_rate = False
        has_burst = False
        for setting in _as_list(method_settings):
            rate = setting.get("ThrottlingRateLimit")
            burst = setting.get("ThrottlingBurstLimit")
            # 数値かつ正であることを確認する（bool は int の派生のため明示的に除外）。
            if (
                isinstance(rate, (int, float))
                and not isinstance(rate, bool)
                and rate > 0
            ):
                has_rate = True
            if (
                isinstance(burst, (int, float))
                and not isinstance(burst, bool)
                and burst > 0
            ):
                has_burst = True
        self.assertTrue(
            has_rate,
            msg="ContactApi に正の ThrottlingRateLimit が設定されていない（R8-6 違反）",
        )
        self.assertTrue(
            has_burst,
            msg="ContactApi に正の ThrottlingBurstLimit が設定されていない（R8-6 違反）",
        )


class ContactFunctionReservedConcurrencyTests(unittest.TestCase):
    """Contact_Function 予約同時実行数上限の検証（R8-6）.

    乱用時の爆発半径・SES 大量送信・従量課金の暴発を抑制するため、
    `ContactFunction` に `ReservedConcurrentExecutions` が設定されていることを
    検証する（出典: design.md C3/C7、requirements.md R8-6/R1）。
    """

    def test_contact_function_has_reserved_concurrency(self) -> None:
        """ContactFunction に予約同時実行数の上限が設定されている（R8-6）."""
        # ContactFunction が存在することを前提とする。
        self.assertIn(
            _CONTACT_FUNCTION_ID,
            _TEMPLATE_RESOURCES,
            msg="ContactFunction が template.yaml に存在しない（tasks.md 5.2 未反映）",
        )
        properties = _TEMPLATE_RESOURCES[_CONTACT_FUNCTION_ID]["Properties"]
        reserved = properties.get("ReservedConcurrentExecutions")
        # 設定されていること（未設定=無制限は暴発抑制にならない）。
        self.assertIsNotNone(
            reserved,
            msg="ReservedConcurrentExecutions が未設定（R8-6 違反、無制限は暴発抑制にならない）",
        )
        # 整数かつ非負であること（bool は明示除外）。
        self.assertIsInstance(
            reserved,
            int,
            msg=f"ReservedConcurrentExecutions が整数でない: {reserved!r}",
        )
        self.assertFalse(
            isinstance(reserved, bool),
            msg="ReservedConcurrentExecutions が bool である（整数値であるべき）",
        )
        self.assertGreaterEqual(
            reserved,
            0,
            msg=f"ReservedConcurrentExecutions が負値: {reserved!r}",
        )


class WafAbsenceTests(unittest.TestCase):
    """WAF リソース既定不在の検証（R8-6）.

    WAF は既定不採用（コメントアウト維持）であり、合成テンプレートに
    `AWS::WAFv2::WebACL` / `AWS::WAFv2::WebACLAssociation` が含まれないことを
    検証する（出典: design.md「WAF 既定不採用」、requirements.md R8-6、tasks.md 5.4）。
    """

    def test_no_wafv2_resources_present(self) -> None:
        """テンプレートに AWS::WAFv2:: リソースが存在しない（R8-6）."""
        # WAFv2 接頭辞のリソースを列挙し、1 つも存在しないことを確認する。
        waf_resources = _resource_types_with_prefix(
            _TEMPLATE_RESOURCES, "AWS::WAFv2::"
        )
        self.assertEqual(
            waf_resources,
            [],
            msg=(
                "WAF リソースが既定で存在する（R8-6 違反、コメントアウト維持のはず）: "
                f"{waf_resources!r}"
            ),
        )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
