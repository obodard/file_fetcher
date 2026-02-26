from file_fetcher.llm.base import SearchFilters, sanitize_query, _MAX_QUERY_LENGTH

def test_search_filters_parsing():
    json_str = '{"media_type": "movies", "year": 2026, "max_age_days": 30, "keywords": ["action"]}'
    filters = SearchFilters.model_validate_json(json_str)
    
    assert filters.media_type == "movies"
    assert filters.year == 2026
    assert filters.max_age_days == 30
    assert filters.keywords == ["action"]

def test_search_filters_defaults():
    json_str = '{}'
    filters = SearchFilters.model_validate_json(json_str)
    
    assert filters.media_type == "all"
    assert filters.year is None
    assert filters.max_age_days is None
    assert filters.keywords == []


def test_max_age_days_capped_at_365():
    json_str = '{"max_age_days": 999999}'
    filters = SearchFilters.model_validate_json(json_str)
    assert filters.max_age_days == 365


def test_max_age_days_within_limit_unchanged():
    json_str = '{"max_age_days": 30}'
    filters = SearchFilters.model_validate_json(json_str)
    assert filters.max_age_days == 30


def test_sanitize_query_strips_control_chars():
    raw = "find movies\x00\x01\x0b\x7f about space"
    assert sanitize_query(raw) == "find movies about space"


def test_sanitize_query_preserves_normal_whitespace():
    raw = "find recent\tmovies\nfrom 2026"
    assert sanitize_query(raw) == raw


def test_sanitize_query_truncates_long_input():
    raw = "a" * 1000
    result = sanitize_query(raw)
    assert len(result) == _MAX_QUERY_LENGTH
