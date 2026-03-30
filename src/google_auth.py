import requests
from tenacity import retry, stop_after_attempt, wait_fixed


class GoogleAuthError(Exception):
    pass


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def get_google_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    url = "https://oauth2.googleapis.com/token"

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    response = requests.post(url, data=data, timeout=30)

    if response.status_code != 200:
        raise GoogleAuthError(
            f"Failed to refresh access token: {response.status_code} {response.text}"
        )

    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise GoogleAuthError("No access_token in Google response")

    return token
