"""Sanity check that the package imports and the test harness is wired correctly."""

import alpha_squad


def test_package_importable():
    assert alpha_squad.__version__
