import jogan


def test_package_exposes_version() -> None:
    assert isinstance(jogan.__version__, str)
    assert jogan.__version__
