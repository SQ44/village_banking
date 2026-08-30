"""Money, and the rules it obeys.

Every amount in this system is a `Decimal` carrying exactly two decimal places,
because the kwacha's minor unit is the ngwee and there is no such thing as half
of one. Nothing here uses `float`: a balance built by adding floats drifts away
from the entries behind it, and a check that cannot use `==` cannot prove a
member's savings are right.

The conventions below are the ordinary ones for currency handling, stated
explicitly so an auditor can see which rule was chosen rather than inferring it
from behaviour:

1.  **Two decimal places.** Amounts are quantized to 0.01 on the way in and
    stored as `NUMERIC(12, 2)`. Twelve digits leaves room for a pot of
    K9,999,999,999.99, far past anything a village bank will hold.

2.  **Round half up.** A half-ngwee rounds away from zero: 2.675 becomes 2.68.
    This is the convention for currency. Python's built-in `round` does *not*
    do this — it rounds half to even (2.675 becomes 2.67), which is right for
    statistics and wrong for money, and was the rule this codebase applied
    before without anyone choosing it.

3.  **Splits preserve the total.** Dividing a sum between members uses the
    largest-remainder method: give everyone their whole ngwee, then hand the
    leftover ngwee one at a time to whoever was cheated by the most. The parts
    always add back to exactly the whole — no ngwee is invented or lost.

4.  **Splits are reproducible.** Ties in that distribution break on the
    recipient's id, so the same inputs always produce the same split. Running
    the books again a year later gives the same answer.

5.  **Rates are not amounts.** A percentage is held to four decimal places and
    only becomes money when it is applied to an amount, at which point the
    result is quantized once, half up.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any, Iterable, Sequence, TypeVar

# The kwacha's minor unit. ZMW is the only currency this app accepts, and the
# check that enforces that lives in the transactions router.
CURRENCY_EXPONENT = Decimal("0.01")
MINOR_UNITS_PER_MAJOR = 100

# Percentages keep more places than money: a rate of 12.375% is meaningful, a
# payment of K12.375 is not.
RATE_EXPONENT = Decimal("0.0001")

ZERO = Decimal("0.00")

# Column widths, used by the models so the precision is declared in one place.
MONEY_PRECISION, MONEY_SCALE = 12, 2
RATE_PRECISION, RATE_SCALE = 9, 4

K = TypeVar("K")


class MoneyError(ValueError):
    """An amount that cannot be read as money."""


def money(value: Any) -> Decimal:
    """Read any sane representation of an amount as a 2dp Decimal, rounding half up.

    A `float` is converted through its shortest repr rather than directly:
    `Decimal(0.1)` is 0.1000000000000000055511151231257827, while
    `Decimal(str(0.1))` is exactly 0.1. Floats still arrive from JSON payloads
    and from a legacy database, so this is the boundary where they stop.
    """
    if value is None:
        raise MoneyError("amount_required")
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, int):
        candidate = Decimal(value)
    elif isinstance(value, float):
        candidate = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            candidate = Decimal(value.strip())
        except Exception as exc:
            raise MoneyError(f"not_an_amount: {value!r}") from exc
    else:
        raise MoneyError(f"not_an_amount: {value!r}")

    if not candidate.is_finite():
        raise MoneyError("amount_must_be_finite")
    return candidate.quantize(CURRENCY_EXPONENT, rounding=ROUND_HALF_UP)


def rate(value: Any) -> Decimal:
    """Read a percentage, kept to four places."""
    if value is None:
        raise MoneyError("rate_required")
    if isinstance(value, float):
        candidate = Decimal(repr(value))
    elif isinstance(value, Decimal):
        candidate = value
    else:
        candidate = Decimal(str(value))
    if not candidate.is_finite():
        raise MoneyError("rate_must_be_finite")
    return candidate.quantize(RATE_EXPONENT, rounding=ROUND_HALF_UP)


def percent_of(amount: Decimal, percent: Decimal) -> Decimal:
    """Apply a percentage to an amount, quantizing once at the end.

    Quantizing once matters: rounding the intermediate would compound the error
    across a schedule of installments.
    """
    with localcontext() as ctx:
        # Room for the full product before it is quantized back to a ngwee.
        ctx.prec = 28
        raw = Decimal(amount) * Decimal(percent) / Decimal(100)
    return raw.quantize(CURRENCY_EXPONENT, rounding=ROUND_HALF_UP)


def to_minor(amount: Decimal) -> int:
    """Ngwee as a whole number. Exact integer arithmetic, for splitting."""
    return int(money(amount) * MINOR_UNITS_PER_MAJOR)


def from_minor(minor: int) -> Decimal:
    return (Decimal(minor) / MINOR_UNITS_PER_MAJOR).quantize(CURRENCY_EXPONENT)


def allocate(total: Decimal, weights: Sequence[tuple[K, Decimal]]) -> list[tuple[K, Decimal]]:
    """Split `total` in proportion to `weights`, losing nothing.

    The largest-remainder method, computed in whole ngwee so there is no
    rounding to argue about:

    * everyone gets the whole ngwee their share entitles them to;
    * the ngwee left over — never more than one per recipient — go to whoever
      the flooring shortchanged by the most;
    * ties break on the recipient's key, so the same books split the same way
      every time they are run.

    The returned amounts always sum to exactly `total`. Recipients allocated
    nothing are omitted, since a zero-value transaction is not a movement.
    """
    total = money(total)
    if total <= ZERO:
        return []

    positive = [(key, Decimal(weight)) for key, weight in weights if Decimal(weight) > 0]
    total_weight = sum((weight for _, weight in positive), Decimal(0))
    if not positive or total_weight <= 0:
        return []

    minor_total = to_minor(total)

    # Exact rational share of the pot, in ngwee, before anyone is rounded.
    shares: list[tuple[K, int, Decimal]] = []
    with localcontext() as ctx:
        ctx.prec = 28
        for key, weight in positive:
            exact = (Decimal(minor_total) * weight) / total_weight
            whole = int(exact)  # Truncates: nobody is given a ngwee they have not earned.
            shares.append((key, whole, exact - whole))

    leftover = minor_total - sum(whole for _, whole, _ in shares)

    # Biggest shortfall first; the key breaks ties so the result is reproducible.
    order = sorted(range(len(shares)), key=lambda i: (-shares[i][2], _sort_key(shares[i][0])))
    allocated = [whole for _, whole, _ in shares]
    for position in range(leftover):
        allocated[order[position % len(order)]] += 1

    return [
        (key, from_minor(amount))
        for (key, _, _), amount in zip(shares, allocated)
        if amount > 0
    ]


def _sort_key(key: Any) -> Any:
    """Order keys of mixed type without raising — ints sort before strings."""
    if isinstance(key, (int, float, Decimal)):
        return (0, Decimal(key), "")
    return (1, Decimal(0), str(key))


def total(amounts: Iterable[Decimal]) -> Decimal:
    """Sum amounts exactly. `sum()` on an empty iterable gives int 0, not money."""
    running = ZERO
    for amount in amounts:
        running += money(amount)
    return running
