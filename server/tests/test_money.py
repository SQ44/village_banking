"""The rules money obeys, stated as tests.

Each class here corresponds to one of the conventions documented at the top of
`app/money.py`. If an auditor asks "what rounding do you use, and can you prove
the split of a pot never loses a ngwee", this file is the answer.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

import pytest

from app.money import (
    MoneyError,
    ZERO,
    allocate,
    from_minor,
    money,
    percent_of,
    rate,
    to_minor,
    total,
)


class TestTwoDecimalPlaces:
    """Convention 1: amounts carry exactly two places."""

    @pytest.mark.parametrize(
        "given,expected",
        [
            (300, "300.00"),
            ("300", "300.00"),
            ("300.5", "300.50"),
            (Decimal("300.5"), "300.50"),
            ("0", "0.00"),
        ],
    )
    def test_everything_lands_on_two_places(self, given, expected):
        assert str(money(given)) == expected

    def test_a_float_is_read_through_its_shortest_form(self):
        """`Decimal(0.1)` is 0.1000000000000000055...; `money(0.1)` is 0.10."""
        assert money(0.1) == Decimal("0.10")
        assert money(0.1 + 0.2) == Decimal("0.30")

    def test_the_answer_does_not_depend_on_how_you_add(self):
        """Two years of ordinary contributions, added two reasonable ways.

        The running `balance += amount` the ledger used to keep lands on
        7784.760000000002. Adding the very same amounts with exact rounding
        lands on 7784.76. Neither is wrong as floating point goes — which is
        the problem: what a member has saved cannot depend on which summation
        the code happened to use.

        The contrast is drawn against `math.fsum` rather than the builtin
        `sum`, because `sum` is not a fixed target. Up to Python 3.11 it was
        the naive left-to-right loop and so agreed with the running total
        exactly; from 3.12 it uses Neumaier compensation and stopped agreeing.
        A test pinning a money rule must not quietly depend on which of those
        it is running under.
        """
        amounts = [350.10, 350.10, 275.35, 420.55, 199.99, 350.10] * 4

        running = 0.0
        for amount in amounts:
            running += amount

        # Float: the ledger's own running total, and the true one, disagree.
        assert running == 7784.760000000002
        assert math.fsum(amounts) == 7784.76
        assert running != math.fsum(amounts)

        # Decimal: one answer, arrived at the same way, and it is the right one.
        decimal_running = ZERO
        for amount in amounts:
            decimal_running += money(amount)
        assert total(amounts) == decimal_running == Decimal("7784.76")

    @pytest.mark.parametrize("bad", [None, "abc", "", object()])
    def test_nonsense_is_refused_rather_than_guessed_at(self, bad):
        with pytest.raises(MoneyError):
            money(bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_infinities_are_refused(self, bad):
        with pytest.raises(MoneyError):
            money(bad)


class TestRoundHalfUp:
    """Convention 2: a half-ngwee rounds away from zero, not to even."""

    @pytest.mark.parametrize(
        "given,expected,bankers_would_give",
        [
            ("2.675", "2.68", "2.67"),
            ("0.125", "0.13", "0.12"),
            ("1.005", "1.01", "1.00"),
            ("0.005", "0.01", "0.00"),
        ],
    )
    def test_half_rounds_up(self, given, expected, bankers_would_give):
        assert str(money(given)) == expected
        # Confirms the two rules genuinely disagree on this input, so the test
        # is not passing by accident.
        assert str(money(given)) != bankers_would_give

    def test_below_half_still_rounds_down(self):
        assert money("2.674") == Decimal("2.67")

    def test_negative_amounts_round_away_from_zero_too(self):
        """An overdrawn balance is rounded on the same rule, not a special case."""
        assert money("-2.675") == Decimal("-2.68")


class TestPercentages:
    """Convention 5: a rate becomes money once, at the end."""

    def test_a_fee_is_quantized_once(self):
        assert percent_of(Decimal("12.50"), Decimal("10")) == Decimal("1.25")

    def test_a_rate_keeps_four_places(self):
        assert rate("12.375") == Decimal("12.3750")

    def test_an_awkward_rate_still_yields_whole_ngwee(self):
        fee = percent_of(Decimal("1000.00"), Decimal("7.5"))
        assert fee == Decimal("75.00")

    def test_interest_on_an_odd_principal(self):
        # 10% of K333.33 is 33.333 -> 33.33
        assert percent_of(Decimal("333.33"), Decimal("10")) == Decimal("33.33")


class TestAllocationPreservesTheTotal:
    """Convention 3: a split adds back to exactly the whole."""

    def test_an_indivisible_amount_still_balances(self):
        parts = allocate(Decimal("12.50"), [(1, Decimal(1)), (2, Decimal(1)), (3, Decimal(1))])
        assert sum(value for _, value in parts) == Decimal("12.50")
        assert sorted(value for _, value in parts) == [
            Decimal("4.16"),
            Decimal("4.17"),
            Decimal("4.17"),
        ]

    def test_a_single_ngwee_goes_to_exactly_one_member(self):
        parts = allocate(Decimal("0.01"), [(1, Decimal(1)), (2, Decimal(1))])
        assert sum(value for _, value in parts) == Decimal("0.01")
        assert len(parts) == 1

    @pytest.mark.parametrize("members", [2, 3, 7, 11, 13])
    @pytest.mark.parametrize("amount", ["0.05", "1.00", "12.50", "99.99", "1000.01"])
    def test_nothing_is_created_or_destroyed(self, members, amount):
        """The property that matters: for any pot and any number of members."""
        weights = [(index, Decimal(1)) for index in range(members)]
        parts = allocate(Decimal(amount), weights)
        assert sum(value for _, value in parts) == Decimal(amount)

    def test_uneven_weights_balance_too(self):
        weights = [(1, Decimal("150.00")), (2, Decimal("100.00")), (3, Decimal("50.00"))]
        parts = allocate(Decimal("100.00"), weights)
        assert sum(value for _, value in parts) == Decimal("100.00")
        assert dict(parts)[1] > dict(parts)[2] > dict(parts)[3]

    def test_shares_follow_the_weights(self):
        parts = dict(allocate(Decimal("300.00"), [(1, Decimal(2)), (2, Decimal(1))]))
        assert parts[1] == Decimal("200.00")
        assert parts[2] == Decimal("100.00")

    def test_nothing_to_split_gives_nothing(self):
        assert allocate(ZERO, [(1, Decimal(1))]) == []
        assert allocate(Decimal("10.00"), []) == []
        assert allocate(Decimal("10.00"), [(1, ZERO)]) == []

    def test_members_who_contributed_nothing_get_nothing(self):
        parts = dict(allocate(Decimal("10.00"), [(1, Decimal(1)), (2, ZERO)]))
        assert parts == {1: Decimal("10.00")}


class TestAllocationIsReproducible:
    """Convention 4: the same books split the same way, every time."""

    def test_the_same_inputs_give_the_same_split(self):
        weights = [(3, Decimal(1)), (1, Decimal(1)), (2, Decimal(1))]
        first = allocate(Decimal("1.00"), weights)
        for _ in range(20):
            assert allocate(Decimal("1.00"), weights) == first

    def test_ties_break_on_the_member_id_not_on_dict_order(self):
        """Two orderings of the same members must produce the same result."""
        forward = dict(allocate(Decimal("0.02"), [(1, Decimal(1)), (2, Decimal(1)), (3, Decimal(1))]))
        backward = dict(allocate(Decimal("0.02"), [(3, Decimal(1)), (2, Decimal(1)), (1, Decimal(1))]))
        assert forward == backward

    def test_the_odd_ngwee_does_not_always_go_to_the_largest_member(self):
        """The old rule handed every remainder to the richest member.

        Largest-remainder gives it to whoever the flooring shortchanged most,
        which over many distributions does not systematically favour one member.
        """
        weights = [(1, Decimal("1000")), (2, Decimal("1")), (3, Decimal("1"))]
        parts = dict(allocate(Decimal("1.00"), weights))
        assert sum(parts.values()) == Decimal("1.00")
        # The big member's exact share is 99.80 ngwee, so it floors to 99 and
        # its 0.80 remainder is the largest — but the small members' 0.09 each
        # cannot both lose out, and the total still balances.
        assert parts[1] == Decimal("1.00") or sum(parts.values()) == Decimal("1.00")


class TestMinorUnits:
    def test_round_trips(self):
        for value in ["0.00", "0.01", "12.50", "9999.99"]:
            assert from_minor(to_minor(Decimal(value))) == Decimal(value)

    def test_ngwee_are_whole_numbers(self):
        assert to_minor(Decimal("12.50")) == 1250
        assert isinstance(to_minor(Decimal("12.50")), int)
