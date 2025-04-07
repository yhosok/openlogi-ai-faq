# src/openlogi_ai_faq/qa_app.py (トークン数表示修正・コメント調整版)
import google.generativeai as genai
import json
import os
from dotenv import load_dotenv
import sys

# クローラーモジュールをインポート (同じパッケージ内の crawler.py)
from . import crawler

# --- 設定 ---
FAQ_DATA_FILE = crawler.DEFAULT_OUTPUT_FILENAME # クローラーのデフォルト出力ファイル名を参照

# 使用するGeminiモデルを選択 (コメントアウトで切り替え)
# 注記: モデルによって性能、料金、利用制限が異なります。
#       参照FAQリンクの精度は 2.5 Pro 系で高い傾向があります。
# MODEL_NAME = "gemini-1.5-flash-latest"     # 高速・低コスト・1Mトークン
# MODEL_NAME = "gemini-1.5-pro-latest"      # 標準・高性能・1Mトークン
MODEL_NAME = "gemini-2.5-pro-exp-03-25"      # 実験版・無料・レート制限低 (デフォルト)
# MODEL_NAME = "gemini-2.5-pro-preview-03-25" # プレビュー版・有料・高性能

# --- 設定ここまで ---

# --- load_faq_data 関数 ---
def load_faq_data(filename):
    """
    指定されたJSONファイルからFAQデータ（質問と回答のペアのリスト）を読み込む。

    Args:
        filename (str): 読み込むJSONファイル名。

    Returns:
        list or None: 読み込んだFAQデータのリスト。エラー時はNone。
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # データ形式がリストであるか基本的なチェック
        if not isinstance(data, list):
             print(f"エラー: {filename} のデータ形式がリストではありません。")
             return None
        print(f"{filename} から {len(data)} 件のFAQデータを読み込みました。")
        return data
    except FileNotFoundError:
        # ファイルが見つからない場合はNoneを返し、呼び出し元で処理する
        return None
    except json.JSONDecodeError:
        print(f"エラー: FAQデータファイル ({filename}) の形式が正しくありません。")
        return None
    except Exception as e:
        print(f"エラー: FAQデータファイルの読み込み中にエラーが発生しました。\n{e}")
        return None

# --- format_faq_context (参照URL出力指示付き) ---
def format_faq_context(faq_data):
    """
    FAQデータのリストをChatSessionの初期コンテキストとして整形する。
    モデルに参照URLの出力をより厳密に指示するプロンプトを含む。
    トークン制限（文字数ベース）を超えた場合はデータを切り詰める。

    Args:
        faq_data (list): FAQデータのリスト。各要素は辞書形式で'question', 'answer', 'url'キーを持つ想定。

    Returns:
        tuple[str | None, bool]: 整形されたコンテキスト文字列と、データが切り詰められたかのフラグ。
                                 コンテキスト生成失敗時は (None, False)。

    注記: 参照FAQリンクの出力精度はモデルによって異なります。
         Gemini 2.5 Pro 系モデルで比較的良好な結果が得られる傾向があります。
    """
    # モデルへの指示 (ロール、タスク、出力形式、制約などを定義)
    context_header = """あなたはユーザーの質問に対して、提供された以下のFAQ情報のみを根拠として回答するFAQアシスタントです。

回答生成のルール:
1.  ユーザーの質問に最も合致するFAQ情報を以下のリストから探し、その**回答内容を要約または引用して**回答を作成してください。
2.  回答の生成に**直接利用したFAQ情報が特定できる場合のみ**、そのFAQの参照URLを回答の最後に「参照FAQ: [URL]」という形式で**1つだけ**記載してください。
3.  複数のFAQが関連しそうな場合でも、**最も回答の主要な根拠となったFAQのURLのみ**を記載してください。判断が難しい場合や、確信が持てない場合はURLを記載しないでください。
4.  FAQ情報の中に該当する答えが見つからない場合は、「関連する情報が見つかりませんでした。」とだけ回答し、URLは記載しないでください。
5.  絶対に推測で回答したり、FAQ情報にない知識で補完したりしないでください。参照URLも、リストにあるもの以外を生成しないでください。

--- FAQ情報 ---
"""
    context_footer = "--- FAQ情報ここまで ---\n\n上記ルールを理解し、記憶しました。ユーザーからの質問を待っています。"

    # トークン制限を文字数で簡易的に計算 (実際のトークン数とは異なる)
    # モデルごとの上限を考慮し、余裕を持たせる
    max_chars = 950000 # (例: 1Mトークンモデル向け) 必要に応じて調整
    approx_char_count = len(context_header) + len(context_footer)

    faq_texts = []      # コンテキストに含めるFAQテキストを格納するリスト
    content_added = False # 有効なFAQが1つでも追加されたか
    limited = False     # コンテキスト長制限によりデータが切り詰められたか

    # FAQデータをループしてテキスト形式に変換し、リストに追加
    for faq in faq_data:
        q = faq.get('question', '')
        a = faq.get('answer', '')
        url = faq.get('url', '')

        # 質問、回答、URLが揃っているデータのみを使用
        if q and a and url:
            faq_entry = f"質問: {q}\n回答: {a}\n参照URL: {url}\n---\n"
            entry_len = len(faq_entry)
            # 文字数制限チェック
            if approx_char_count + entry_len < max_chars:
                faq_texts.append(faq_entry)
                approx_char_count += entry_len
                content_added = True
            else:
                # 制限に達したらループを中断し、フラグを立てる
                print(f"[注意] FAQデータが大きいため、{len(faq_texts)}件でコンテキストへの追加を打ち切りました。")
                limited = True
                break

    # 有効なFAQが一つもなかった場合
    if not content_added and faq_data:
        print("警告: コンテキストに追加できる有効なFAQがありませんでした。")
        return None, False # コンテキスト生成失敗

    # ヘッダー、FAQテキスト、フッターを結合して最終的なコンテキスト文字列を作成
    full_context = context_header + "".join(faq_texts) + context_footer
    return full_context, limited

# --- メイン処理 (__main__) ---
if __name__ == "__main__":
    print(f"FAQ Q&A アプリ (モデル: {MODEL_NAME}, ChatSession利用)")
    print("-" * 30)

    # --- FAQデータの準備 ---
    faq_data = None
    # データファイルが存在するかチェック
    if not os.path.exists(FAQ_DATA_FILE):
        print(f"FAQデータファイル ({FAQ_DATA_FILE}) が見つかりません。")
        # ユーザーにデータ取得の意向を確認
        user_input = input("今すぐデータを取得しますか？ (y/n): ").lower()
        if user_input == 'y':
            print("\nクローラーを起動します...")
            # crawler モジュールの run_crawl 関数を呼び出し
            crawl_success = crawler.run_crawl(start_url=None, output_filename=FAQ_DATA_FILE)
            if not crawl_success:
                print("FAQデータの取得に失敗しました。アプリケーションを終了します。")
                sys.exit(1)
            # クロール成功後、データを読み込む
            faq_data = load_faq_data(FAQ_DATA_FILE)
        else:
            # 取得しない場合は終了
            print("データがないため、アプリケーションを終了します。")
            sys.exit(1)
    else:
        # ファイルが存在する場合
        print(f"既存のFAQデータファイル ({FAQ_DATA_FILE}) が見つかりました。")
        # ユーザーにデータ更新の意向を確認
        user_input = input("データを更新しますか？ (y/n): ").lower()
        if user_input == 'y':
            print("\nクローラーを起動してデータを更新します...")
            # クローラーを実行してデータを上書き
            crawl_success = crawler.run_crawl(start_url=None, output_filename=FAQ_DATA_FILE)
            if not crawl_success:
                print("FAQデータの更新に失敗しました。既存のデータで続行します。")
                # 更新失敗時は既存データを読み込む
                faq_data = load_faq_data(FAQ_DATA_FILE)
            else:
                 # 更新成功後、新しいデータを読み込む
                 faq_data = load_faq_data(FAQ_DATA_FILE)
        else:
            # 更新しない場合、既存のデータを読み込む
            print("既存のデータを使用します。")
            faq_data = load_faq_data(FAQ_DATA_FILE)

    # データが最終的に読み込めたか確認
    if faq_data is None:
        print(f"エラー: FAQデータの読み込みに失敗しました。({FAQ_DATA_FILE} を確認してください)")
        sys.exit(1)
    # --- FAQデータの準備 ここまで ---


    # .envファイルからAPIキーを読み込み
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("エラー: 環境変数 'GEMINI_API_KEY' が設定されていません。")
        sys.exit(1)

    # Geminiクライアントの設定
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME) # ここで選択されたモデルが使われる
        print(f"\nGeminiモデル ({MODEL_NAME}) を初期化しました。")
        # 選択されているモデルに応じた注意喚起
        if "preview" in MODEL_NAME or "exp" in MODEL_NAME:
             print(f"INFO: モデル {MODEL_NAME} はプレビュー版または実験版です。")
             if "preview" in MODEL_NAME:
                 print("     有料であり、アクセスには権限が必要な場合があります。")
             if "exp" in MODEL_NAME:
                 print("     無料ですが、レート制限が低い場合があります。")
    except Exception as e:
        print(f"エラー: Geminiモデル ({MODEL_NAME}) の初期化に失敗しました。\n{e}")
        # モデル名や権限に関するエラーメッセージの可能性
        if "Resource not found" in str(e) or "Permission denied" in str(e) or "model" in str(e).lower() and "not found" in str(e).lower():
             print(f"指定されたモデル名 '{MODEL_NAME}' が見つからないか、アクセス権がない可能性があります。")
             print("モデル名を確認するか、Google CloudプロジェクトでAPIやモデルへのアクセスが有効になっているか確認してください。")
        sys.exit(1)

    # FAQデータを初期コンテキストとして整形
    initial_context, context_limited = format_faq_context(faq_data)
    if initial_context is None:
        print("エラー: 初期コンテキストの生成に失敗しました。FAQデータを確認してください。")
        sys.exit(1)
    if context_limited:
         print("警告: FAQデータの一部のみがコンテキストとして使用されます。")

    # --- トークン数カウンターを初期化 ---
    total_prompt_tokens_sent_in_session = 0 # セッション中にAPIに送信された全プロンプトトークン(重複含む)
    total_candidates_tokens_generated = 0 # セッション中に生成された全応答トークン
    initial_prompt_tokens = 0             # 初期コンテキスト投入時のプロンプトトークン数
    initial_response_tokens = 0           # 初期コンテキスト投入時の応答トークン数
    # ----------------------------------

    # チャットセッションの開始と初期コンテキストの投入
    try:
        print("\nチャットセッションを開始し、FAQ情報をモデルに読み込ませています...")
        # ChatSessionを開始。history=[] で空の状態から始める。
        # SDKが内部で会話履歴（プロンプトと応答）を管理する。
        chat = model.start_chat(history=[])

        # 最初のプロンプトには、整形したFAQコンテキスト全体と、モデルへの確認メッセージを含める
        initial_prompt = f"{initial_context}\n\n上記ルールを理解しましたか？準備ができたら「準備完了」とだけ答えてください。"

        # APIの安全設定 (不適切なコンテンツのブロック閾値)
        safety_settings=[
             { "category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        # 回答の生成に関する設定 (temperatureを低くして、より決定的な回答を促す)
        generation_config = genai.types.GenerationConfig(temperature=0.2)

        # --- 初期コンテキスト投入とトークン数記録 ---
        # 最初のメッセージを送信し、モデルにFAQ情報を「記憶」させる
        response = chat.send_message(
            initial_prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
            )

        # 応答メタデータからトークン数を取得して記録
        if hasattr(response, 'usage_metadata'):
            initial_prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
            initial_response_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
            # 初回のトークン数を合計に記録
            total_prompt_tokens_sent_in_session += initial_prompt_tokens
            total_candidates_tokens_generated += initial_response_tokens
            print(f"(初期コンテキスト投入: プロンプト {initial_prompt_tokens} トークン, 応答 {initial_response_tokens} トークン)")
        else:
            print("警告: 初期コンテキスト投入時のトークン数を取得できませんでした。")
        # -----------------------------------------

        print("\nFAQ情報の読み込みが完了しました。質問を入力してください。")
        print("終了するには 'quit' または 'exit' と入力してください。")
        print("-" * 30)

    # チャットセッション開始時のエラーハンドリング
    except Exception as e:
        print(f"エラー: チャットセッションの開始または初期コンテキスト投入に失敗しました。\n{e}")
        if hasattr(e, 'message'): print(f"APIエラー詳細: {e.message}")
        sys.exit(1)


    # ユーザーからの質問を受け付けるメインループ
    while True:
        try:
            # ユーザーからの入力を受け付け
            user_question = input("\n質問を入力してください: ")
            # 終了コマンドのチェック
            if user_question.lower() in ['quit', 'exit']:
                break
            # 空の入力は無視
            if not user_question:
                continue

            print("\nGeminiに問い合わせています...")
            # --- 質問応答とトークン数記録 ---
            # ChatSessionにユーザーの質問を送信。SDKが自動的に履歴を付加する。
            response = chat.send_message(
                user_question,
                generation_config=generation_config, # 同じ設定を使用
                safety_settings=safety_settings     # 同じ設定を使用
                )

            # このAPI呼び出しで消費されたトークン数を取得して加算
            if hasattr(response, 'usage_metadata'):
                 current_prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
                 current_candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
                 # 各API呼び出しで送信されたプロンプトと生成された応答のトークン数を累積
                 total_prompt_tokens_sent_in_session += current_prompt_tokens
                 total_candidates_tokens_generated += current_candidates_tokens
                 print(f"(今回API呼出: プロンプト {current_prompt_tokens}, 応答 {current_candidates_tokens})") # 今回の呼び出し分
            else:
                 print("警告: 今回のAPI呼び出しのトークン数を取得できませんでした。")
            # -------------------------------

            # 回答をコンソールに表示
            print("\n回答:")
            print(response.text) # 回答に参照URLが含まれることを期待

        # ループ中のエラーハンドリング
        except Exception as e:
            print(f"エラー: メッセージの送信または応答の受信中にエラーが発生しました。\n{e}")
            # レート制限エラーの場合のメッセージ
            if "Resource has been exhausted" in str(e) or "rate limit" in str(e).lower():
                print("INFO: レート制限に達した可能性があります。")
            # エラーが発生してもループは継続
            continue

    # --- アプリ終了時に合計トークン数を表示 (説明を調整) ---
    print("\n" + "="*30)
    print("セッションが終了しました。")
    print("API利用状況 (トークン数 - 参考値):")
    print(f"  初期コンテキスト プロンプト: {initial_prompt_tokens}")
    print(f"  初期コンテキスト 応答:     {initial_response_tokens}")
    print(f"  Q&Aで生成された応答の合計: {total_candidates_tokens_generated - initial_response_tokens}") # 初期応答分を除く
    print(f"  ---")
    print(f"  APIに送信された総プロンプトトークン数 (履歴重複含む): {total_prompt_tokens_sent_in_session}")
    print(f"  APIが生成した総応答トークン数:                       {total_candidates_tokens_generated}")
    print("="*30)
    print("\n重要: 上記はAPI呼び出しで報告されたトークン数の合計です。")
    print("      ChatSessionでは会話履歴が毎回送信されるため、「送信された総プロンプトトークン数」には過去の履歴が重複してカウントされています。")
    print("      課金対象となる正確な「入力トークン数」「出力トークン数」とは異なります。")
    print("      正確な料金はGoogle Cloudの請求情報をご確認ください。")
    print("\nアプリを終了します。")
    # -----------------------------------------