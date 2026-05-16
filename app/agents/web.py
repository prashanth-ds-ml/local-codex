"""Web Agent — searches the web and reads specific URLs."""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

_USER_AGENT = "CodeMitra/1.0 (+https://github.com)"
_MAX_FETCH_CHARS = 6000
_DEFAULT_TIMEOUT = 15


def _invoke_with_status(llm_with_tools, messages: list, console: Console | None, label: str) -> AIMessage:
    if console is None:
        return llm_with_tools.invoke(messages)
    with console.status(f"[bold cyan]{label}[/bold cyan]", spinner="dots"):
        return llm_with_tools.invoke(messages)


def _run_tool_with_status(fn, args: dict, console: Console | None, label: str) -> str:
    if console is None:
        return fn.invoke(args)
    with console.status(f"[bold cyan]{label}[/bold cyan]", spinner="dots"):
        return fn.invoke(args)


def _http_get(url: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(250_000)
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _resolve_search_result_url(href: str) -> str | None:
    if not href:
        return None
    candidate = href.strip()
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    parsed = urllib.parse.urlparse(candidate)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        query = urllib.parse.parse_qs(parsed.query)
        target = query.get("uddg", [])
        if target:
            candidate = urllib.parse.unquote(target[0])
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    return None


class _SearchResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_map = dict(attrs)
        class_name = attrs_map.get("class") or ""
        href = attrs_map.get("href") or ""
        resolved = _resolve_search_result_url(href)
        if not resolved:
            return
        if "result__a" not in class_name and "result-link" not in class_name and "result-link" not in href:
            return
        self._current_href = resolved
        self._current_chunks = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return
        title = re.sub(r"\s+", " ", "".join(self._current_chunks)).strip()
        if title and not any(url == self._current_href for _, url in self.results):
            self.results.append((title, self._current_href))
        self._current_href = None
        self._current_chunks = []


class _PageTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._capture_title = False
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag == "title":
            self._capture_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._capture_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._capture_title:
            self.title = text
        else:
            self._chunks.append(text)

    def text(self, max_chars: int) -> str:
        joined = " ".join(self._chunks)
        compact = re.sub(r"\s+", " ", html.unescape(joined)).strip()
        return compact[:max_chars].rstrip()


@tool
def search_web(query: str, max_results: int = 5) -> str:
    """
    Search the public web for a topic and return the top result titles with URLs.
    Use for online research, current information, documentation lookups, and general internet search.
    """
    q = (query or "").strip()
    if not q:
        return "✗ No search query provided."
    try:
        url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
        html_text = _http_get(url)
    except Exception as exc:
        return f"✗ Web search failed: {exc}"

    parser = _SearchResultsParser()
    parser.feed(html_text)
    results = parser.results[: max(1, min(max_results, 10))]
    if not results:
        return f"No web results found for '{q}'."

    lines = [f"# Web results for '{q}'"]
    for index, (title, href) in enumerate(results, 1):
        lines.append(f"{index}. {title}")
        lines.append(f"   {href}")
    return "\n".join(lines)


@tool
def fetch_url(url: str, max_chars: int = _MAX_FETCH_CHARS) -> str:
    """
    Fetch a specific URL and return the page title plus the main readable text.
    Use when the user gives a webpage URL or asks to inspect a specific page.
    """
    target = (url or "").strip()
    if not target:
        return "✗ No URL provided."
    if not re.match(r"^https?://", target, re.IGNORECASE):
        target = "https://" + target
    try:
        html_text = _http_get(target)
    except Exception as exc:
        return f"✗ URL fetch failed: {exc}"

    parser = _PageTextParser()
    parser.feed(html_text)
    page_text = parser.text(max(500, max_chars))
    if not page_text:
        page_text = _strip_tags(html_text)[:max_chars].rstrip()
    title = parser.title or target
    return f"# {title}\nURL: {target}\n\n{page_text[:max_chars].rstrip()}"


_ALL_TOOLS = [search_web, fetch_url]

_SYSTEM_PROMPT = """You are the Web Agent inside CodeMitra.
You can search the public web and read specific web pages.

## Available tools
- search_web : search the web for a topic and return result titles with URLs
- fetch_url  : read a specific webpage URL and return readable text

## Rules
1. If the user provides a URL, use fetch_url first.
2. If the user asks for online research or current/public information, use search_web.
3. After search_web, fetch 1-2 relevant pages when you need more than titles.
4. Keep the answer concise and practical.
5. Include the source URLs in the final answer when you used web results.
6. Never pretend you browsed a page you did not fetch.
"""


@dataclass
class WebResponse:
    request: str
    findings: list[str] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)
    summary: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


def _first_failure_text(tool_outputs: list[str]) -> str:
    for output in tool_outputs:
        cleaned = (output or "").strip()
        if cleaned.startswith("✗"):
            return cleaned.lstrip("✗").strip().splitlines()[0]
    return ""


def _finalize_summary(tool_outputs: list[str], model_summary: str) -> str:
    failures = [output for output in tool_outputs if (output or "").strip().startswith("✗")]
    if not failures:
        return model_summary

    first_error = _first_failure_text(tool_outputs)
    if len(failures) == len(tool_outputs):
        return f"Could not complete the web request. {first_error}." if first_error else "Could not complete the web request."
    if first_error:
        return f"Completed part of the web request, but hit {len(failures)} error{'s' if len(failures) != 1 else ''}. {first_error}."
    return f"Completed part of the web request, but hit {len(failures)} error{'s' if len(failures) != 1 else ''}."


def run(llm, user_request: str, console: Console | None = None) -> WebResponse:
    llm_with_tools = llm.bind_tools(_ALL_TOOLS)
    tool_map = {tool_obj.name: tool_obj for tool_obj in _ALL_TOOLS}
    response_obj = WebResponse(request=user_request)
    messages: list = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_request),
    ]

    while True:
        phase = "Summarizing web findings..." if any(isinstance(m, ToolMessage) for m in messages) else "Planning web steps..."
        response: AIMessage = _invoke_with_status(llm_with_tools, messages, console, phase)
        meta = getattr(response, "usage_metadata", None) or {}
        response_obj.tokens_in += meta.get("input_tokens", 0)
        response_obj.tokens_out += meta.get("output_tokens", 0)
        messages.append(response)

        if not response.tool_calls:
            response_obj.summary = _finalize_summary(response_obj.tool_outputs, (response.content or "").strip())
            return response_obj

        for tc in response.tool_calls:
            if console is not None:
                args_str = ", ".join(
                    f"{key}={repr(str(value))[:60]}" for key, value in tc["args"].items()
                )
                console.print(
                    f"  [dim cyan]⋯[/dim cyan] [cyan]{tc['name']}[/cyan][dim]({args_str})[/dim]"
                )
            fn = tool_map.get(tc["name"])
            if fn is None:
                output = f"✗ Unknown tool: {tc['name']}"
            else:
                tool_label = "Fetching webpage..." if tc["name"] == "fetch_url" else "Searching public web..."
                output = _run_tool_with_status(fn, tc["args"], console, tool_label)
            response_obj.tool_outputs.append(str(output))
            response_obj.findings.append(f"{tc['name']}: {str(output)[:200]}")
            messages.append(ToolMessage(content=str(output), tool_call_id=tc["id"]))


def render(response: WebResponse) -> Panel:
    return Panel(
        Markdown(response.summary),
        title="[bold cyan]Web Search[/bold cyan]",
        border_style="cyan",
    )


def make_routing_tool(llm, console: Console | None = None):
    @tool
    def browse_web(request: str) -> str:
        """
        Search the web or inspect a specific webpage.
        Use for internet research, public documentation, current information, or when the user provides a URL.
        Pass the full user request unchanged.
        """
        response = run(llm, request, console=console)
        return response.summary

    return browse_web
