"""Storage helpers for user-defined Custom translator profiles.

A profile is a named OpenAI-compatible endpoint:

    {"name": "Gemini Lite", "api_key": "...", "api_url": "...", "model": "...",
     "api_type": "openai" | "gemini"}

Profiles are persisted as a JSON list under ``credentials/custom_profiles`` in
QSettings. Translator values of the form ``Custom: <name>`` select a profile;
the plain value ``Custom`` resolves to the first profile (kept for backward
compatibility with settings saved before profiles existed).
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

PROFILES_KEY = "custom_profiles"
API_TYPES = ("openai", "gemini")
DEFAULT_API_TYPE = "openai"
CREDENTIALS_GROUP = "credentials"
CUSTOM_VALUE_PREFIX = "Custom:"
LEGACY_FIELDS = ("api_key", "api_url", "model")


def custom_value_for(profile_name: str) -> str:
    """Translator value that selects the given profile."""
    return f"{CUSTOM_VALUE_PREFIX} {profile_name}"


def profile_name_from_value(value: str) -> str | None:
    """Extract the profile name from a 'Custom: <name>' value, else None."""
    if not isinstance(value, str) or not value.startswith(CUSTOM_VALUE_PREFIX):
        return None
    return value[len(CUSTOM_VALUE_PREFIX):].strip()


def load_profiles(qsettings) -> list[dict]:
    """Read the profile list; malformed content yields an empty list."""
    qsettings.beginGroup(CREDENTIALS_GROUP)
    raw = qsettings.value(PROFILES_KEY, "", type=str)
    qsettings.endGroup()

    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("custom_profiles is not valid JSON; ignoring it")
        return []
    if not isinstance(data, list):
        return []

    profiles: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        api_type = str(item.get("api_type", DEFAULT_API_TYPE) or DEFAULT_API_TYPE).lower()
        if api_type not in API_TYPES:
            api_type = DEFAULT_API_TYPE
        profiles.append({
            "name": name,
            "api_key": str(item.get("api_key", "") or ""),
            "api_url": str(item.get("api_url", "") or ""),
            "model": str(item.get("model", "") or ""),
            "api_type": api_type,
        })
    return profiles


def save_profiles(qsettings, profiles: list[dict]) -> None:
    qsettings.beginGroup(CREDENTIALS_GROUP)
    qsettings.setValue(PROFILES_KEY, json.dumps(profiles, ensure_ascii=False))
    qsettings.endGroup()


def migrate_legacy_profile(qsettings, profiles: list[dict]) -> list[dict]:
    """Fold the pre-profile single Custom configuration into the list.

    Runs only when no ``custom_profiles`` value was ever written; an explicitly
    saved empty list means the user deleted all profiles and must not be
    resurrected from the legacy keys.
    """
    if profiles:
        return profiles
    qsettings.beginGroup(CREDENTIALS_GROUP)
    raw = qsettings.value(PROFILES_KEY, None)
    qsettings.endGroup()
    if raw is not None:
        return profiles
    qsettings.beginGroup(CREDENTIALS_GROUP)
    legacy = {field: qsettings.value(f"Custom_{field}", "", type=str) for field in LEGACY_FIELDS}
    qsettings.endGroup()
    if any(legacy.values()):
        logger.info("Migrated legacy Custom credentials into a 'Default' profile")
        return [{"name": "Default", **legacy, "api_type": DEFAULT_API_TYPE}]
    return profiles


def resolve_profile(profiles: list[dict], value: str) -> dict | None:
    """Map a translator value ('Custom' or 'Custom: <name>') to a profile.

    Unknown profile names fall back to the first profile so a deleted profile
    never breaks translation entirely.
    """
    if not profiles:
        return None
    name = profile_name_from_value(value)
    if name:
        for profile in profiles:
            if profile["name"] == name:
                return profile
        lowered = name.lower()
        for profile in profiles:
            if profile["name"].lower() == lowered:
                return profile
    return profiles[0]
