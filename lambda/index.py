# lambda/index.py
import json
import os
import re  # 正規表現モジュール (もし未使用なら削除可能)
import urllib.request # requests の代わりに urllib.request を使用
import urllib.error   # urllib のエラーハンドリング用
import socket         # タイムアウト判定用

# 環境変数からFastAPIエンドポイントのURLを取得
FASTAPI_ENDPOINT_URL = os.environ.get("FASTAPI_ENDPOINT_URL") # 元のコード 'os.environ.get("https://...")' から修正

def lambda_handler(event, context):
    try:
        # FastAPIエンドポイントURLが設定されているか確認
        if not FASTAPI_ENDPOINT_URL:
            # 環境変数名が正しいか確認してください
            raise ValueError("Environment variable 'FASTAPI_ENDPOINT_URL' is not set or empty.")

        print("Received event:", json.dumps(event))

        # Cognitoで認証されたユーザー情報を取得
        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            user_info = event['requestContext']['authorizer']['claims']
            print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")

        # リクエストボディの解析
        try:
            body = json.loads(event['body'])
            message = body['message']
        except (TypeError, KeyError, json.JSONDecodeError) as e:
             raise ValueError(f"Invalid request body: {str(e)}")

        print("Processing message:", message)

        # --- FastAPIへのリクエストペイロード作成 ---
        fastapi_payload = {
            "prompt": message,
            "max_new_tokens": 512,
            "temperature": 0.7,
            "top_p": 0.9
            }

        print(f"Calling FastAPI endpoint: {FASTAPI_ENDPOINT_URL}")
        print(f"Sending payload to FastAPI: {json.dumps(fastapi_payload)}")

        assistant_response = None # レスポンスを格納する変数を初期化

        # --- FastAPIエンドポイント呼び出し (urllib.request を使用) ---
        try:
            # ペイロードをJSON文字列に変換し、UTF-8バイト列にする
            data = json.dumps(fastapi_payload).encode('utf-8')
            # ヘッダーを設定 (Content-Type は必須)
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json' # レスポンス形式を指定
            }
            # Requestオブジェクトを作成 (メソッドをPOSTに指定)
            req = urllib.request.Request(FASTAPI_ENDPOINT_URL, data=data, headers=headers, method='POST')

            # リクエストを実行し、レスポンスを取得 (タイムアウトを設定)
            # 'with' ステートメントでレスポンスオブジェクトを確実にクローズする
            with urllib.request.urlopen(req, timeout=60) as response:
                status_code = response.status
                print(f"FastAPI response status: {status_code}")

                # レスポンスボディを読み取り、UTF-8でデコード
                response_body_bytes = response.read()
                response_body_str = response_body_bytes.decode('utf-8')

                # レスポンスをJSONとしてパース
                try:
                    fastapi_response_data = json.loads(response_body_str)
                    print(f"Received response from FastAPI: {json.dumps(fastapi_response_data)}")
                except json.JSONDecodeError:
                    # レスポンスがJSON形式でない場合のエラー
                    print(f"Error decoding JSON response from FastAPI. Response text: {response_body_str}")
                    raise Exception("Received an invalid (non-JSON) response from the inference service.")

                # FastAPI側の処理結果を確認 (元のコードのロジックを維持)
                if not fastapi_response_data.get('success', False):
                    error_message = fastapi_response_data.get('error', 'Unknown error from FastAPI service')
                    # FastAPI側でエラーが発生した場合
                    raise Exception(f"FastAPI service returned an error: {error_message}")

                # 必要なレスポンスデータを取得
                assistant_response = fastapi_response_data.get('response')
                # conversationHistory は元のコードでは取得後未使用だったためコメントアウト
                # updated_conversation_history = fastapi_response_data.get('conversationHistory')

                # レスポンスに必要なデータが含まれているか確認
                if assistant_response is None:
                    raise Exception("Invalid response format from FastAPI service (missing 'response').")

        except urllib.error.HTTPError as e:
            # HTTPエラー (例: 4xx クライアントエラー, 5xx サーバーエラー)
            print(f"HTTP Error calling FastAPI endpoint: {e.code} {e.reason}")
            error_message = f"FastAPI service returned HTTP error {e.code}."
            try:
                # エラーレスポンスのボディに詳細が含まれている場合がある
                error_body = e.read().decode('utf-8')
                print(f"Error response body: {error_body}")
                # ボディがJSON形式であれば、詳細メッセージを抽出しようと試みる
                try:
                    error_data = json.loads(error_body)
                    # FastAPIのHTTPExceptionは 'detail' キーを持つことが多い
                    error_detail = error_data.get('detail', error_body)
                    error_message = f"FastAPI service returned HTTP error {e.code}: {error_detail}"
                except json.JSONDecodeError:
                    # JSONでない場合は、そのままメッセージに追加
                     error_message += f" Response: {error_body}"
            except Exception as inner_e:
                # エラーレスポンスボディの読み取りやパースに失敗した場合
                print(f"Could not read or parse error response body: {inner_e}")
            raise Exception(error_message) # 元のエラーメッセージとともに例外を発生

        except urllib.error.URLError as e:
            # URL関連のエラー (ネットワーク接続、名前解決、タイムアウトなど)
            # タイムアウトかどうかを判定
            if isinstance(e.reason, socket.timeout):
                print(f"Error: Request to FastAPI endpoint timed out after 60 seconds.")
                raise Exception("The inference service did not respond in time.")
            else:
                # その他のURLエラー (例: 接続拒否、ホストが見つからない)
                print(f"URL Error calling FastAPI endpoint: {e.reason}")
                raise Exception(f"Failed to connect to the inference service: {e.reason}")
        # except json.JSONDecodeError は response の try-except 内で処理されるため、ここでは不要

        # assistant_response が FastAPI 呼び出し後に None のままならエラー
        if assistant_response is None:
             raise Exception("Failed to get assistant response from FastAPI for an unknown reason.")

        # --- 成功レスポンスの返却 ---
        return {
            "statusCode": 200,
             "headers": {
                # CORSヘッダーなど、必要なヘッダーを設定
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*", # 必要に応じて制限してください
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST" # Lambdaプロキシ統合で必要
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response,
                # "conversationHistory": updated_conversation_history # 必要なら含める
            })
        }

    # --- Lambdaハンドラ全体のエラーハンドリング ---
    except ValueError as ve: # 設定やリクエストボディのバリデーションエラー
        print(f"Configuration or Request Validation Error: {str(ve)}")
        return {
            "statusCode": 400, # Bad Request
             "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": f"Bad Request: {str(ve)}"
            })
        }
    except Exception as error: # その他の予期せぬエラー
        print(f"Error in Lambda handler: {str(error)}")
        import traceback
        traceback.print_exc() # スタックトレースをログに出力
        # --- Lambdaのエラーレスポンス ---
        return {
            "statusCode": 500, # Internal Server Error
             "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                # 本番環境では詳細なエラーメッセージをクライアントに返さない方が良い場合もある
                "error": f"Lambda processing error: {str(error)}"
            })
        }