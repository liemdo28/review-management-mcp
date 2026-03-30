import requests
from tenacity import retry, stop_after_attempt, wait_fixed
from typing import Any


class GoogleReviewAPIError(Exception):
    pass


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def list_reviews(
    access_token: str,
    account_id: str,
    location_id: str,
) -> list[dict[str, Any]]:
    url = (
        f"https://mybusiness.googleapis.com/v4/"
        f"accounts/{account_id}/locations/{location_id}/reviews"
    )
    response = requests.get(url, headers=_headers(access_token), timeout=30)

    if response.status_code != 200:
        raise GoogleReviewAPIError(
            f"Failed to list reviews: {response.status_code} {response.text}"
        )

    payload = response.json()
    return payload.get("reviews", [])


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def reply_to_review(
    access_token: str,
    account_id: str,
    location_id: str,
    review_id: str,
    comment: str,
) -> dict[str, Any]:
    url = (
        f"https://mybusiness.googleapis.com/v4/accounts/"
        f"{account_id}/locations/{location_id}/reviews/{review_id}/reply"
    )

    response = requests.put(
        url,
        headers=_headers(access_token),
        json={"comment": comment},
        timeout=30,
    )

    if response.status_code not in (200, 201):
        raise GoogleReviewAPIError(
            f"Failed to reply to review: {response.status_code} {response.text}"
        )

    return response.json()