"""Validators referenced by the CIOOS scheming schema."""

import ckan.lib.navl.dictization_functions as df
import pytest

from ckanext.cioos import validators


@pytest.fixture
def name_validator():
    return validators.cioos_name_validator({}, {})


@pytest.fixture
def tag_validator():
    return validators.cioos_tag_name_validator({}, {})


@pytest.fixture
def range_validator():
    return validators.cioos_is_valid_range({}, {})


@pytest.mark.usefixtures("with_request_context")
class TestNameValidator:
    @pytest.mark.parametrize("value", ["ab", "a-dataset_01", "x" * 255])
    def test_accepts(self, name_validator, value):
        assert name_validator(value, {}) == value

    @pytest.mark.parametrize(
        "value",
        ["a", "new", "edit", "search", "Upper", "with space", "accént", "x" * 256, 42],
    )
    def test_rejects(self, name_validator, value):
        with pytest.raises(df.Invalid):
            name_validator(value, {})


@pytest.mark.usefixtures("with_request_context")
class TestTagNameValidator:
    @pytest.mark.parametrize(
        "value",
        ["sea surface temperature", "Température", "O2 (dissolved)", "a/b; c, d.e-f"],
    )
    def test_accepts(self, tag_validator, value):
        assert tag_validator(value, {}) == value

    @pytest.mark.parametrize("value", ["tag!", "50%", "a#b", "<script>"])
    def test_rejects(self, tag_validator, value):
        with pytest.raises(df.Invalid):
            tag_validator(value, {})


@pytest.mark.usefixtures("with_request_context")
class TestRangeValidator:
    @pytest.mark.parametrize(
        "value",
        [
            '{"begin": "2020-01-01", "end": "2021-01-01"}',
            '{"begin": "2020-01-01"}',
            '{"begin": "2020-01-01", "end": "2020-01-01"}',
            "{}",
        ],
    )
    def test_accepts(self, range_validator, value):
        assert range_validator(value, {}) == value

    @pytest.mark.parametrize(
        "value",
        ['{"end": "2021-01-01"}', '{"begin": "2021-01-01", "end": "2020-01-01"}'],
    )
    def test_rejects(self, range_validator, value):
        with pytest.raises(df.Invalid):
            range_validator(value, {})
