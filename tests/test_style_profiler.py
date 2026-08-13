"""Tests for onboarding style-profile extraction (prompt parse, mock, persona)."""
import json

from app.services.llm import MockLLMClient, _parse_style_profile


def test_mock_profiler_heuristic_casual_cheerful():
    profile = MockLLMClient().extract_style_profile(
        "Halo kak, siap kak! Mantap banget 👍👍\n"
        "Noted kak, gas terus ya kak 😊"
    )
    sp = profile["style_profile"]
    assert sp["formality"] == "casual"
    assert sp["emoji_density"] == "medium"
    assert sp["tone"] == "warm_and_enthusiastic"
    assert "siap kak" in sp["key_phrases"]
    assert profile["identity"]["name"] is None


def test_parse_style_profile_coerces_out_of_enum():
    raw = json.dumps({
        "identity": {"name": "Sinta", "role": "owner", "business_name": None},
        "style_profile": {
            "formality": "shouty",
            "emoji_density": "many",
            "sentence_length": "short",
            "tone": "angry",
            "key_phrases": ["siap kak", "", 42, "mantap", "noted", "oke kak", "satu", "dua"],
        },
        "key_facts_and_preferences": ["jualan sore-sore paling ramai", ""],
    })
    profile = _parse_style_profile(raw)
    sp = profile["style_profile"]
    assert sp["formality"] == "semi-formal"
    assert sp["emoji_density"] == "low"
    assert sp["sentence_length"] == "concise"
    assert sp["tone"] == "professional_and_direct"
    assert sp["key_phrases"] == ["siap kak", "mantap", "noted", "oke kak"]
    assert profile["identity"]["name"] == "Sinta"
    assert profile["key_facts_and_preferences"] == ["jualan sore-sore paling ramai"]


def test_parse_style_profile_accepts_markdown_wrapped_json():
    wrapped = '```json\n{"identity": {"name": "Budi"}, "style_profile": '
    wrapped += '{"formality": "formal", "emoji_density": "none", "sentence_length": "detailed", '
    wrapped += '"tone": "humble_and_polite", "key_phrases": ["dengan hormat"]}, '
    wrapped += '"key_facts_and_preferences": []}\n```'
    profile = _parse_style_profile(wrapped)
    assert profile["identity"]["name"] == "Budi"
    assert profile["style_profile"]["tone"] == "humble_and_polite"


def test_persona_block_built_from_stored_profile():
    from app.graph.nodes import _style_profile_block

    tenant = {
        "onboarding_data": json.dumps({
            "merchant_name": "Toko A",
            "style_profile": {
                "identity": {"name": "Sinta"},
                "style_profile": {
                    "formality": "casual",
                    "emoji_density": "low",
                    "sentence_length": "concise",
                    "tone": "warm_and_enthusiastic",
                    "key_phrases": ["siap kak"],
                },
            },
        })
    }
    block = _style_profile_block(tenant)
    assert "casual" in block and "siap kak" in block and "warm" in block
    assert _style_profile_block({"onboarding_data": "not-json"}) == ""
    assert _style_profile_block({"onboarding_data": "{}"}) == ""
