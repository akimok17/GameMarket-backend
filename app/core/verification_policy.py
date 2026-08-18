from __future__ import annotations

from typing import Iterable

VALID_POLICIES = {"none", "any", "email", "phone", "both"}


def normalize_policy(value: str | None, default: str = "any") -> str:
    policy = (value or default).strip().lower()
    if policy not in VALID_POLICIES:
        raise RuntimeError(f"Invalid verification policy: {policy}")
    return policy


def policy_satisfied(user, policy: str) -> bool:
    policy = normalize_policy(policy)
    email_ok = bool(getattr(user, "email_verified_at", None))
    phone_ok = bool(getattr(user, "phone_verified_at", None))
    if policy == "none":
        return True
    if policy == "any":
        return email_ok or phone_ok
    if policy == "email":
        return email_ok
    if policy == "phone":
        return phone_ok
    return email_ok and phone_ok


def missing_channels(user, policy: str) -> list[str]:
    policy = normalize_policy(policy)
    email_ok = bool(getattr(user, "email_verified_at", None))
    phone_ok = bool(getattr(user, "phone_verified_at", None))
    if policy == "none":
        return []
    if policy == "any":
        return [] if (email_ok or phone_ok) else ["email_or_phone"]
    if policy == "email":
        return [] if email_ok else ["email"]
    if policy == "phone":
        return [] if phone_ok else ["phone"]
    missing: list[str] = []
    if not email_ok:
        missing.append("email")
    if not phone_ok:
        missing.append("phone")
    return missing


def policy_text(policy: str) -> str:
    policy = normalize_policy(policy)
    return {
        "none": "Подтверждение не требуется",
        "any": "Подтвердите email или телефон",
        "email": "Подтвердите email",
        "phone": "Подтвердите телефон",
        "both": "Подтвердите email и телефон",
    }[policy]


def policy_needs_channel(policy: str, channel: str) -> bool:
    policy = normalize_policy(policy)
    if policy == "both":
        return channel in {"email", "phone"}
    if policy == "any":
        return channel in {"email", "phone"}
    return policy == channel
