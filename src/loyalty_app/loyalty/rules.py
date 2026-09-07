from __future__ import annotations

import math

from loyalty_app.config import Settings


class RuleViolation(ValueError):
    """A business-rule check failed (not enough points, below minimum, etc.)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def calculate_earn_points(purchase_amount_gross: int, settings: Settings) -> int:
    """Authoritative points-for-a-purchase calculation. The server always recomputes
    this - a client-supplied pointsDelta is only ever a UI preview (see
    CLAUDE_CODE_UNAS_QR_MIDDLEWARE_SPEC.md, "Javasolt belso API").

    Only the amount-based mode is implemented in this phase, because product/SKU
    data is not available without a POS integration (explicitly deferred to phase
    2 by the spec). See docs/KNOWN_LIMITATIONS.md.
    """
    if settings.loyalty_points_rule_mode != "per_currency_unit":
        raise RuleViolation(
            "unsupported_rule_mode",
            f"Nem tamogatott pontszamitasi mod: {settings.loyalty_points_rule_mode}",
        )
    if purchase_amount_gross < 0:
        raise RuleViolation("invalid_amount", "A vasarlasi osszeg nem lehet negativ")

    raw_points = purchase_amount_gross * settings.loyalty_points_per_currency_unit
    return _round_points(raw_points, settings.loyalty_points_rounding)


def _round_points(value: float, mode: str) -> int:
    if mode == "ceil":
        return math.ceil(value)
    if mode == "round":
        return round(value)
    return math.floor(value)


def validate_redeem_request(
    points_to_redeem: int, current_balance: int, settings: Settings, *, purchase_amount_gross: int
) -> None:
    if points_to_redeem <= 0:
        raise RuleViolation("invalid_points", "A bevaltando pontnak pozitivnak kell lennie")
    if points_to_redeem < settings.loyalty_redemption_min_points:
        raise RuleViolation(
            "below_minimum",
            f"A bevaltas minimum {settings.loyalty_redemption_min_points} pont lehet",
        )
    max_per_tx = settings.loyalty_redemption_max_points_per_tx
    if max_per_tx and points_to_redeem > max_per_tx:
        raise RuleViolation(
            "above_maximum",
            f"A bevaltas maximum {max_per_tx} pont lehet tranzakciononkent",
        )
    max_percent = settings.loyalty_redemption_max_percent_of_order
    if max_percent:
        max_value = purchase_amount_gross * max_percent
        if redemption_value(points_to_redeem, settings) > max_value:
            raise RuleViolation(
                "above_order_percent_limit",
                f"A bevaltott pontok erteke nem haladhatja meg a rendeles vegosszegenek "
                f"{max_percent * 100:.0f}%-at",
            )
    if points_to_redeem > current_balance:
        raise RuleViolation("insufficient_balance", "Nincs eleg pont a bevaltashoz")


def redemption_value(points: int, settings: Settings) -> float:
    return points * settings.loyalty_redemption_value_per_point
