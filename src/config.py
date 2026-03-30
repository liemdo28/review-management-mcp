from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_refresh_token: str = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    google_account_id: str = os.getenv("GOOGLE_ACCOUNT_ID", "")

    google_location_id_raw_sushi_stockton: str = os.getenv("GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON", "")
    google_location_id_bakudan_bandera: str = os.getenv("GOOGLE_LOCATION_ID_BAKUDAN_BANDERA", "")
    google_location_id_bakudan_rim: str = os.getenv("GOOGLE_LOCATION_ID_BAKUDAN_RIM", "")
    google_location_id_bakudan_stone_oak: str = os.getenv("GOOGLE_LOCATION_ID_BAKUDAN_STONE_OAK", "")

    dry_run: bool = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")
    state_file: str = os.getenv("STATE_FILE", "state/reviews.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/app.log")

    @property
    def location_ids(self) -> list[tuple[str, str]]:
        ids = []
        mapping = {
            self.google_location_id_raw_sushi_stockton: "Raw Sushi (Stockton)",
            self.google_location_id_bakudan_bandera: "Bakudan Ramen (Bandera)",
            self.google_location_id_bakudan_rim: "Bakudan Ramen (The Rim)",
            self.google_location_id_bakudan_stone_oak: "Bakudan Ramen (Stone Oak)",
        }
        for loc_id, name in mapping.items():
            if loc_id:
                ids.append((loc_id, name))
        return ids

    @property
    def is_configured(self) -> bool:
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.google_refresh_token
            and self.google_account_id
            and self.location_ids
        )


settings = Settings()