"""Tests for misc/ascii.py banner rendering."""
import pathlib
import sys

from rich.text import Text

# Ensure project root is importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from misc.ascii import generate_codemitra_banner_art, generate_title_art


class TestGenerateTitleArt:
    def test_returns_rich_text(self):
        art = generate_title_art("CODE\nMITRA", cols=48, rows=8)
        assert isinstance(art, Text)

    def test_contains_filled_ascii_characters(self):
        art = generate_title_art("CODE\nMITRA", cols=48, rows=8)
        rendered = art.plain
        assert any(ch in rendered for ch in "░▒▓█")

    def test_respects_requested_row_count(self):
        art = generate_title_art("CODE\nMITRA", cols=48, rows=8)
        assert len(art.plain.splitlines()) == 8


class TestGenerateCodeMitraBannerArt:
    def test_returns_rich_text(self):
        art = generate_codemitra_banner_art()
        assert isinstance(art, Text)

    def test_contains_codemitra_wordmark(self):
        art = generate_codemitra_banner_art()
        rendered = art.plain
        assert "______" in rendered
        assert "▓▓▓▓▓▓" in rendered
