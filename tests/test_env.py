"""Numeric environment settings: a typo is logged and the default used, never a crash at start."""
import pytest

from floorbit.env import number


@pytest.mark.parametrize(('raw', 'kind', 'expected'), [
    (None, int, 6379), ('', int, 6379), ('  ', int, 6379), ('6380', int, 6380), (' 6380 ', int, 6380),
    ('abc', int, 6379), ('1.5', int, 6379), ('2.5', float, 2.5), ('soon', float, 6379),
    ('nan', float, 6379), ('inf', float, 6379),
])
def test_a_number_from_the_environment(monkeypatch, raw, kind, expected):
    if raw is None:
        monkeypatch.delenv('FLOORBIT_TEST_NUMBER', raising=False)
    else:
        monkeypatch.setenv('FLOORBIT_TEST_NUMBER', raw)
    assert number('FLOORBIT_TEST_NUMBER', 6379, kind=kind) == expected


def test_a_bad_value_names_the_variable_in_the_log(monkeypatch, capsys):
    monkeypatch.setenv('FLOORBIT_TEST_NUMBER', 'twelve')
    assert number('FLOORBIT_TEST_NUMBER', 12.0, kind=float) == 12.0
    assert "FLOORBIT_TEST_NUMBER='twelve' is not a number; using 12.0" in capsys.readouterr().out


def test_a_value_below_the_minimum_is_raised_to_it(monkeypatch):
    monkeypatch.setenv('FLOORBIT_TEST_NUMBER', '0')
    assert number('FLOORBIT_TEST_NUMBER', 12.0, kind=float, minimum=0.1) == 0.1

