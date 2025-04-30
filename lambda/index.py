# lambda/index.py
import json
import urllib.request

# --- 🔧 ここに後で自分の ngrok 公開URLを入れる ---
API_URL = "https://77c4-34-143-213-28.ngrok-free.app/generate"


def lambda_handler(event, context):
    try:
        # クライアントからのメッセージを取得
        body = json.loads(event["body"])
        message = body["message"]

        # FastAPI に送る推論リクエストの構築
        request_data = {
            "prompt": message,
            "max_new_tokens": 512,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9
        }

        data = json.dumps(request_data).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=data,
            headers={"Content-Type": "application/json"}
        )

        # API 呼び出し
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read())

        # 応答テキストを返却
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": True,
                "response": result["generated_text"]
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": str(e)
            })
        }