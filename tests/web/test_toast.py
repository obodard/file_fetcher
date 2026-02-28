"""Tests for make_toast() and ToastContainer — Story 8.3."""
import pytest

from file_fetcher.web.utils import make_toast


class TestMakeToast:
    def test_success_contains_alert_success_class(self):
        """make_toast('ok', 'success') contains 'alert-success' CSS class."""
        html = make_toast("ok", "success")
        assert "alert-success" in html

    def test_error_contains_alert_error_class(self):
        """make_toast('fail', 'error') contains 'alert-error' CSS class."""
        html = make_toast("fail", "error")
        assert "alert-error" in html

    def test_info_contains_alert_info_class(self):
        """make_toast('note', 'info') contains 'alert-info' CSS class."""
        html = make_toast("note", "info")
        assert "alert-info" in html

    def test_default_type_is_info(self):
        """Default type is 'info' when not specified."""
        html = make_toast("hello")
        assert "alert-info" in html

    def test_message_in_output(self):
        """The message string appears in the returned HTML."""
        html = make_toast("File added successfully!")
        assert "File added successfully!" in html

    def test_oob_swap_attribute_present(self):
        """Output contains hx-swap-oob for HTMX OOB insertion."""
        html = make_toast("msg")
        assert "hx-swap-oob" in html
        assert "toast-container" in html

    def test_role_alert_present(self):
        """Output contains role='alert' for accessibility."""
        html = make_toast("msg")
        assert 'role="alert"' in html

    def test_dismiss_button_present(self):
        """Output contains a dismiss button with aria-label='Dismiss'."""
        html = make_toast("msg")
        assert "Dismiss" in html

    def test_error_has_data_toast_error_attr(self):
        """Error toasts have data-toast-error attribute for JS dismiss timing."""
        html = make_toast("err", "error")
        assert "data-toast-error" in html

    def test_success_has_data_toast_attr(self):
        """Success toasts have data-toast attribute (not data-toast-error)."""
        html = make_toast("ok", "success")
        assert "data-toast" in html
        assert "data-toast-error" not in html


class TestToastContainerInBase:
    """Integration test: base.html must render the toast container div."""

    @pytest.fixture
    def client(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from file_fetcher.web.app import create_app

        app = create_app()
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            yield TestClient(app)

    def test_toast_container_present_in_base(self, client):
        """Base template renders #toast-container div."""
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "file_fetcher.web.routes.catalog.search_catalog", return_value=[]
        ):
            response = client.get("/")
        assert "toast-container" in response.text

    def test_toast_container_has_aria_live(self, client):
        """#toast-container has aria-live='polite' for screen readers."""
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "file_fetcher.web.routes.catalog.search_catalog", return_value=[]
        ):
            response = client.get("/")
        assert 'aria-live="polite"' in response.text
