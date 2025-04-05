# src/openlogi_ai_faq/crawler.py (デフォルトURL設定・関数化)
import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urlparse, urljoin, urldefrag, urlunparse
import time
import sys
import re
from collections import deque
import os # ファイルパス操作用

# --- 設定 ---
# デフォルトの出力ファイル名を指定 (qa_app.py と合わせる)
DEFAULT_OUTPUT_FILENAME = "faq_data_openlogi.json"
# デフォルトの開始URL
DEFAULT_START_URL = "https://help.openlogi.com/"
REQUEST_DELAY = 1
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
MAX_PAGES = 10000
IGNORE_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.css', '.js', '.xml', '.svg', '.ico', '.mp4', '.mp3', '.avi']
# --- 設定ここまで ---

# is_valid_url, normalize_url, extract_specific_faq_and_links, save_data 関数は変更なし
# (ただし、save_data はファイル名を引数で受け取るようにする)
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def normalize_url(base_url, link):
    try:
        abs_url = urljoin(base_url, link.strip())
        parsed_url = urlparse(abs_url)
        normalized = urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            '', '', ''
        ))
        if not is_valid_url(normalized):
             return None
        return normalized
    except Exception:
        return None

def extract_specific_faq_and_links(soup, url):
    faq_info = None
    question_text = ""
    answer_text = ""
    question_h2 = soup.find('h2', class_='faq_qstCont_ttl')
    if question_h2:
        question_text = question_h2.get_text(strip=True)
    answer_div = soup.find('div', id='faq_answer_contents')
    if answer_div:
        answer_text = answer_div.get_text(separator='\n', strip=True)
        answer_text = re.sub(r'\n\s*\n+', '\n', answer_text)
    if question_text and answer_text:
        faq_info = {
            'question': question_text,
            'answer': answer_text,
            'url': url
        }
    internal_links = set()
    base_domain = urlparse(url).netloc
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        normalized_link_url = normalize_url(url, href)
        if normalized_link_url:
            link_domain = urlparse(normalized_link_url).netloc
            if link_domain == base_domain:
                 path = urlparse(normalized_link_url).path.lower()
                 if not any(path.endswith(ext) for ext in IGNORE_EXTENSIONS):
                      internal_links.add(normalized_link_url)
    return faq_info, internal_links

def save_data(data_list, filename):
    """ページ情報のリストを指定されたファイル名でJSONファイルに保存する。"""
    if not isinstance(data_list, list):
         print(f"エラー: 保存するデータはリスト形式である必要があります。")
         return False # 保存失敗
    if not data_list:
        print("保存するデータがありません。")
        return False # 保存するデータがない場合も失敗扱いとするか、Trueとするかは要件による

    try:
        # ファイルパスを絶対パスに変換するか、実行ディレクトリ基準で考える
        # ここではカレントディレクトリからの相対パスとする
        filepath = os.path.abspath(filename)
        print(f"データを {filepath} に保存しようとしています...")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
        print(f"データを {filename} に保存しました。({len(data_list)} 件)")
        return True # 保存成功
    except IOError as e:
        print(f"エラー: ファイルへの保存に失敗しました - {filename}\n{e}")
        return False # 保存失敗
    except Exception as e:
        print(f"エラー: 不明なエラーが発生しました（ファイル保存時）\n{e}")
        return False # 保存失敗


def crawl_site_for_faq(start_url, output_filename):
    """
    指定された開始URLからサイト内を再帰的にクロールし、
    特定の形式のFAQページの質問と回答を指定されたファイル名で収集・保存する。
    """
    normalized_start_url = normalize_url(start_url, start_url)
    if not normalized_start_url:
        print(f"エラー: 無効な開始URL、または正規化に失敗しました - {start_url}")
        return False # クロール失敗

    start_domain = urlparse(normalized_start_url).netloc
    if not start_domain:
         print(f"エラー: 開始URLからドメインを取得できませんでした - {normalized_start_url}")
         return False

    print("-" * 30)
    print(f"クロールを開始します...")
    print(f"  対象ドメイン: {start_domain}")
    print(f"  開始URL: {start_url}") # ユーザーが入力した（またはデフォルトの）URLを表示
    print(f"  正規化URL: {normalized_start_url}")
    print(f"  出力ファイル: {output_filename}")
    print(f"  最大探索ページ数 (安全装置): {MAX_PAGES}")
    print(f"  FAQ形式: <h2 class='faq_qstCont_ttl'>(質問), <div id='faq_answer_contents'>(回答)")
    print("-" * 30)


    urls_to_visit = deque([normalized_start_url])
    visited_urls = set()
    all_faq_data = []
    page_count = 0
    faq_found_count = 0
    processed_unique_urls = 0

    while urls_to_visit and page_count < MAX_PAGES:
        current_normalized_url = urls_to_visit.popleft()

        if current_normalized_url in visited_urls:
            continue

        visited_urls.add(current_normalized_url)
        processed_unique_urls += 1
        page_count += 1

        if processed_unique_urls % 10 == 0:
            print(f"--- 処理済みユニークURL: {processed_unique_urls}, 発見済みFAQ: {faq_found_count}, 残りキュー: {len(urls_to_visit)} ---")

        try:
            time.sleep(REQUEST_DELAY)
            # print(f"[{processed_unique_urls}/{MAX_PAGES}*] ページ取得中: {current_normalized_url}") # 少し冗長なのでコメントアウト

            response = requests.get(current_normalized_url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                 continue

            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'html.parser')

            faq_info, internal_links = extract_specific_faq_and_links(soup, current_normalized_url)

            if faq_info:
                all_faq_data.append(faq_info)
                faq_found_count += 1
                # print(f" -> ★★★ FAQ発見 ({faq_found_count}件目): Q='{faq_info['question'][:50]}...'") # 毎回表示しない

            for normalized_link in internal_links:
                if normalized_link not in visited_urls:
                     if urlparse(normalized_link).netloc == start_domain:
                        urls_to_visit.append(normalized_link)

        except requests.exceptions.Timeout:
             print(f"エラー: タイムアウトしました - {current_normalized_url}")
        except requests.exceptions.RequestException as e:
             if e.response is not None and e.response.status_code == 404:
                 # 404 は頻繁に出るのでログレベルを下げる（表示しない）
                 # print(f"情報: 404 Not Found - {current_normalized_url}")
                 pass
             else:
                 print(f"エラー: ページの取得に失敗しました - {current_normalized_url}\n{e}")
        except Exception as e:
             print(f"エラー: ページの処理中に予期せぬエラーが発生しました - {current_normalized_url}\n{e}")

        if page_count >= MAX_PAGES:
             print("ページ数上限に達しました。")
             break

    print("-" * 30)
    if page_count >= MAX_PAGES:
        print(f"最大探索ページ数 ({MAX_PAGES}) に達したため、クロールを終了します。")
    elif not urls_to_visit:
        print("探索可能なURLがなくなったため、クロールを終了します。")
    else:
         print("クロールを終了します。")

    print(f"\nクロール完了。合計 {processed_unique_urls} のユニークURLを処理し、{faq_found_count} 件の指定形式FAQ情報を収集しました。")

    # 結果の保存
    if all_faq_data:
        save_success = save_data(all_faq_data, output_filename)
        return save_success # 保存の成否を返す
    else:
        print("指定形式のFAQデータが見つからなかったため、ファイルは保存されませんでした。")
        # FAQが見つからなくても、クロール自体は正常終了したとみなすか？
        # ここではデータがない場合も True (処理は正常完了) を返すことにする
        # 必要であれば False に変更
        return True


def run_crawl(start_url: str | None = None, output_filename: str = DEFAULT_OUTPUT_FILENAME):
    """
    クローラーを実行するメイン関数。URLが指定されなければ入力を促す。

    Args:
        start_url (str | None): 開始URL。Noneの場合はユーザーに入力を求める。
        output_filename (str): 出力ファイル名。

    Returns:
        bool: クロールと保存が正常に完了した場合はTrue、失敗した場合はFalse。
    """
    if start_url is None:
        start_url_input = input(f"探索を開始するサイトのURLを入力してください (デフォルト: {DEFAULT_START_URL}): ")
        # 入力が空ならデフォルトURLを使用
        if not start_url_input:
            start_url_to_use = DEFAULT_START_URL
            print(f"デフォルトURLを使用します: {start_url_to_use}")
        else:
            start_url_to_use = start_url_input
    else:
        start_url_to_use = start_url

    if not is_valid_url(start_url_to_use):
        print(f"エラー: 入力されたURLが無効です - {start_url_to_use}")
        return False

    # クロール本体の実行
    success = crawl_site_for_faq(start_url_to_use, output_filename)

    print("-" * 30)
    if success:
        print("クロール処理が完了しました。")
    else:
        print("クロール処理中にエラーが発生したか、データが保存されませんでした。")
    print("-" * 30)
    return success

# スクリプトとして直接実行された場合の処理
if __name__ == "__main__":
    print("FAQコンテンツ探索・保存スクリプト")
    print("-" * 30)
    # 直接実行時はデフォルトファイル名を使用
    run_crawl(start_url=None, output_filename=DEFAULT_OUTPUT_FILENAME)