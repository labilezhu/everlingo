import json
from pathlib import Path

from .models import UserProfile

PROFILE_PATH = Path.home() / ".everlingo" / "profile.json"


def load_profile() -> UserProfile:
    if PROFILE_PATH.exists():
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return UserProfile(
            interface_language=data.get("interface_language", ""),
            target_language=data.get("target_language", ""),
        )
    return UserProfile()


def save_profile(profile: UserProfile) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(
        json.dumps(
            {
                "interface_language": profile.interface_language,
                "target_language": profile.target_language,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
