import os
from datetime import datetime, timezone


def run():
    print("=== Weekly Python Job Started ===")
    print("UTC time:", datetime.now(timezone.utc).isoformat())

    # Ví dụ đọc biến môi trường từ GitHub Secrets
    demo_secret = os.getenv("DEMO_SECRET", "")
    if demo_secret:
        print("DEMO_SECRET loaded successfully.")
    else:
        print("No DEMO_SECRET found. Running without secret.")

    # TODO: Đặt code thật của bạn ở đây
    print("Hello from weekly job!")

    print("=== Weekly Python Job Finished ===")


if __name__ == "__main__":
    run()