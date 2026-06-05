"""Tests for LLMEntityExtractor — JSON parsing and fault tolerance."""

from xagent.core.wiki.compiler.entity_extractor import LLMEntityExtractor


class TestParseResponse:
    def test_valid_json(self):
        response = """{
  "entities": [
    {"name": "张伟", "type": "person", "context": "学员"},
    {"name": "Python", "type": "technology", "context": "编程语言"}
  ],
  "relations": [
    {"source": "张伟", "target": "Python", "type": "learns", "context": "学习"}
  ]
}"""
        entities, relations = LLMEntityExtractor.parse_response(response)
        assert len(entities) == 2
        assert entities[0].name == "张伟"
        assert entities[0].entity_type == "person"
        assert entities[1].name == "Python"
        assert len(relations) == 1
        assert relations[0].source == "张伟"
        assert relations[0].target == "Python"
        assert relations[0].relation_type == "learns"

    def test_fenced_json(self):
        response = """```json
{"entities": [{"name": "A", "type": "concept"}], "relations": []}
```"""
        entities, relations = LLMEntityExtractor.parse_response(response)
        assert len(entities) == 1
        assert entities[0].name == "A"
        assert relations == []

    def test_fenced_json_without_lang(self):
        response = """```
{"entities": [{"name": "B", "type": "event"}], "relations": []}
```"""
        entities, _ = LLMEntityExtractor.parse_response(response)
        assert len(entities) == 1

    def test_invalid_json_returns_empty(self):
        response = "this is not json at all"
        entities, relations = LLMEntityExtractor.parse_response(response)
        assert entities == []
        assert relations == []

    def test_partial_json_still_works(self):
        response = "Here is the result: {\"entities\": [{\"name\": \"X\"}], \"relations\": []} done."
        entities, _ = LLMEntityExtractor.parse_response(response)
        assert len(entities) == 1
        assert entities[0].name == "X"

    def test_missing_name_skipped(self):
        response = '{"entities": [{"type": "person"}, {"name": "Valid"}], "relations": []}'
        entities, _ = LLMEntityExtractor.parse_response(response)
        assert len(entities) == 1
        assert entities[0].name == "Valid"

    def test_empty_name_skipped(self):
        response = '{"entities": [{"name": "  ", "type": "person"}], "relations": []}'
        entities, _ = LLMEntityExtractor.parse_response(response)
        assert entities == []

    def test_missing_type_defaults(self):
        response = '{"entities": [{"name": "NoType"}], "relations": []}'
        entities, _ = LLMEntityExtractor.parse_response(response)
        assert entities[0].entity_type == "unknown"

    def test_missing_relation_fields_skipped(self):
        response = '{"entities": [], "relations": [{"source": "A"}, {"source": "B", "target": "C"}]}'
        _, relations = LLMEntityExtractor.parse_response(response)
        assert len(relations) == 1
        assert relations[0].source == "B"

    def test_empty_response(self):
        entities, relations = LLMEntityExtractor.parse_response("")
        assert entities == []
        assert relations == []


class TestExtractAsync:
    async def test_extract_calls_llm(self, mock_llm):
        mock_llm.set_default(
            '{"entities": [{"name": "Test", "type": "concept"}], "relations": []}'
        )
        extractor = LLMEntityExtractor(mock_llm)

        from xagent.core.wiki.models import Chunk
        chunks = [Chunk(chunk_id="c1", doc_id="d1", content="Test content", token_count=5, position=0)]
        entities, _ = await extractor.extract(chunks)

        assert len(entities) == 1
        assert entities[0].name == "Test"
        assert mock_llm.call_count == 1
