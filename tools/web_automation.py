"""
Playwright-powered browser automation helpers for API onboarding.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass
class DiscoveryResult:
    provider: str
    docs_url: str
    signup_url: str
    notes: str = ""


@dataclass
class BrowserRunResult:
    status: str
    visited_urls: list[str]
    blockers: list[str]
    extracted_text: list[str]
    artifacts: dict[str, str]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def discover_provider_urls(provider: str) -> DiscoveryResult:
    """
    Attempt provider docs/signup discovery.
    Uses deterministic fallbacks, then DuckDuckGo lite JSON endpoint.
    """
    clean = provider.strip()
    slug = _slug(clean)
    if not clean:
        return DiscoveryResult(provider=provider, docs_url="", signup_url="", notes="Empty provider")

    candidates = [
        f"https://developer.{slug}.com",
        f"https://developers.{slug}.com",
        f"https://{slug}.com/developers",
        f"https://{slug}.com/docs",
        f"https://{slug}.com/signup",
    ]
    reachable = []
    for url in candidates:
        if _url_exists(url):
            reachable.append(url)
    if reachable:
        docs_url = reachable[0]
        signup_url = reachable[-1]
        return DiscoveryResult(provider=clean, docs_url=docs_url, signup_url=signup_url, notes="Heuristic URL discovery")

    query = urllib.parse.quote_plus(f"{clean} developer api signup")
    ddg_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
    try:
        with urllib.request.urlopen(ddg_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return DiscoveryResult(provider=clean, docs_url="", signup_url="", notes="Discovery failed")

    abstract_url = payload.get("AbstractURL") or ""
    related = payload.get("RelatedTopics") or []
    related_urls: list[str] = []
    for topic in related:
        if isinstance(topic, dict):
            if "FirstURL" in topic:
                related_urls.append(topic["FirstURL"])
            for nested in topic.get("Topics") or []:
                if isinstance(nested, dict) and "FirstURL" in nested:
                    related_urls.append(nested["FirstURL"])

    urls = [u for u in [abstract_url, *related_urls] if isinstance(u, str) and u.startswith("http")]
    docs_url = urls[0] if urls else ""
    signup_url = next((u for u in urls if any(x in u.lower() for x in ("signup", "register", "developer", "api"))), docs_url)
    return DiscoveryResult(provider=clean, docs_url=docs_url, signup_url=signup_url, notes="DuckDuckGo discovery")


def _url_exists(url: str) -> bool:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            return response.status < 400
    except Exception:
        return False


def run_signup_automation(
    provider: str,
    account_email: str,
    signup_url: str,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> BrowserRunResult:
    """
    Drive signup/dashboard flow and collect evidence.
    Returns blockers when manual action is likely required.
    """
    visited: list[str] = []
    blockers: list[str] = []
    extracted_text: list[str] = []
    artifacts: dict[str, str] = {}
    if not signup_url:
        return BrowserRunResult(
            status="failed",
            visited_urls=visited,
            blockers=["No signup URL discovered"],
            extracted_text=extracted_text,
            artifacts=artifacts,
        )

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return BrowserRunResult(
            status="failed",
            visited_urls=visited,
            blockers=[f"Playwright unavailable: {e}"],
            extracted_text=extracted_text,
            artifacts=artifacts,
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(signup_url, wait_until="domcontentloaded", timeout=timeout_ms)
            visited.append(page.url)
            body_text = page.inner_text("body")[:5000]
            extracted_text.append(body_text)
            _detect_blockers(body_text, blockers)
            _fill_email_if_possible(page, account_email)
            _click_primary_continue(page)
            page.wait_for_timeout(2000)
            visited.append(page.url)
            body_text_after = page.inner_text("body")[:8000]
            extracted_text.append(body_text_after)
            _detect_blockers(body_text_after, blockers)
            # Grab obvious dashboard credentials if they show up.
            _extract_inline_artifacts(body_text_after, artifacts)
            browser.close()
    except PlaywrightTimeoutError as e:
        blockers.append(f"Timed out during browser automation: {e}")
        return BrowserRunResult(
            status="manual_required",
            visited_urls=visited,
            blockers=blockers,
            extracted_text=extracted_text,
            artifacts=artifacts,
        )
    except Exception as e:
        blockers.append(f"Browser automation failed: {e}")
        return BrowserRunResult(
            status="failed",
            visited_urls=visited,
            blockers=blockers,
            extracted_text=extracted_text,
            artifacts=artifacts,
        )

    status = "manual_required" if blockers else "ok"
    return BrowserRunResult(
        status=status,
        visited_urls=visited,
        blockers=blockers,
        extracted_text=extracted_text,
        artifacts=artifacts,
    )


def _fill_email_if_possible(page, account_email: str) -> None:
    email_selectors = [
        'input[type="email"]',
        'input[name="email"]',
        'input[id*="email"]',
        'input[placeholder*="email" i]',
    ]
    for selector in email_selectors:
        locator = page.locator(selector).first
        if locator.count() > 0 and locator.is_visible():
            locator.fill(account_email)
            return


def _click_primary_continue(page) -> None:
    labels = ["Sign up", "Create account", "Continue", "Next", "Get started"]
    for label in labels:
        btn = page.get_by_role("button", name=re.compile(label, re.I)).first
        if btn.count() > 0 and btn.is_enabled():
            btn.click(timeout=2000)
            return


def _detect_blockers(body_text: str, blockers: list[str]) -> None:
    low = body_text.lower()
    if any(term in low for term in ("captcha", "i am not a robot", "recaptcha")):
        blockers.append("CAPTCHA detected")
    if any(term in low for term in ("phone number", "sms verification", "text message code")):
        blockers.append("Phone verification required")
    if any(term in low for term in ("check your email", "verify your email", "confirmation email")):
        blockers.append("Email verification required")


def _extract_inline_artifacts(body_text: str, artifacts: dict[str, str]) -> None:
    patterns = {
        "api_key": re.compile(r"(?i)\bapi[_\s-]?key\b\s*[:=]\s*([A-Za-z0-9_\-\.]{10,})"),
        "access_token": re.compile(r"(?i)\baccess[_\s-]?token\b\s*[:=]\s*([A-Za-z0-9_\-\.]{10,})"),
        "client_id": re.compile(r"(?i)\bclient[_\s-]?id\b\s*[:=]\s*([A-Za-z0-9_\-\.]{6,})"),
        "client_secret": re.compile(r"(?i)\bclient[_\s-]?secret\b\s*[:=]\s*([A-Za-z0-9_\-\.]{10,})"),
    }
    for name, pattern in patterns.items():
        match = pattern.search(body_text)
        if match:
            artifacts[name] = match.group(1)


def playwright_headless_default() -> bool:
    raw = os.getenv("PMO_API_ONBOARDING_PLAYWRIGHT_HEADLESS", "0").strip().lower()
    return raw in ("1", "true", "yes")

