"""
Deterministic API onboarding workflow:
discover docs/signup -> browser signup -> email verification/key retrieval -> .env install.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from tools.api_key_extractors import (
    CredentialCandidate,
    extract_verification_links,
)
from tools.env_install import install_secrets_to_env
from tools.google_auth import get_credentials
from tools.provider_profiles import ProviderProfile, resolve_provider_profile
from tools.web_automation import playwright_headless_default


class OnboardingStage(str, Enum):
    PRECHECK = "PRECHECK"
    DISCOVER = "DISCOVER"
    SIGNUP = "SIGNUP"
    VERIFY_EMAIL = "VERIFY_EMAIL"
    OBTAIN_KEY = "OBTAIN_KEY"
    INSTALL = "INSTALL"
    VALIDATE = "VALIDATE"
    REPORT = "REPORT"


class OnboardingError(RuntimeError):
    """Raised for fatal onboarding stage failures."""

    def __init__(self, stage: OnboardingStage, message: str):
        super().__init__(message)
        self.stage = stage


@dataclass
class OnboardingContext:
    run_id: str
    provider: str
    account_email: str
    env_path: str
    allow_full_secret_logs: bool
    profile_name: str = ""
    stage: OnboardingStage = OnboardingStage.PRECHECK
    status: str = "running"
    logs: list[str] = field(default_factory=list)
    docs_url: str = ""
    signup_url: str = ""
    discovered_notes: str = ""
    browser_status: str = ""
    browser_blockers: list[str] = field(default_factory=list)
    visited_urls: list[str] = field(default_factory=list)
    candidates: list[CredentialCandidate] = field(default_factory=list)
    installed: dict[str, str] = field(default_factory=dict)

    def log(self, msg: str) -> None:
        line = f"[{self.run_id}][{self.stage.value}] {msg}"
        print(line, flush=True)
        self.logs.append(line)


def onboard_api_integration(
    provider: str,
    account_email: str = "",
    project_env_path: str = "",
    allow_full_secret_logs: bool = True,
    dry_run: bool = False,
) -> str:
    """Top-level orchestrator for API signup + key install flow."""
    resolved_email = account_email.strip() or os.getenv("PMO_API_ONBOARDING_EMAIL", "").strip()
    resolved_env = project_env_path.strip() or str(Path(__file__).resolve().parent.parent / ".env")
    ctx = OnboardingContext(
        run_id=uuid.uuid4().hex[:10],
        provider=provider.strip(),
        account_email=resolved_email,
        env_path=resolved_env,
        allow_full_secret_logs=allow_full_secret_logs,
    )
    profile = resolve_provider_profile(ctx.provider)
    ctx.profile_name = profile.name

    try:
        _stage_precheck(ctx)
        _stage_discover(ctx, profile)
        _stage_signup(ctx, profile)
        _stage_verify_email(ctx, profile)
        _stage_obtain_key(ctx)
        if not dry_run:
            _stage_install(ctx, profile)
            _stage_validate(ctx, profile)
        else:
            ctx.log("Dry run enabled; skipping install/validate.")
        ctx.status = "success"
    except OnboardingError as e:
        ctx.status = "manual_required" if "manual" in str(e).lower() else "failed"
        ctx.log(f"Stage failed at {e.stage.value}: {e}")
    except Exception as e:
        ctx.status = "failed"
        ctx.log(f"Unhandled onboarding error: {e}")
    finally:
        ctx.stage = OnboardingStage.REPORT
        _persist_run_log(ctx)
        return _render_report(ctx)


def _stage_precheck(ctx: OnboardingContext) -> None:
    ctx.stage = OnboardingStage.PRECHECK
    if os.getenv("PMO_API_ONBOARDING_ENABLED", "1").strip().lower() not in ("1", "true", "yes"):
        raise OnboardingError(ctx.stage, "API onboarding disabled by PMO_API_ONBOARDING_ENABLED")
    if not ctx.provider:
        raise OnboardingError(ctx.stage, "Provider is required")
    if not ctx.account_email:
        raise OnboardingError(ctx.stage, "Onboarding email is required (pass account_email or set PMO_API_ONBOARDING_EMAIL)")
    ctx.log(f"Precheck passed for provider={ctx.provider}, email={ctx.account_email}, profile={ctx.profile_name}")


def _stage_discover(ctx: OnboardingContext, profile: ProviderProfile) -> None:
    ctx.stage = OnboardingStage.DISCOVER
    result = profile.discover(ctx.provider)
    ctx.docs_url = result.docs_url
    ctx.signup_url = result.signup_url
    ctx.discovered_notes = result.notes
    ctx.log(f"Discovery docs_url={ctx.docs_url or 'n/a'} signup_url={ctx.signup_url or 'n/a'} notes={ctx.discovered_notes}")
    if not ctx.signup_url:
        raise OnboardingError(ctx.stage, "Could not discover signup URL")


def _stage_signup(ctx: OnboardingContext, profile: ProviderProfile) -> None:
    ctx.stage = OnboardingStage.SIGNUP
    browser_result = profile.run_signup(
        provider=ctx.provider,
        account_email=ctx.account_email,
        signup_url=ctx.signup_url,
        headless=playwright_headless_default(),
        timeout_ms=int(os.getenv("PMO_API_ONBOARDING_TIMEOUT_MS", "30000")),
    )
    ctx.browser_status = browser_result.status
    ctx.browser_blockers = browser_result.blockers
    ctx.visited_urls.extend(browser_result.visited_urls)
    ctx.log(f"Browser status={ctx.browser_status}; visited={len(browser_result.visited_urls)} urls")
    for blocker in ctx.browser_blockers:
        ctx.log(f"Blocker: {blocker}")
    ctx.candidates.extend(profile.extract_candidates_from_browser(ctx.provider, browser_result))


def _stage_verify_email(ctx: OnboardingContext, profile: ProviderProfile) -> None:
    ctx.stage = OnboardingStage.VERIFY_EMAIL
    messages = _poll_gmail_for_provider(profile.gmail_queries(ctx.provider))
    if not messages:
        ctx.log("No matching provider emails found in poll window.")
        return
    ctx.log(f"Collected {len(messages)} provider emails")
    for msg in messages:
        text = msg.get("body", "")
        for link in extract_verification_links(text):
            ctx.log(f"Verification/link candidate: {link}")
        ctx.candidates.extend(profile.extract_candidates_from_email(ctx.provider, text))


def _stage_obtain_key(ctx: OnboardingContext) -> None:
    ctx.stage = OnboardingStage.OBTAIN_KEY
    if not ctx.candidates:
        raise OnboardingError(ctx.stage, "No credential candidates found; manual follow-up required")
    ctx.candidates = sorted(ctx.candidates, key=lambda c: c.confidence, reverse=True)
    preview = ", ".join(f"{c.key_name}@{c.confidence:.2f}" for c in ctx.candidates[:5])
    ctx.log(f"Top candidates: {preview}")


def _stage_install(ctx: OnboardingContext, profile: ProviderProfile) -> None:
    ctx.stage = OnboardingStage.INSTALL
    to_install = profile.select_install_credentials(ctx.candidates)
    if not to_install:
        raise OnboardingError(ctx.stage, "No installable credentials")
    result = install_secrets_to_env(
        env_path=ctx.env_path,
        secrets=to_install,
        allow_full_secret_logs=ctx.allow_full_secret_logs,
    )
    ctx.installed = result.written
    ctx.log(f"Installed {len(result.written)} secret(s) to {result.env_path}")


def _stage_validate(ctx: OnboardingContext, profile: ProviderProfile) -> None:
    ctx.stage = OnboardingStage.VALIDATE
    env_text = Path(ctx.env_path).read_text(encoding="utf-8")
    valid, message = profile.validate_installed(env_text, ctx.installed)
    if not valid:
        raise OnboardingError(ctx.stage, message)
    ctx.log(message)


def _poll_gmail_for_provider(queries: list[str]) -> list[dict]:
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except Exception:
        return []

    creds = get_credentials()
    if not creds:
        return []
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    start = time.time()
    timeout_s = int(os.getenv("PMO_API_ONBOARDING_EMAIL_TIMEOUT_S", "45"))
    poll_interval_s = int(os.getenv("PMO_API_ONBOARDING_EMAIL_POLL_S", "5"))
    seen_ids: set[str] = set()
    found: list[dict] = []
    while time.time() - start < timeout_s:
        for query in queries:
            try:
                result = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
            except HttpError:
                continue
            for item in result.get("messages") or []:
                mid = item.get("id")
                if not mid or mid in seen_ids:
                    continue
                seen_ids.add(mid)
                full = service.users().messages().get(userId="me", id=mid, format="full").execute()
                payload = full.get("payload") or {}
                headers = payload.get("headers") or []
                subject = _header(headers, "Subject")
                body = _decode_payload_body(payload)
                found.append({"id": mid, "subject": subject, "body": body, "query": query})
        if found:
            return found
        time.sleep(poll_interval_s)
    return found


def _header(headers: list[dict], name: str) -> str:
    for header in headers:
        if (header.get("name") or "").lower() == name.lower():
            return (header.get("value") or "").strip()
    return ""


def _decode_payload_body(payload: dict) -> str:
    import base64
    import re

    body = payload.get("body") or {}
    data = body.get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="replace")
        except Exception:
            return ""

    for part in payload.get("parts") or []:
        pbody = part.get("body") or {}
        pdata = pbody.get("data")
        if not pdata:
            continue
        try:
            decoded = base64.urlsafe_b64decode(pdata.encode("ascii")).decode("utf-8", errors="replace")
            if part.get("mimeType") == "text/html":
                decoded = re.sub(r"<[^>]+>", " ", decoded)
            if decoded.strip():
                return decoded.strip()
        except Exception:
            continue
    return ""


def _persist_run_log(ctx: OnboardingContext) -> None:
    try:
        path = Path(os.getenv("PMO_API_ONBOARDING_LOG_PATH", Path(__file__).resolve().parent.parent / "logs" / "api_onboarding.log"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(ctx.logs))
            f.write("\n")
    except Exception:
        pass


def _render_report(ctx: OnboardingContext) -> str:
    lines = [
        f"API onboarding run: {ctx.run_id}",
        f"Provider: {ctx.provider}",
        f"Status: {ctx.status}",
        f"Discovered docs: {ctx.docs_url or 'n/a'}",
        f"Discovered signup: {ctx.signup_url or 'n/a'}",
        f"Browser status: {ctx.browser_status or 'n/a'}",
    ]
    if ctx.browser_blockers:
        lines.append("Browser blockers:")
        lines.extend(f"- {b}" for b in ctx.browser_blockers)
    if ctx.installed:
        lines.append("Installed credentials:")
        lines.extend(f"- {k}={v}" for k, v in ctx.installed.items())
    else:
        lines.append("Installed credentials: none")
    lines.append("Stage logs:")
    lines.extend(f"- {line}" for line in ctx.logs[-15:])
    return "\n".join(lines)

