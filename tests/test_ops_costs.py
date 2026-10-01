"""Cost model: derived prices, break-even and the tag on every configured number (D-019)."""

import datetime as dt
import re
from pathlib import Path

import pytest

from jogan.ops import costs as pricing
from jogan.ops.config import load_ops_config
from jogan.ops.env import Episode
from jogan.ops.metrics import summarize
from jogan.ops.policies import STATUS_QUO
from jogan.sim.config import CONFIG_DIR

TAGS = ("SOURCE", "DERIVED", "ASSUMPTION")


@pytest.fixture(scope="module")
def costs():
    return load_ops_config().costs


def test_commission_rate_comes_from_tk_per_thousand(costs) -> None:
    rate = pricing.commission_rate(costs)
    for side, tk in costs.agent_commission_per_1000_tk.items():
        assert rate[side] == pytest.approx(tk / 1000)


def test_runner_time_is_priced_from_salary_and_legal_week(costs) -> None:
    low, high = costs.runner.salary_tk_per_month
    minutes = costs.runner.hours_per_week * 60 * 365.25 / 12 / 7
    assert pricing.labour_tk_per_minute(costs) == pytest.approx((low + high) / 2 / minutes)
    assert pricing.labour_tk_per_minute(costs, salary=low) < pricing.labour_tk_per_minute(costs)


def test_petrol_price_follows_the_official_dates(costs) -> None:
    table = costs.runner.petrol_tk_per_litre
    (first, p0), (second, p1) = table[0], table[1]
    day_before = second - dt.timedelta(days=1)
    prices = pricing.petrol_tk_per_litre(costs, [first, day_before, second])
    assert prices.tolist() == [p0, p0, p1]
    with pytest.raises(ValueError, match="no petrol price"):
        pricing.petrol_tk_per_litre(costs, [first - dt.timedelta(days=1)])
    per_km = pricing.fuel_tk_per_km(costs, [second], "rural")
    assert per_km[0] == pytest.approx(p1 / costs.runner.km_per_litre["rural"])


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((150.0, 10), (100.0, 20), {"value_tk": 5.0, "cheaper": "a above"}),
        ((100.0, 20), (150.0, 10), {"value_tk": 5.0, "cheaper": "a below"}),
        ((90.0, 10), (100.0, 20), {"value_tk": None, "cheaper": "a"}),
        ((110.0, 20), (100.0, 10), {"value_tk": None, "cheaper": "b"}),
        ((100.0, 10), (100.0, 10), {"value_tk": None, "cheaper": "equal"}),
    ],
)
def test_break_even_value_per_lost_customer(a, b, expected) -> None:
    assert pricing.break_even(*a, *b) == expected
    value = expected["value_tk"]
    if value is not None:  # at the break-even value both policies cost the same
        assert a[0] + value * a[1] == pytest.approx(b[0] + value * b[1])


def test_runner_cost_in_the_summary(tiny_episodes: dict[str, Episode], costs) -> None:
    s = summarize(tiny_episodes[STATUS_QUO])
    hours = s["operations"]["runner_busy_hours"]
    labour = hours * 60 * pricing.labour_tk_per_minute(costs)
    assert s["cost_tk"]["runner_time"] == pytest.approx(labour, rel=1e-3)
    petrol = [p for _, p in costs.runner.petrol_tk_per_litre]
    km_per_litre = costs.runner.km_per_litre.values()
    km = s["operations"]["runner_km"]
    low, high = min(petrol) / max(km_per_litre), max(petrol) / min(km_per_litre)
    assert km * low <= s["cost_tk"]["runner_fuel"] <= km * high
    assert "goodwill" not in s["cost_tk"]  # a lost customer's value is unknown (D-019)


def _untagged(path: Path) -> list[str]:
    """Lines holding a number with no tag on the line or in the comment block above it."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header_end = next(i for i, line in enumerate(lines) if not line.startswith("#"))
    bad, in_sources = [], False
    for i, line in enumerate(lines):
        code = line.split(" #", 1)[0]
        if not line.startswith(" "):
            in_sources = code.startswith("sources:")
        if line.lstrip().startswith("#") or in_sources or not re.search(r"\d", code):
            continue
        if any(tag in line for tag in TAGS):
            continue
        j = i - 1
        while j >= header_end and not lines[j].lstrip().startswith("#"):
            if not re.fullmatch(r"\s*(- .*|[\w]+:)", lines[j]):
                break  # a sibling setting with its own tag; the block above is not ours
            j -= 1
        block = []
        while j >= header_end and lines[j].lstrip().startswith("#"):
            block.append(lines[j])
            j -= 1
        if not any(tag in text for text in block for tag in TAGS):
            bad.append(f"{path.name}:{i + 1}: {line.strip()}")
    return bad


@pytest.mark.parametrize("name", ["costs", "env", "policies"])
def test_every_ops_number_is_tagged(name: str) -> None:
    assert _untagged(CONFIG_DIR / "ops" / f"{name}.yaml") == []


def test_tag_check_catches_an_untagged_number(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text(
        "# header: SOURCE DERIVED ASSUMPTION\n"
        "sources:\n  a: https://example.org/2026\n"
        "# block (SOURCE)\nlisted:\n  - [2026-01-01, 118]\n"
        "tagged: 3 # ASSUMPTION\n"
        "bare: 7\n",
        encoding="utf-8",
    )
    assert _untagged(path) == ["x.yaml:8: bare: 7"]
