"""Tests for helpers.py."""

import pytest

from ckanext.cioos_theme.helpers import theme_color_overrides


@pytest.mark.ckan_config("ckan.cioos.primary_color", "#1b6ca8")
@pytest.mark.ckan_config("ckan.cioos.accent_color", " #FA7 ")
@pytest.mark.ckan_config("ckan.cioos.footer_color", "#0b1f26")
def test_theme_color_overrides_maps_config_to_tokens():
    assert theme_color_overrides() == {
        "--cioos-primary": "#1b6ca8",
        "--cioos-accent": "#FA7",
        "--cioos-footer-bg": "#0b1f26",
    }


@pytest.mark.ckan_config("ckan.cioos.primary_color", "red;}</style><script>")
@pytest.mark.ckan_config("ckan.cioos.primary_dark_color", "#12345")
def test_theme_color_overrides_drops_non_hex_values():
    assert theme_color_overrides() == {}


@pytest.mark.usefixtures("with_plugins")
@pytest.mark.ckan_config("ckan.cioos.primary_color", "#1b6ca8")
def test_theme_color_overrides_rendered_in_page(app):
    assert ":root { --cioos-primary: #1b6ca8; }" in app.get("/dataset/").body
