import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv


class ApiSettingsError(ValueError):
    """Raised when API environment settings are invalid."""


@dataclass(frozen=True)
class ApiSettings:
    title: str = "Traffic and Crowd Monitoring API"
    version: str = "0.1.0"
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @classmethod
    def from_environment(cls) -> "ApiSettings":
        load_dotenv()
        raw_origins = os.getenv("API_CORS_ORIGINS", "http://localhost:5173")
        origins = tuple(
            origin.strip() for origin in raw_origins.split(",") if origin.strip()
        )
        for origin in origins:
            parsed = urlparse(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
            ):
                raise ApiSettingsError(
                    "API_CORS_ORIGINS must contain explicit HTTP or HTTPS origins"
                )
        return cls(cors_origins=origins)
