# src/openlogi_ai_faq/qa_app.py (クローラー連携機能追加)
import google.generativeai as genai
import json
import os
from dotenv import load_dotenv
import sys

# クローラーモジュールをインポート
from . import crawler

# --- 設定 ---
# crawler.py のデフォルトファイル名と合わせる
FAQ_DATA_FILE = crawler.DEFAULT_OUTPUT_FILENAME
# MODEL_NAME = "gemini-1.5-flash-latest"
MODEL_NAME = "gemini-2.0-flash"
# MODEL_NAME = "gemini-2.5-pro-exp-03-25"
# --- 設定ここまで ---

# --- load_faq_data 関数 ---
def load_faq_data(filename):
    """JSONファイルからFAQデータを読み込む"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
             print(f"エラー: {filename} のデータ形式がリストではありません。")
             return None
        print(f"{filename} から {len(data)} 件のFAQデータを読み込みました。")
        return data
    except FileNotFoundError:
        # ファイルがない場合は呼び出し元でハンドリングするため、ここではNoneを返す
        return None
    except json.JSONDecodeError:
        print(f"エラー: FAQデータファイル ({filename}) の形式が正しくありません。")
        return None
    except Exception as e:
        print(f"エラー: FAQデータファイルの読み込み中にエラーが発生しました。\n{e}")
        return None

# --- format_faq_context (シンプルな指示) ---
def format_faq_context(faq_data):
    """
    FAQデータのリストをChatSessionの初期コンテキストとして整形する。
    シンプルな指示に戻す。
    トークン制限を考慮して内容を切り詰める。
    """
    # モデルへの指示をシンプルに戻す
    context_header = """あなたは親切なFAQアシスタントです。以下のFAQ情報を参考に、提供された情報のみに基づいてユーザーの質問に日本語で回答してください。FAQ情報の中に該当する答えが見つからない場合は、「関連する情報が見つかりませんでした。」と正直に回答してください。推測やFAQ情報以外の知識で回答を補完しないでください。

--- FAQ情報 ---
"""
    context_footer = "--- FAQ情報ここまで ---\n\n上記情報を記憶し、ユーザーからの質問に備えてください。"

    # Gemini 1.5 Flash のトークン制限 (1M) を考慮
    max_chars = 950000 # 念のためマージンを取る
    approx_char_count = len(context_header) + len(context_footer)

    faq_texts = []
    content_added = False
    limited = False

    for faq in faq_data:
        q = faq.get('question', '')
        a = faq.get('answer', '')
        # url = faq.get('url', '') # URLはもう使用しない

        # URLを除外
        if q and a:
            faq_entry = f"質問: {q}\n回答: {a}\n---\n" # URL部分を削除
            entry_len = len(faq_entry)
            if approx_char_count + entry_len < max_chars:
                faq_texts.append(faq_entry)
                approx_char_count += entry_len
                content_added = True
            else:
                print(f"[注意] FAQデータが大きいため、{len(faq_texts)}件でコンテキストへの追加を打ち切りました。")
                limited = True
                break

    if not content_added and faq_data:
        print("警告: コンテキストに追加できる有効なFAQがありませんでした。")
        return None, False # コンテンツがない場合はNoneを返す

    full_context = context_header + "".join(faq_texts) + context_footer
    return full_context, limited

# --- メイン処理 (__main__) ---
if __name__ == "__main__":
    print(f"FAQ Q&A アプリ (モデル: {MODEL_NAME}, ChatSession利用)")
    print("-" * 30)

    # --- FAQデータの準備 ---
    faq_data = None
    # データファイルの存在チェック
    if not os.path.exists(FAQ_DATA_FILE):
        # ... (ファイルがない場合の処理) ...
        print(f"FAQデータファイル ({FAQ_DATA_FILE}) が見つかりません。")
        user_input = input("今すぐデータを取得しますか？ (y/n): ").lower()
        if user_input == 'y':
            print("\nクローラーを起動します...")
            # クローラーを実行 (デフォルトURL, デフォルトファイル名で)
            crawl_success = crawler.run_crawl(start_url=None, output_filename=FAQ_DATA_FILE)
            if not crawl_success:
                print("FAQデータの取得に失敗しました。アプリケーションを終了します。")
                sys.exit(1)
            # クロール成功後、再度読み込みを試みる
            faq_data = load_faq_data(FAQ_DATA_FILE)
        else:
            print("データがないため、アプリケーションを終了します。")
            sys.exit(1)
    else:
        # ... (ファイルがある場合の処理) ...
        print(f"既存のFAQデータファイル ({FAQ_DATA_FILE}) が見つかりました。")
        user_input = input("データを更新しますか？ (y/n): ").lower()
        if user_input == 'y':
            print("\nクローラーを起動してデータを更新します...")
            # クローラーを実行してデータを上書き
            crawl_success = crawler.run_crawl(start_url=None, output_filename=FAQ_DATA_FILE)
            if not crawl_success:
                print("FAQデータの更新に失敗しました。既存のデータで続行します。")
                # 既存データを読み込む
                faq_data = load_faq_data(FAQ_DATA_FILE)
            else:
                 # 更新成功後、新しいデータを読み込む
                 faq_data = load_faq_data(FAQ_DATA_FILE)
        else:
            # 更新しない場合、既存のデータを読み込む
            print("既存のデータを使用します。")
            faq_data = load_faq_data(FAQ_DATA_FILE)

    # 最終的にデータが読み込めているか確認
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
        model = genai.GenerativeModel(MODEL_NAME)
        print(f"\nGeminiモデル ({MODEL_NAME}) を初期化しました。")
    except Exception as e:
        print(f"エラー: Geminiモデル ({MODEL_NAME}) の初期化に失敗しました。\n{e}")
        sys.exit(1)

    # FAQデータを初期コンテキストとして整形
    initial_context, context_limited = format_faq_context(faq_data)
    if initial_context is None:
        print("エラー: 初期コンテキストの生成に失敗しました。FAQデータを確認してください。")
        sys.exit(1)
    if context_limited:
         print("警告: FAQデータの一部のみがコンテキストとして使用されます。")

    # --- トークン数カウンターを初期化 ---
    total_tokens_used = 0
    initial_prompt_tokens = 0
    initial_response_tokens = 0
    qa_prompt_tokens = 0
    qa_response_tokens = 0
    # ----------------------------------

    # チャットセッションの開始と初期コンテキストの投入
    try:
        print("\nチャットセッションを開始し、FAQ情報をモデルに読み込ませています...")
        # ChatSessionを開始。履歴はSDKが内部で管理する。
        chat = model.start_chat(history=[])
        # 最初のメッセージとしてコンテキストを投入する指示
        initial_prompt = f"{initial_context}\n\n上記の内容を理解しましたか？準備ができたら「準備完了」とだけ答えてください。"

        # 安全設定
        safety_settings=[
             { "category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        # 低温設定で事実に即した回答を促す
        generation_config = genai.types.GenerationConfig(temperature=0.2)

        # --- 初期コンテキスト投入とトークン数記録 ---
        # コンテキスト投入 (最初のメッセージ送信)
        response = chat.send_message(
            initial_prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
            )

        # print(f"モデルからの初期応答: {response.text[:100]}...") # デバッグ用

        # 初期コンテキスト投入時のトークン数を記録
        if hasattr(response, 'usage_metadata'):
            initial_prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
            initial_response_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
            total_tokens_used += getattr(response.usage_metadata, 'total_token_count', 0)
            print(f"(初期コンテキスト投入: プロンプト {initial_prompt_tokens} トークン, 応答 {initial_response_tokens} トークン)")
        else:
            print("警告: 初期コンテキスト投入時のトークン数を取得できませんでした。")
        # -----------------------------------------

        print("\nFAQ情報の読み込みが完了しました。質問を入力してください。")
        print("終了するには 'quit' または 'exit' と入力してください。")
        print("-" * 30)

    except Exception as e:
        print(f"エラー: チャットセッションの開始または初期コンテキスト投入に失敗しました。\n{e}")
        if hasattr(e, 'message'): print(f"APIエラー詳細: {e.message}")
        sys.exit(1)


    # ユーザーからの質問を受け付けるループ
    while True:
        try:
            user_question = input("\n質問を入力してください: ")
            if user_question.lower() in ['quit', 'exit']:
                break
            if not user_question:
                continue

            print("\nGeminiに問い合わせています...")
            # --- 質問応答とトークン数記録 ---
            # ユーザーの質問を送信 (ChatSessionが履歴を管理し、文脈を維持)
            response = chat.send_message(
                user_question,
                generation_config=generation_config, # 同じ設定を使用
                safety_settings=safety_settings     # 同じ設定を使用
                )

            # この回のトークン数を加算
            current_total_tokens = 0
            current_prompt_tokens = 0
            current_candidates_tokens = 0
            if hasattr(response, 'usage_metadata'):
                 current_prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
                 current_candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
                 current_total_tokens = getattr(response.usage_metadata, 'total_token_count', 0)
                 total_tokens_used += current_total_tokens # セッション全体の合計に加算
                 qa_prompt_tokens += current_prompt_tokens # Q&A部分のプロンプトトークン累計
                 qa_response_tokens += current_candidates_tokens # Q&A部分の応答トークン累計
                 # print(f"(今回: プロンプト {current_prompt_tokens}, 応答 {current_candidates_tokens}, 合計 {current_total_tokens})") # デバッグ用
            else:
                 print("警告: 今回のAPI呼び出しのトークン数を取得できませんでした。")
            # -------------------------------

            # 回答を表示
            print("\n回答:")
            print(response.text)

        except Exception as e:
            print(f"エラー: メッセージの送信または応答の受信中にエラーが発生しました。\n{e}")
            # レート制限などのエラーメッセージ
            if "Resource has been exhausted" in str(e) or "rate limit" in str(e).lower():
                print("INFO: レート制限に達した可能性があります。")
            continue

    # --- アプリ終了時に合計トークン数を表示 ---
    print("\n" + "="*30)
    print("セッションが終了しました。")
    print("利用状況 (トークン数):")
    print(f"  初期コンテキスト投入:")
    print(f"    - プロンプト: {initial_prompt_tokens}")
    print(f"    - 応答:       {initial_response_tokens}")
    print(f"  Q&A部分:")
    print(f"    - プロンプト累計: {qa_prompt_tokens}")
    print(f"    - 応答累計:   {qa_response_tokens}")
    print(f"  --------------------")
    print(f"  セッション合計: {total_tokens_used} トークン")
    print("="*30)
    print("\n注意: これはAPIから報告されたトークン数であり、実際の請求額とは異なる場合があります。")
    print("正確な料金はGoogle Cloudの請求情報をご確認ください。")
    print("\nアプリを終了します。")
    # -----------------------------------------