"""Tests for the Wikilinker — extraction and generation."""

from xagent.core.wiki.compiler.wikilinker import Wikilinker


class TestExtract:
    def test_no_wikilinks(self):
        assert Wikilinker.extract("plain text without links") == []

    def test_single_wikilink(self):
        result = Wikilinker.extract("See [[Python]] for details.")
        assert result == ["Python"]

    def test_multiple_wikilinks(self):
        text = "Related: [[SQL基础]], [[数据分析]] and [[Python]]."
        result = Wikilinker.extract(text)
        assert result == ["SQL基础", "数据分析", "Python"]

    def test_wikilink_with_alias(self):
        result = Wikilinker.extract("Check [[Python|编程语言]].")
        assert result == ["Python"]

    def test_deduplication(self):
        text = "Mention [[Python]] twice: [[Python]]."
        result = Wikilinker.extract(text)
        assert result == ["Python"]

    def test_order_preserved(self):
        text = "[[C]] then [[A]] then [[B]]."
        assert Wikilinker.extract(text) == ["C", "A", "B"]

    def test_empty_target_skipped(self):
        text = "Empty [[]] should be skipped, but [[Valid]] kept."
        result = Wikilinker.extract(text)
        assert result == ["Valid"]

    def test_chinese_wikilinks(self):
        text = "参见 [[张伟]] 和 [[李明的学习计划]]。"
        result = Wikilinker.extract(text)
        assert result == ["张伟", "李明的学习计划"]


class TestGenerate:
    def test_empty(self):
        assert Wikilinker.generate([]) == ""

    def test_single(self):
        assert Wikilinker.generate(["Python"]) == "- [[Python]]"

    def test_multiple(self):
        result = Wikilinker.generate(["SQL", "Python"])
        assert result == "- [[SQL]]\n- [[Python]]"


class TestMakeLink:
    def test_simple(self):
        assert Wikilinker.make_link("Python") == "[[Python]]"

    def test_with_alias(self):
        assert Wikilinker.make_link("Python", "编程语言") == "[[Python|编程语言]]"
