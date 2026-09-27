"""Tests for pyabf.project."""

import pytest

from pyabf import ProjectPlan, ValuationAssumptions


def _plan(**kw):
    args = dict(name="Roof", budget=1_000_000, duration_months=10,
                start_year=2026, start_month=11,
                improvement_fraction=0.25, yield_rate=0.04)
    args.update(kw)
    return ProjectPlan(**args)


class TestProjectPlan:
    def test_monthly_payment_is_linear(self):
        plan = _plan()
        schedule = plan.payment_schedule()
        assert len(schedule) == 10
        assert (schedule["payment"] == 100_000).all()
        assert schedule["payment"].sum() == pytest.approx(1_000_000)
        assert schedule["cumulative_paid"].iloc[-1] == pytest.approx(1_000_000)
        assert schedule["improvement"].sum() == pytest.approx(250_000)

    def test_schedule_wraps_years(self):
        schedule = _plan().payment_schedule()
        assert list(zip(schedule["year"], schedule["month"]))[:3] == [
            (2026, 11), (2026, 12), (2027, 1)]
        assert (schedule["year"].iloc[-1], schedule["month"].iloc[-1]) == (2027, 8)

    def test_end_year_and_month(self):
        plan = _plan()
        assert (plan.end_year, plan.end_month) == (2027, 8)
        plan = _plan(start_month=1, duration_months=12)
        assert (plan.end_year, plan.end_month) == (2026, 12)
        plan = _plan(start_month=12, duration_months=1)
        assert (plan.end_year, plan.end_month) == (2026, 12)

    def test_annual_payments(self):
        annual = _plan().annual_payments()
        assert list(annual.index) == [2026, 2027]
        assert list(annual["months"]) == [2, 8]
        assert list(annual["payment"]) == pytest.approx([200_000, 800_000])
        assert list(annual["improvement"]) == pytest.approx([50_000, 200_000])

    def test_improvement_allowances(self):
        allowances = _plan().improvement_allowances()
        assert [(a.year, a.cost) for a in allowances] == [
            (2026, pytest.approx(200_000)), (2027, pytest.approx(800_000))]
        assert all(a.improvement_fraction == 0.25 for a in allowances)
        assert sum(a.annual_allowance for a in allowances) == pytest.approx(
            1_000_000 * 0.25 * 0.04)

    def test_add_to_valuation_appends(self):
        assumptions = ValuationAssumptions()
        _plan().add_to_valuation(assumptions)
        _plan(name="Windows").add_to_valuation(assumptions)
        assert len(assumptions.improvements) == 4
        assert assumptions.total_improvement_allowance == pytest.approx(2 * 10_000)

    @pytest.mark.parametrize("kw", [
        {"duration_months": 0},
        {"budget": -1},
        {"start_month": 13},
        {"improvement_fraction": 1.5},
    ])
    def test_invalid_inputs(self, kw):
        with pytest.raises(ValueError):
            _plan(**kw)
