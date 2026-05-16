"""Tests for app/agents/web.py."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.agents import web as web_agent


class TestSearchWeb:
    def test_search_web_parses_results(self, monkeypatch):
        html = """
        <html><body>
        <a class="result__a" href="https://example.com/python-packaging">Python Packaging Guide</a>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.example.com%2Fpackaging">Packaging Docs</a>
        </body></html>
        """
        monkeypatch.setattr(web_agent, "_http_get", lambda url, timeout=15: html)

        result = web_agent.search_web.invoke({"query": "python packaging"})

        assert "Web results for 'python packaging'" in result
        assert "Python Packaging Guide" in result
        assert "https://docs.example.com/packaging" in result

    def test_search_web_requires_query(self):
        result = web_agent.search_web.invoke({"query": ""})
        assert "No search query" in result


class TestFetchUrl:
    def test_fetch_url_extracts_title_and_text(self, monkeypatch):
        html = """
        <html>
            <head><title>Example Docs</title><style>.x{}</style></head>
            <body>
                <h1>Welcome</h1>
                <p>Read the docs carefully.</p>
                <script>console.log("skip me")</script>
            </body>
        </html>
        """
        monkeypatch.setattr(web_agent, "_http_get", lambda url, timeout=15: html)

        result = web_agent.fetch_url.invoke({"url": "https://example.com/docs"})

        assert "# Example Docs" in result
        assert "https://example.com/docs" in result
        assert "Read the docs carefully." in result
        assert "skip me" not in result

    def test_fetch_url_requires_url(self):
        result = web_agent.fetch_url.invoke({"url": ""})
        assert "No URL provided" in result
