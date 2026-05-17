"""Tests for the fast heuristic scorer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scorer import fast_score, compute_info_density, count_entities_regex
from models import Score


def test_fast_score_returns_score():
    content = "Vincent W is a builder based in San Francisco working on AI projects at Nous Research."
    score = fast_score("abc", content, source_id="wiki")
    assert 0.0 <= score.fast_score <= 1.0
    assert score.entity_count >= 2  # Vincent, San Francisco, Nous Research
    assert score.info_density > 0


def test_empty_content_low_score():
    score = fast_score("abc", "", source_id="wiki")
    assert score.fast_score < 0.2


def test_entity_counting():
    text = "John met Mary at Google HQ in New York"
    count = count_entities_regex(text)
    assert count >= 2  # Capitalized words: John, Mary, Google, New York


def test_info_density():
    dense = "The quick brown fox jumps over the lazy dog near the stream"
    sparse = "the the the the the the the the the the"
    assert compute_info_density(dense) > compute_info_density(sparse)


if __name__ == "__main__":
    test_fast_score_returns_score()
    test_empty_content_low_score()
    test_entity_counting()
    test_info_density()
    print("All scorer tests passed!")
