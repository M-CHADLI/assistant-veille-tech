"""Default source lists for the daily batch scrape (cf. guide.md, sections 1.3 et 1.4)."""

from __future__ import annotations

GITHUB_REPOS: list[str] = [
    "vercel/next.js",
    "openai/openai-python",
    "remix-run/remix",
    "withastro/astro",
    "chroma-core/chroma",
    "langchain-ai/langchain",
    "anthropics/anthropic-sdk-python",
    "vuejs/core",
    "tiangolo/fastapi",
    "vercel/vercel",
]

RSS_FEEDS: list[str] = [
    "https://dev.to/feed",
    "https://css-tricks.com/feed/",
    "https://blog.logrocket.com/feed/",
    "https://changelog.com/feed",
]


def github_releases_urls(repos: list[str] = GITHUB_REPOS) -> list[str]:
    return [f"https://api.github.com/repos/{repo}/releases" for repo in repos]


def default_scrape_urls() -> list[str]:
    return RSS_FEEDS + github_releases_urls()
