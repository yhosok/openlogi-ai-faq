# src/openlogi_ai_faq/qa_app.py (クローラー連携機能追加)
import google.generativeai as genai
import json
import os
from dotenv import load_dotenv
import sys

# クローラーモジュールをインポート (同じパッケージ内なので相対インポート)
from . import crawler

# --- 設定 ---
# crawler.py のデフォルトファイル名と合わせる
FAQ_DATA_FILE = crawler.DEFAULT_OUTPUT_FILENAME
# MODEL_NAME = "gemini-1.5-flash-latest"
# MODEL_NAME = "gemini-2.0-flash"
MODEL_NAME = "gemini-2.5-pro-exp-03-25"
# --- 設定ここまで ---

# --- load_faq_data, format_faq_context 関数は変更なし ---
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

def format_faq_context(faq_data):
    """FAQデータのリストをChatSessionの初期コンテキストとして整形する。"""
    context_header = "あなたは親切なFAQアシスタントです。以下のFAQ情報を参考に、提供された情報のみに基づいてユーザーの質問に日本語で回答してください。情報がない場合は「関連する情報が見つかりませんでした。」と正直に回答してください。\n\n--- FAQ情報 ---\n"
    context_footer = "--- FAQ情報ここまで ---\n\n上記情報を記憶し、今後の質問に備えてください。"
    max_chars = 950000
    approx_char_count = len(context_header) + len(context_footer)
    faq_texts = []
    content_added = False
    limited = False
    for faq in faq_data:
        q = faq.get('question', '')
        a = faq.get('answer', '')
        url = faq.get('url', '')
        if q and a:
            faq_entry = f"Q: {q}\nA: {a}\n参照URL: {url}\n---\n"
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
        return None, False
    full_context = context_header + "".join(faq_texts) + context_footer
    return full_context, limited

# --- メイン処理 (__main__) ---
if __name__ == "__main__":
    print(f"FAQ Q&A アプリ (モデル: {MODEL_NAME}, ChatSession利用)")
    print("-" * 30)

    # --- FAQデータの準備 ---
    faq_data = None
    if not os.path.exists(FAQ_DATA_FILE):
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


    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("エラー: 環境変数 'GEMINI_API_KEY' が設定されていません。")
        sys.exit(1)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        print(f"\nGeminiモデル ({MODEL_NAME}) を初期化しました。")
    except Exception as e:
        print(f"エラー: Geminiモデル ({MODEL_NAME}) の初期化に失敗しました。\n{e}")
        sys.exit(1)

    initial_context, context_limited = format_faq_context(faq_data)
    if initial_context is None:
        print("エラー: 初期コンテキストの生成に失敗しました。FAQデータを確認してください。")
        sys.exit(1)
    if context_limited:
         print("警告: FAQデータの一部のみがコンテキストとして使用されます。")

    try:
        print("\nチャットセッションを開始し、FAQ情報をモデルに読み込ませています...")
        chat = model.start_chat(history=[])
        initial_prompt = f"{initial_context}\n\n上記の内容を理解しましたか？準備ができたら「準備完了」とだけ答えてください。"
        safety_settings=[
             { "category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
             { "category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        generation_config = genai.types.GenerationConfig(temperature=0.2)

        response = chat.send_message(
            initial_prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
            )

        print("\nFAQ情報の読み込みが完了しました。質問を入力してください。")
        print("終了するには 'quit' または 'exit' と入力してください。")
        print("-" * 30)

    except Exception as e:
        print(f"エラー: チャットセッションの開始または初期コンテキスト投入に失敗しました。\n{e}")
        if hasattr(e, 'message'): print(f"APIエラー詳細: {e.message}")
        sys.exit(1)


    while True:
        try:
            user_question = input("\n質問を入力してください: ")
            if user_question.lower() in ['quit', 'exit']:
                break
            if not user_question:
                continue

            print("\nGeminiに問い合わせています...")
            response = chat.send_message(
                user_question,
                generation_config=generation_config,
                safety_settings=safety_settings
                )

            print("\n回答:")
            print(response.text)

        except Exception as e:
            print(f"エラー: メッセージの送信または応答の受信中にエラーが発生しました。\n{e}")
            if "Resource has been exhausted" in str(e) or "rate limit" in str(e).lower():
                print("INFO: レート制限に達した可能性があります。")
            continue

    print("\nアプリを終了します。")