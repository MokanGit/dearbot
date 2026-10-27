import re
from typing import Tuple


def classify_client(user_agent: str | None) -> Tuple[str, str | None]:
    """
    Classify the client based on User-Agent into:
    - client_type: 'ai_agent' | 'browser' | 'known_bot' | 'unknown'
    - client_name: e.g. 'ChatGPT', 'Claude', 'Perplexity', 'Chrome', 'Safari'

    Best-effort heuristics. Never present inferred client identity as certain.
    """
    if not user_agent:
        return "unknown", None

    ua = user_agent.lower()

    # 1. AI Agents & Crawlers
    if "chatgpt-user" in ua or "gptbot" in ua or "openai" in ua:
        return "ai_agent", "ChatGPT"
    if "claudebot" in ua or "claude-web" in ua or "anthropic" in ua:
        return "ai_agent", "Claude"
    if "perplexitybot" in ua or "perplexity" in ua:
        return "ai_agent", "Perplexity"
    if "cohere-ai" in ua or "cohere" in ua:
        return "ai_agent", "Cohere"
    if "deepseek" in ua:
        return "ai_agent", "DeepSeek"
    if "meta-externalagent" in ua or "facebookbot" in ua:
        return "ai_agent", "Meta AI"

    # 2. Known Search / Social Crawlers & Bots
    if any(bot in ua for bot in [
        "googlebot", "bingbot", "bytespider", "yandex", "duckduckbot",
        "baiduspider", "linkedinbot", "twitterbot", "slackbot", "whatsapp",
        "telegrambot", "discordbot", "curl", "wget", "python-requests", "httpx"
    ]):
        if "googlebot" in ua:
            return "known_bot", "Googlebot"
        if "bingbot" in ua:
            return "known_bot", "Bingbot"
        if "linkedinbot" in ua:
            return "known_bot", "LinkedIn Bot"
        if "slackbot" in ua:
            return "known_bot", "Slackbot"
        return "known_bot", "Automated Crawler/Bot"

    # 3. Standard Browsers
    if "mozilla" in ua:
        if "edg/" in ua:
            return "browser", "Microsoft Edge"
        if "chrome/" in ua and "safari/" in ua and "edg/" not in ua:
            return "browser", "Google Chrome"
        if "firefox/" in ua:
            return "browser", "Mozilla Firefox"
        if "safari/" in ua and "chrome/" not in ua:
            return "browser", "Apple Safari"
        return "browser", "Web Browser"

    return "unknown", None
