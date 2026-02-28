"""Tests for web/app.py — FastAPI application factory."""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """Return a configured FastAPI app instance."""
    from file_fetcher.web.app import create_app

    return create_app()


@pytest.fixture
def client(app):
    """Return a TestClient for the app."""
    return TestClient(app)


class TestCreateApp:
    def test_returns_fastapi_instance(self, app):
        """create_app() must return a FastAPI instance."""
        assert isinstance(app, FastAPI)

    def test_has_static_mount(self, app):
        """App must have a /static mount for serving CSS/JS."""
        routes = {r.path: r for r in app.routes}
        assert "/static" in routes, "/static route not found"

    def test_has_index_route(self, app):
        """App must expose a GET / route."""
        routes = {getattr(r, "path", None) for r in app.routes}
        assert "/" in routes, "GET / route not found"


class TestIndexRoute:
    def test_get_index_returns_200(self, client):
        """GET / must return HTTP 200."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert response.status_code == 200

    def test_get_index_returns_html(self, client):
        """GET / must return HTML content."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert "text/html" in response.headers.get("content-type", "")

    def test_navbar_in_response(self, client):
        """GET / response must include navbar markup."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert "<nav" in response.text

    def test_base_template_structure(self, client):
        """GET / response must contain key base template elements."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        body = response.text
        assert "<!DOCTYPE html>" in body
        assert 'id="main-content"' in body
        assert "Skip to content" in body

    def test_htmx_script_included(self, client):
        """Base template must include HTMX script."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert "htmx.org" in response.text

    def test_data_theme_attribute(self, client):
        """Base template must include data-theme on html element for DaisyUI."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert "data-theme=" in response.text

