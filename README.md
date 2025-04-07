# openlogi-ai-faq

## 概要

このプロジェクトは、オープンロジのヘルプサイト (`https://help.openlogi.com/`) をクロールしてFAQデータを抽出し、そのデータを使ってGoogle Gemini API と対話形式でQ&Aを行うアプリケーションです。回答には、根拠となったFAQページのURL（参照FAQリンク）が含まれることがあります。

Pythonのパッケージ管理ツールとして `uv` を使用します。

## 機能

### 1. FAQコンテンツクローラー (`src/openlogi_ai_faq/crawler.py`)

*   指定された開始URL（デフォルト: `https://help.openlogi.com/`）から、同じドメイン内のWebページを再帰的に探索します。
*   **特定のHTML構造**を持つページから、以下の情報を抽出します。
    *   **質問:** `<h2 class="faq_qstCont_ttl">` タグ内のテキスト
    *   **回答:** `<div id="faq_answer_contents">` タグ内のテキスト
*   URLの**クエリパラメータを除去**して正規化し、同じコンテンツへの重複アクセスを防ぎます。
*   訪問済みURLを管理し、無限ループを回避します（安全装置として最大探索ページ数も設定可能）。
*   抽出したQ&Aペア（質問、回答、参照元URL）をJSONファイル (`faq_data_openlogi.json`) に保存します。
*   サーバー負荷軽減のため、リクエスト間に遅延（`REQUEST_DELAY`）を設定しています。
*   単体で実行可能ですが、Q&Aアプリからも必要に応じて呼び出されます。

### 2. Gemini Q&A アプリ (`src/openlogi_ai_faq/qa_app.py`)

*   `faq_data_openlogi.json` ファイルを読み込みます。
    *   **初回実行時やファイルが存在しない場合:** ユーザーに確認後、`crawler.py` を実行してFAQデータを生成します。
    *   **ファイルが存在する場合:** ユーザーに確認後、`crawler.py` を実行してデータを更新するか、既存のデータを使用するかを選択できます。
*   読み込んだFAQデータを整形し、Google Gemini API (デフォルト: `gemini-2.5-pro-exp-03-25`、変更可能) の**ChatSession**に初期コンテキストとして投入します。
    *   `ChatSession` を利用することで、会話の履歴が維持され、FAQ情報に基づいた回答が可能になります。
*   モデルに対して、回答の根拠となったFAQのURLを「参照FAQ: [URL]」形式で出力するように指示します。
    *   **注記:** この参照FAQリンクの出力精度は、使用するGeminiモデルに依存します。**`gemini-2.5-pro` 系モデルで比較的正確なリンクが出力される傾向がありますが、他のモデル（例: `gemini-1.5-flash`）では関連性の低いリンクが表示される場合があります。**
*   ユーザーがコマンドラインで質問を入力すると、Gemini APIに問い合わせ、FAQコンテキストに基づいた回答（参照FAQリンクを含む場合あり）を表示します。
*   APIキーは `.env` ファイルから安全に読み込みます。
*   セッション終了時に、そのセッションで使用されたAPIの合計トークン数（推定値）を表示します。

## 必要なもの

*   **Python 3.8** 以上
*   **`uv`**: 高速なPythonパッケージ管理ツール ([インストール方法](https://astral.sh/uv#installation))
*   **Google Gemini API キー**: Google AI Studio ([https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)) などで取得してください。
    *   `gemini-2.5-pro` 系の実験版/プレビュー版モデルを使用する場合、アクセス権が必要な場合があります。

## セットアップ手順

1.  **リポジトリをクローン:** このリポジトリをローカル環境にクローンします。
    ```text
    git clone <repository_url>
    cd openlogi-ai-faq
    ```
    `<repository_url>` は実際のリポジトリURLに置き換えてください。

2.  **仮想環境を作成:** プロジェクトのルートディレクトリで実行します。
    ```text
    uv venv
    ```

3.  **仮想環境をアクティベート:**
    *   **macOS / Linux (bash/zsh):**
        ```text
        source .venv/bin/activate
        ```
    *   **Windows (PowerShell):**
        ```text
        .venv\Scripts\Activate.ps1
        ```
    *   **Windows (Command Prompt):**
        ```text
        .venv\Scripts\activate.bat
        ```
    (ターミナルのプロンプトの先頭に `(.venv)` のような表示が出ます)

4.  **依存関係をインストール:** `pyproject.toml` に基づいて必要なライブラリをインストールします。
    ```text
    uv pip install -e .
    ```
    (`pyproject.toml` が正しく設定されていれば、`requests`, `beautifulsoup4`, `google-generativeai`, `python-dotenv`, `lxml` などがインストールされます。)

5.  **.env ファイルを作成:** プロジェクトのルートディレクトリに `.env` という名前のファイルを作成し、以下のようにAPIキーを記述します。
    ```text
    GEMINI_API_KEY=YOUR_API_KEY_HERE
    ```
    `YOUR_API_KEY_HERE` を実際のAPIキーに置き換えてください。このファイルは `.gitignore` によりGit管理から除外されます。

## 使用方法

### 1. FAQデータのクロールと保存 (単体実行)

クローラーを個別に実行してFAQデータを収集・更新することも可能です。

```text
# デフォルトの開始URL (https://help.openlogi.com/) で実行
python -m openlogi_ai_faq.crawler

# もし別のURLから開始したい場合 (現状は引数指定に対応していません)
# (コードを修正するか、一時的にDEFAULT_START_URLを変更してください)
```

クロールが完了すると、指定された形式のFAQデータがプロジェクトルートに `faq_data_openlogi.json` として保存（または上書き）されます。このファイルは `.gitignore` で管理対象外となっています。

### 2. Q&A アプリの実行

Q&Aアプリを実行します。

```text
python -m openlogi_ai_faq.qa_app
```

*   **初回実行時など `faq_data_openlogi.json` がない場合:**
    「FAQデータファイルが見つかりません。今すぐデータを取得しますか？ (y/n):」と表示されます。`y` を入力するとクローラーが実行され、データが生成されます。
*   **`faq_data_openlogi.json` が存在する場合:**
    「既存のFAQデータファイルが見つかりました。データを更新しますか？ (y/n):」と表示されます。`y` を入力するとクローラーが実行され、データが更新されます。`n` を入力すると既存のデータが使用されます。

データの準備が完了すると、GeminiモデルにFAQ情報が読み込まれ、質問を入力するように促されます。

```text
質問を入力してください: (ここに質問を入力してEnter)
```

入力された質問に対して、読み込まれたFAQ情報に基づいてGeminiが回答を生成し、表示します。回答の最後に参照FAQリンクが含まれる場合があります。`quit` または `exit` と入力するとアプリを終了します。セッション終了時には、使用された合計トークン数（推定値）が表示されます。

## 設定

いくつかの動作はスクリプト内の定数を変更することで調整できます。

*   **`src/openlogi_ai_faq/crawler.py`:**
    *   `DEFAULT_OUTPUT_FILENAME`: 保存するJSONファイル名 (デフォルト: `"faq_data_openlogi.json"`)
    *   `DEFAULT_START_URL`: クローラー単体実行時やURL入力がない場合に使用される開始URL (デフォルト: `"https://help.openlogi.com/"`)
    *   `REQUEST_DELAY`: 各HTTPリクエスト間の待機時間（秒）(デフォルト: `1`)。**値を小さくしすぎるとサイトに負荷をかけるので注意してください。**
    *   `MAX_PAGES`: クロールする最大ページ数（安全装置）(デフォルト: `10000`)。
*   **`src/openlogi_ai_faq/qa_app.py`:**
    *   `FAQ_DATA_FILE`: 読み込むFAQデータファイル名 (デフォルトは `crawler.DEFAULT_OUTPUT_FILENAME` を参照)
    *   `MODEL_NAME`: 使用するGeminiモデル名。複数記載されており、コメントアウトで切り替え可能です (デフォルト: `"gemini-2.5-pro-exp-03-25"`)。

## 注意点

*   **Webスクレイピングのマナー:** クロール対象サイトの利用規約や `robots.txt` を確認し、`REQUEST_DELAY` を適切に設定して、サーバーに過度な負荷をかけないように注意してください。
*   **抽出ロジックの依存性:** `crawler.py` のFAQ抽出ロジックは、オープンロジヘルプサイトの特定のHTML構造に依存しています。サイト構造が変更された場合、修正が必要です。
*   **参照FAQリンクの精度:** Q&Aアプリは回答の根拠となったFAQのURLを出力しようと試みますが、この精度は使用するモデルに依存します。**`gemini-2.5-pro` 系モデル以外では、関連性の低いURLが表示される可能性があります。**
*   **ChatSessionとトークン数:** `qa_app.py` では `ChatSession` を利用してFAQコンテキストを維持します。会話が長くなるほど、APIに送信されるトークン数が増加し、応答時間やコストに影響が出る可能性があります。表示される合計トークン数は推定値です。
*   **APIコストとレート制限:** Gemini APIの利用にはコストが発生する場合があります（特に`preview`版モデル）。APIのレート制限（単位時間あたりのリクエスト数上限）に達することがあります（特に`exp`版モデル）。
*   **プレビュー/実験版モデル:** デフォルトで使用する `gemini-2.5-pro-exp-03-25` は実験版であり、無料ですがレート制限が低い場合があります。有料のプレビュー版や安定版を使用する場合は、`qa_app.py` の `MODEL_NAME` を変更してください。

## ライセンス

MIT License (プロジェクトに合わせて変更してください)