"""Numbers in the README and docs are an up-to-date copy of the evaluation artifacts."""

import pytest

from jogan.eval.docs import BLOCK, RENDERERS, files, fill, load


def test_every_numbers_block_matches_the_artifacts() -> None:
    s = load()
    for path in files():
        text = path.read_text()
        assert fill(text, s) == text, f"{path.name} is stale: run `make docs`"


def test_the_readme_carries_the_headline_blocks() -> None:
    readme = files()[0].read_text()
    names = {m["name"] for m in BLOCK.finditer(readme)}
    assert {"headline", "limits", "stress", "runtime"} <= names


def test_an_unknown_block_is_refused() -> None:
    with pytest.raises(KeyError, match="unknown numbers block"):
        fill("<!-- numbers:nope -->\n<!-- /numbers -->", load())


def test_every_renderer_writes_text_without_blocks_of_its_own() -> None:
    s = load()
    for name, render in RENDERERS.items():
        out = render(s)
        assert out.strip(), name
        assert "<!-- numbers" not in out, name


def test_every_renderer_is_used_in_some_file() -> None:
    used = {m["name"] for path in files() for m in BLOCK.finditer(path.read_text())}
    assert set(RENDERERS) <= used, sorted(set(RENDERERS) - used)
