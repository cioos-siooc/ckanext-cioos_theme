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



def _eov(name, category="Physical", count=0):
    return {"name": name, "category": category, "count": count}


def test_eov_categories_orders_categories_and_ranks_by_count():
    from ckanext.cioos_theme.helpers import eov_categories

    groups = eov_categories([
        _eov("oxygen", category="Biogeochemical", count=926),
        _eov("brandNew", category="Aardvark", count=3),
        _eov("seaState", count=29),
        _eov("seaSurfaceTemperature", count=286),
    ])

    # Fixed order first; categories outside it follow alphabetically.
    assert [g["category"] for g in groups] == ["Physical", "Biogeochemical", "Aardvark"]
    assert [x["name"] for x in groups[0]["eovs"]] == ["seaSurfaceTemperature", "seaState"]


def test_eov_categories_applies_exclusions_and_handles_no_counts():
    from ckanext.cioos_theme.helpers import eov_categories

    groups = eov_categories(
        [{"name": "seaState", "category": "Physical"}, _eov("oxygen", category="Biogeochemical"), _eov("seaIce")],
        exclude_eov="['seaIce']",
        exclude_category="Biogeochemical",
    )

    assert groups == [{"category": "Physical", "eovs": [_eov("seaState")]}]


@pytest.mark.ckan_config("ckan.cioos.primary_color", "#1b6ca8")
@pytest.mark.ckan_config("ckan.cioos.eov_icon_color", "")
def test_eov_icon_color_follows_primary_color():
    from ckanext.cioos_theme.helpers import eov_icon_color

    assert eov_icon_color() == "#1b6ca8"


@pytest.mark.ckan_config("ckan.cioos.primary_color", "#1b6ca8")
@pytest.mark.ckan_config("ckan.cioos.eov_icon_color", "#e55162")
def test_eov_icon_color_overrides_primary_color():
    from ckanext.cioos_theme.helpers import eov_icon_color

    assert eov_icon_color() == "#e55162"


def test_recolored_eov_icon_replaces_only_the_teal():
    from ckanext.cioos_theme.helpers import recolored_eov_icon

    svg = recolored_eov_icon("currents.svg", "#e55162")
    assert "#e55162" in svg
    assert "#51A79A" not in svg.upper()
    assert "#FFFFFF" in svg.upper()


def test_bundled_eov_icons_use_only_the_recolorable_teal_and_white():
    # Recoloring replaces only EOV_ICON_TEAL_RE: a new shade synced from
    # cioos-commons would stay teal on every regional deployment.
    import re

    from ckanext.cioos_theme.helpers import bundled_eov_icons, recolored_eov_icon

    for icon in bundled_eov_icons():
        colors = set(re.findall(r"#[0-9a-f]{3,8}\b", recolored_eov_icon(icon, "#000000"), re.I))
        assert colors <= {"#000000", "#fff", "#FFF", "#ffffff", "#FFFFFF"}, icon


@pytest.mark.usefixtures("with_plugins")
@pytest.mark.ckan_config("ckan.cioos.primary_color", "#1b6ca8")
def test_eov_icon_url_and_view_serve_recolored_icon(app, test_request_context):
    from ckanext.cioos_theme.helpers import eov_icon_url

    with test_request_context():
        url = eov_icon_url({"icon": "currents.svg"})
        assert eov_icon_url({"icon": "icon-x.png"}).endswith(
            "/base/images/eov-icons-svg/icon-x.png"
        )
        assert eov_icon_url({"icon": "currents.svg", "image_display_url": "/x.png"}) == "/x.png"
    assert url.startswith("/eov-icon/currents.svg")

    response = app.get(url)
    assert response.headers["Content-Type"].startswith("image/svg+xml")
    assert "#1b6ca8" in response.body
    app.get("/eov-icon/..%2Fplugin.py", status=404)


@pytest.mark.usefixtures("with_plugins")
@pytest.mark.ckan_config("ckan.cioos.primary_color", "#1b6ca8")
def test_eov_icon_url_keeps_custom_base_path(test_request_context, monkeypatch):
    import ckan.plugins.toolkit as toolkit
    from ckanext.cioos_theme.helpers import eov_icon_url

    # Set after plugin load: envvars re-applies .env over ckan_config markers.
    monkeypatch.setitem(toolkit.config, "ckan.eov_icon_base_path", "/regional/icons/")
    with test_request_context():
        assert eov_icon_url({"icon": "currents.svg"}).endswith("/regional/icons/currents.svg")
