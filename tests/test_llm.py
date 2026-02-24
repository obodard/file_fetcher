from file_fetcher.llm.base import SearchFilters

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
