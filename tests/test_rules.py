import pytest

from loyalty_app.loyalty.rules import RuleViolation, calculate_earn_points, redemption_value, validate_redeem_request


def test_calculate_earn_points_floor_rounding(settings):
    settings.loyalty_points_per_currency_unit = 0.01
    settings.loyalty_points_rounding = "floor"
    assert calculate_earn_points(1750, settings) == 17  # 17.5 -> floor -> 17


def test_calculate_earn_points_round_rounding(settings):
    settings.loyalty_points_per_currency_unit = 0.01
    settings.loyalty_points_rounding = "round"
    assert calculate_earn_points(1750, settings) == 18  # 17.5 -> round -> 18


def test_calculate_earn_points_ceil_rounding(settings):
    settings.loyalty_points_per_currency_unit = 0.01
    settings.loyalty_points_rounding = "ceil"
    assert calculate_earn_points(1701, settings) == 18  # 17.01 -> ceil -> 18


def test_calculate_earn_points_rejects_negative_amount(settings):
    with pytest.raises(RuleViolation):
        calculate_earn_points(-100, settings)


def test_calculate_earn_points_rejects_unsupported_mode(settings):
    settings.loyalty_points_rule_mode = "per_product"
    with pytest.raises(RuleViolation):
        calculate_earn_points(1000, settings)


def test_validate_redeem_below_minimum(settings):
    settings.loyalty_redemption_min_points = 10
    with pytest.raises(RuleViolation) as excinfo:
        validate_redeem_request(5, current_balance=100, settings=settings)
    assert excinfo.value.code == "below_minimum"


def test_validate_redeem_above_maximum(settings):
    settings.loyalty_redemption_max_points_per_tx = 100
    with pytest.raises(RuleViolation) as excinfo:
        validate_redeem_request(200, current_balance=1000, settings=settings)
    assert excinfo.value.code == "above_maximum"


def test_validate_redeem_insufficient_balance(settings):
    with pytest.raises(RuleViolation) as excinfo:
        validate_redeem_request(50, current_balance=20, settings=settings)
    assert excinfo.value.code == "insufficient_balance"


def test_validate_redeem_rejects_non_positive_points(settings):
    with pytest.raises(RuleViolation) as excinfo:
        validate_redeem_request(0, current_balance=100, settings=settings)
    assert excinfo.value.code == "invalid_points"


def test_validate_redeem_accepts_valid_request(settings):
    validate_redeem_request(50, current_balance=100, settings=settings)  # no raise


def test_redemption_value(settings):
    settings.loyalty_redemption_value_per_point = 2.5
    assert redemption_value(10, settings) == 25.0
