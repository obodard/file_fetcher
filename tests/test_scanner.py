from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
import stat

from file_fetcher.scanner import SFTPScanner
from file_fetcher.llm.base import SearchFilters

def test_scan_filters_by_age():
    mock_sftp = MagicMock()
    mock_downloader = Mock()
    mock_downloader.sftp = mock_sftp
    
    now = datetime.now()
    recent = (now - timedelta(days=5)).timestamp()
    old = (now - timedelta(days=40)).timestamp()
    
    m_rec = Mock()
    m_rec.filename = "Recent Movie (2026)"
    m_rec.st_mtime = recent
    m_rec.st_size = 1000
    m_rec.st_mode = stat.S_IFDIR
    
    m_old = Mock()
    m_old.filename = "Old Movie (2025)"
    m_old.st_mtime = old
    m_old.st_size = 1000
    m_old.st_mode = stat.S_IFDIR
    
    def mock_listdir(path):
        if path == "Media1/Films":
            return [m_rec, m_old]
        raise FileNotFoundError
        
    mock_sftp.listdir_attr.side_effect = mock_listdir
    scanner = SFTPScanner(mock_downloader)
    
    filters = SearchFilters(media_type="movies", max_age_days=30)
    results = scanner.scan(filters)
    
    assert len(results) == 1
    assert results[0].title == "Recent Movie"

def test_scan_filters_by_keyword():
    mock_sftp = MagicMock()
    mock_downloader = Mock()
    mock_downloader.sftp = mock_sftp
    
    now = datetime.now()
    
    m1 = Mock()
    m1.filename = "Avatar (2009)"
    m1.st_mtime = now.timestamp()
    m1.st_size = 1000
    m1.st_mode = stat.S_IFDIR
    
    m2 = Mock()
    m2.filename = "Avatar The Way of Water (2022)"
    m2.st_mtime = now.timestamp()
    m2.st_size = 1000
    m2.st_mode = stat.S_IFDIR
    
    def mock_listdir(path):
        if path == "Media1/Films":
            return [m1, m2]
        raise FileNotFoundError
        
    mock_sftp.listdir_attr.side_effect = mock_listdir
    scanner = SFTPScanner(mock_downloader)
    
    filters = SearchFilters(media_type="movies", keywords=["Avatar", "water"])
    results = scanner.scan(filters)
    
    assert len(results) == 1
    assert results[0].title == "Avatar The Way of Water"
