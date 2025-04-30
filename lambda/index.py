# lambda/index.py
import json
import os
import re  # 正規表現モジュールをインポート
import requests


# 環境変数からFastAPIエンドポイントのURLを取得
FASTAPI_ENDPOINT_URL = os.environ.get("https://a89e-34-125-177-5.ngrok-free.app")

def lambda_handler(event, context):
    try:
        # FastAPIエンドポイントURLが設定されているか確認
        if not FASTAPI_ENDPOINT_URL:
          raise ValueError("Environment variable FASTAPI_ENDPOINT_URL is not set.")
        
        print("Received event:", json.dumps(event))
        
        # Cognitoで認証されたユーザー情報を取得
        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            user_info = event['requestContext']['authorizer']['claims']
            print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")
        
        # リクエストボディの解析
        body = json.loads(event['body'])
        message = body['message']
        
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
        
        # --- FastAPIエンドポイント呼び出し ---
        try:
            response = requests.post(
                FASTAPI_ENDPOINT_URL,
                json=fastapi_payload,
                headers={'Content-Type': 'application/json'},
                timeout=60 # Hugging Faceモデルの推論は時間がかかる可能性があるので長めに設定
            )
            response.raise_for_status()

            fastapi_response_data = response.json()
            print(f"Received response from FastAPI: {json.dumps(fastapi_response_data)}")

            if not fastapi_response_data.get('success', False):
                 error_message = fastapi_response_data.get('error', 'Unknown error from FastAPI service')
                 raise Exception(f"FastAPI service returned an error: {error_message}")

            assistant_response = fastapi_response_data.get('response')
            updated_conversation_history = fastapi_response_data.get('conversationHistory')

            if assistant_response is None or updated_conversation_history is None:
                raise Exception("Invalid response format from FastAPI service.")

        except requests.exceptions.Timeout:
            print(f"Error: Request to FastAPI endpoint timed out.")
            raise Exception("The inference service did not respond in time.")
        except requests.exceptions.RequestException as e:
            print(f"Error calling FastAPI endpoint: {e}")
            raise Exception(f"Failed to connect to the inference service: {str(e)}")
        except json.JSONDecodeError:
            print(f"Error decoding JSON response from FastAPI. Response text: {response.text}")
            raise Exception("Received an invalid (non-JSON) response from the inference service.")
        
        # レスポンスを解析
        response_body = json.loads(response.read())
        print("Fast API response:", json.dumps(response_body, default=str))
        
        # アシスタントの応答を取得
        assistant_response = response_body['generated_text']
        
        # 成功レスポンスの返却
        return {
            "statusCode": 200,
             "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response,
            })
        }
        
    except Exception as error:
        print(f"Error in Lambda handler: {str(error)}")
        import traceback
        traceback.print_exc()
        # --- Lambdaのエラーレスポンス ---
        return {
            "statusCode": 500,
             "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": f"Lambda processing error: {str(error)}"
            })
        }
