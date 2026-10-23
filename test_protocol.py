
import httpx

BASE_URL = "http://127.0.0.1:8000/a2a"
ORIGIN = "http://127.0.0.1:8000"

VALID_HEADERS = {
    "Authorization": "Bearer local-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

TEST_BODY = {
    "message": {
        "messageId": "protocol-test-message",
        "role": "ROLE_USER",
        "parts": [],
    }
}

def check(name, response, expected_status):
    passed = response.status_code == expected_status
    print(
        f"{'PASS' if passed else 'FAIL'}: {name} "
        f"(expected {expected_status}, got {response.status_code})"
    )
    if not passed:
        print(response.text)


with httpx.Client(timeout=15) as client:
    missing_auth = client.post(
        f"{BASE_URL}/message:send",
        headers={
            "A2A-Version": "1.0",
            "Content-Type": "application/a2a+json",
        },
        json=TEST_BODY,
    )
    check("Missing bearer token", missing_auth, 401)

    wrong_version_headers = {
        **VALID_HEADERS,
        "A2A-Version": "9.9",
    }
    wrong_version = client.post(
        f"{BASE_URL}/message:send",
        headers=wrong_version_headers,
        json=TEST_BODY,
    )
    check("Wrong A2A-Version", wrong_version, 400)

    wrong_content_type_headers = {
        **VALID_HEADERS,
        "Content-Type": "application/json",
    }
    wrong_content_type = client.post(
        f"{BASE_URL}/message:send",
        headers=wrong_content_type_headers,
        json=TEST_BODY,
    )
    check("Wrong POST Content-Type", wrong_content_type, 415)

    card_response = client.get(
        f"{ORIGIN}/.well-known/agent-card.json"
    )
    check("Public Agent Card", card_response, 200)

    if card_response.status_code == 200:
        card = card_response.json()

        interface = next(
            (
                item for item in card.get("supportedInterfaces", [])
                if item.get("protocolBinding") == "HTTP+JSON"
            ),
            None,
        )

        check(
            "Agent Card has a supported interface",
            httpx.Response(
                200 if interface else 500,
                request=card_response.request,
            ),
            200,
        )

        if interface:
            print("Advertised base URL:", interface.get("url"))
            print("Protocol version:", interface.get("protocolVersion"))
            print("Input modes:", card.get("defaultInputModes"))
            print("Output modes:", card.get("defaultOutputModes"))
            print("Skill IDs:", [
                skill.get("id") for skill in card.get("skills", [])
            ])
