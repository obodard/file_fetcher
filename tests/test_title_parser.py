from file_fetcher.title_parser import parse_title_and_year

def test_parse_with_parentheses():
    title, year = parse_title_and_year(
        "Good Bye Lenin! (2003) (Good Bye, Lenin!) 1080p x264 AC3 5.1 MULTI [NOEX]"
    )
    assert title == "Good Bye Lenin!"
    assert year == 2003

def test_parse_with_dots():
    title, year = parse_title_and_year(
        "The.Secret.Agent.2025.SUBFRENCH.1080p.WEBrip.x264-RLK"
    )
    assert title == "The Secret Agent"
    assert year == 2025

def test_parse_no_year():
    title, year = parse_title_and_year("Some Random Movie MULTI 1080p")
    assert title == "Some Random Movie"
    assert year is None

def test_parse_with_extension():
    title, year = parse_title_and_year("Inception.2010.mkv")
    assert title == "Inception"
    assert year == 2010

def test_parse_long_name():
    title, year = parse_title_and_year(
        "A.Charlie.Brown.Christmas.1965.MULTi.1080p.WEB.H264-FW"
    )
    assert title == "A Charlie Brown Christmas"
    assert year == 1965
