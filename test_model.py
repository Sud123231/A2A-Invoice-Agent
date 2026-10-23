import asyncio
import os

import httpx
from dotenv import load_dotenv


load_dotenv()


async def test_model():
    api_key = os.getenv("AI_API_KEY")
    base_url = os.getenv("AI_BASE_URL")
    model = os.getenv("AI_MODEL")

    if not api_key or not base_url or not model:
        print("ERROR: Check the AI settings in your .env file.")
        return

    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Return JSON with one key named status "
                                "whose value is the string ok."
                            ),
                        }
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                    "max_tokens": 200,
                },
            )

        print("HTTP status:", response.status_code)

        if response.is_success:
            result = response.json()
            print("Model:", result.get("model", "not provided"))

            choices = result.get("choices", [])
            if not choices:
                print("No choices returned:", result)
            else:
                message = choices[0].get("message", {})
                content = message.get("content")

                if content is not None:
                    print("Response:", content)
                    print("API connection successful.")
                else:
                    print("Unexpected message format:", message)
                    print("Finish reason:", choices[0].get("finish_reason"))
        else:
            print("API error:", response.text[:1500])

    except httpx.TimeoutException:
        print("ERROR: The API request timed out.")
    except httpx.RequestError as error:
        print("ERROR: Network request failed:", str(error))
    except (ValueError, KeyError, IndexError, TypeError) as error:
        print("ERROR: Unexpected API response:", str(error))

asyncio.run(test_model())
