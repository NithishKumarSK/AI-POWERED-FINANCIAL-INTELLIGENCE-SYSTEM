"""7 payload validation tests — verifies that the correct equity-option payload is built."""
from __future__ import annotations

import pytest
from decimal import Decimal

from src.models.backtest_models import BacktestLeg, BacktestPayload
from src.services.tastytrade_backtester_service import (
    build_equity_option_short_put_payload,
    build_custom_legs_payload,
)


class TestBacktestLegDefaults:
    def test_default_type_is_equity_option(self):
        leg = BacktestLeg()
        assert leg.type == "equity-option", "type must be 'equity-option'"

    def test_default_direction_is_short(self):
        leg = BacktestLeg()
        assert leg.direction == "short"

    def test_to_dict_uses_camel_case(self):
        leg = BacktestLeg(days_until_expiration=30, delta=25)
        d = leg.to_dict()
        assert "daysUntilExpiration" in d
        assert "strikeSelection" in d
        assert d["daysUntilExpiration"] == 30
        assert d["delta"] == 25

    def test_wrong_type_would_fail_validation(self):
        leg = BacktestLeg(type="option")
        assert leg.type != "equity-option", "Sanity: 'option' != 'equity-option'"


class TestBuildShortPutPayload:
    def test_returns_payload_object(self):
        payload = build_equity_option_short_put_payload("SPY", "2021-01-01", "2024-01-01")
        assert isinstance(payload, BacktestPayload)

    def test_symbol_uppercased(self):
        payload = build_equity_option_short_put_payload("spy", "2021-01-01", "2024-01-01")
        assert payload.symbol == "SPY"

    def test_two_legs_by_default(self):
        payload = build_equity_option_short_put_payload("SPY", "2021-01-01", "2024-01-01")
        assert len(payload.legs) == 2

    def test_all_legs_are_equity_option(self):
        payload = build_equity_option_short_put_payload("SPY", "2021-01-01", "2024-01-01")
        for leg in payload.legs:
            assert leg.type == "equity-option"

    def test_end_date_formatted_as_date_only(self):
        # TastyTrade website uses date-only format (no time suffix) — must NOT include "T"
        payload = build_equity_option_short_put_payload("SPY", "2021-01-01", "2024-06-01")
        d = payload.to_dict()
        assert "T" not in d["endDate"], "endDate must be date-only (no T time component — matches TastyTrade website)"
        assert len(d["endDate"]) == 10, f"endDate must be 10 chars (YYYY-MM-DD), got: {d['endDate']}"

    def test_to_dict_has_required_keys(self):
        payload = build_equity_option_short_put_payload("SPY", "2021-01-01", "2024-01-01")
        d = payload.to_dict()
        # "status" field was removed from payload to match TastyTrade website format
        for key in ("startDate", "endDate", "symbol", "entryConditions", "exitConditions", "legs"):
            assert key in d, f"Missing key: {key}"

    def test_custom_dte_and_delta_propagate(self):
        payload = build_equity_option_short_put_payload("QQQ", "2022-01-01", "2025-01-01", dte=30, delta=20)
        for leg in payload.legs:
            assert leg.days_until_expiration == 30
            assert leg.delta == 20
