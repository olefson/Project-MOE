"""
Provider profile resolver.
"""

from __future__ import annotations

from tools.provider_profiles.base import ProviderProfile
from tools.provider_profiles.generic import GenericProviderProfile
from tools.provider_profiles.stripe import StripeProviderProfile
from tools.provider_profiles.twilio import TwilioProviderProfile


_PROFILE_BY_NAME: dict[str, ProviderProfile] = {
    "stripe": StripeProviderProfile(),
    "twilio": TwilioProviderProfile(),
}


def resolve_provider_profile(provider: str) -> ProviderProfile:
    normalized = provider.strip().lower()
    if normalized in _PROFILE_BY_NAME:
        return _PROFILE_BY_NAME[normalized]
    return GenericProviderProfile()

