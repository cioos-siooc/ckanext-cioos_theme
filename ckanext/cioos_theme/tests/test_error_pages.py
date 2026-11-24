"""Tests for templates/error_document_template.html."""

import pytest


@pytest.mark.usefixtures("with_plugins")
def test_unknown_url_renders_404_page(app):
    body = app.get("/no-such-page-anywhere", status=404).body
    assert "404 - Page not found" in body
    assert "The requested URL was not found on the server." in body
    assert 'href="/dataset/"' in body


@pytest.mark.usefixtures("with_plugins")
def test_not_found_dataset_shows_ckan_message(app):
    body = app.get("/dataset/no-such-dataset", status=404).body
    assert "404 - Page not found" in body
    assert "Dataset not found" in body
