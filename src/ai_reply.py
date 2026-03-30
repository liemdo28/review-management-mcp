import openai
from typing import Any


def fallback_reply(star_rating: str) -> str:
    """Hardcoded fallback if OpenAI call fails."""
    if star_rating in ("FIVE", "FOUR"):
        return (
            "Thank you so much for your kind review! We truly appreciate your support "
            "and look forward to serving you again soon. It's customers like you that "
            "keep us motivated to deliver the best experience."
        )
    return (
        "Thank you for your feedback. We are sorry your experience did not fully meet expectations. "
        "Please contact us directly so we can learn more and work to make it right. "
        "We value your input and are committed to improvement."
    )


def build_reply(
    review: dict[str, Any],
    restaurant_name: str,
    location: str,
    api_key: str,
    model: str,
) -> str:
    """Generate a professional restaurant reply using OpenAI."""
    star_map = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
    raw_rating = review.get("starRating", "UNKNOWN")
    rating = star_map.get(raw_rating, 0)
    stars = "⭐" * rating if rating else raw_rating

    reviewer_name = (
        review.get("reviewer", {}).get("displayName", "")
        or review.get("reviewerName", "")
        or "Guest"
    )
    comment = (review.get("comment") or "").strip()

    system_prompt = (
        "You are a restaurant owner support assistant.\n"
        "Write short, professional, warm, natural Google review replies for a restaurant.\n"
        "Rules:\n"
        "- Keep reply between 40 and 120 words.\n"
        "- Sound human, polite, and concise.\n"
        "- Never mention AI.\n"
        "- Do not invent facts.\n"
        "- Do not offer discounts unless explicitly provided.\n"
        "- For negative reviews (1-3 stars), apologize briefly, acknowledge the issue, "
        "and invite the customer to contact the restaurant privately.\n"
        "- For positive reviews (4-5 stars), thank them and mention looking forward "
        "to serving them again.\n"
        "- Output plain text only."
    )

    user_prompt = (
        f"Restaurant name: {restaurant_name}\n"
        f"Location: {location}\n"
        f"Review rating: {stars}\n"
        f"Reviewer name: {reviewer_name}\n"
        f"Review text: {comment or '[No written comment]'}\n\n"
        "Write a reply suitable for Google Business Profile."
    )

    if not api_key:
        return fallback_reply(raw_rating)

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        text = response.choices[0].message.content or ""
        return text.strip()
    except Exception as e:
        print(f"[AI Reply] OpenAI call failed, using fallback: {e}")
        return fallback_reply(raw_rating)