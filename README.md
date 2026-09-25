# pyABF

Tools for computing and modelling the finances of a Danish housing
cooperative (*andelsboligforening*, ABF): units and share values, mortgage
loans, budgets vs. actuals, land tax (*grundskyld*) and a DCF property
valuation (*valuarvurdering*).

The package is generic. Everything specific to one cooperative (units,
loans, chart of accounts, valuation assumptions) is passed in by the caller.

## Installation

Requires Python 3.12+.

```bash
pip install -e ".[dev]"
```

Run the tests (including the examples in this README):

```bash
pytest
```

## Modules

| Module | Contents |
| --- | --- |
| `pyabf.cooperative` | `HousingCooperative`: the main entry point that ties everything together |
| `pyabf.units` | `Unit`, `CooperativeUnit`, `CommercialUnit`, `Improvement` |
| `pyabf.loan` | `Loan`: annuity loans with interest-only periods, contribution rate and bond price |
| `pyabf.accounting` | `AccountEntry`, `AnnualReport`, `DEFAULT_NOTES` |
| `pyabf.budget` | `Budget`, `BudgetTracker`, `AccountMapping`, balance-sheet CSV import |
| `pyabf.tax` | `compute_property_tax`: grundskyld under the 2024+ transition rules |
| `pyabf.valuation` | `ValuationAssumptions`, `DCFModel`, `run_sensitivity`, `ValuationReport` |
| `pyabf.ois` | `OISClient`, `fetch_units`, `fetch_floors`: load a property's BBR units and floors (basements, roof floors) from OIS.dk by BFE number |

All amounts are in DKK. Rates are fractions (`0.02` = 2 %).

## Quick start

### The cooperative, units and share price

```python
>>> from pyabf import HousingCooperative, CooperativeUnit, CommercialUnit, Loan
>>> coop = HousingCooperative(
...     name="A/B Example",
...     units=[
...         CooperativeUnit("Street 1, st. tv.", area=60, rooms=2),
...         CooperativeUnit("Street 1, st. th.", area=80, rooms=3),
...         CommercialUnit("Street 1, kld.", area=100, rooms=1,
...                        is_rental=True, fixed_rent=120_000),
...     ],
...     owned_rate_per_sqm=650,      # boligafgift, DKK/m²/year
...     loans=[Loan("Loan 1", principal=5_000_000, interest_rate=0.02,
...                 term_years=30, bond_price=90)],
... )
>>> coop.total_annual_income
211000
>>> round(coop.compute_and_update_shares(property_value=10_000_000))
39286

```

### Loading units from OIS.dk

Given the BFE numbers of the cooperative's properties, the units (area,
rooms, bathrooms, address) can be fetched from BBR via OIS.dk. Housing
units become `CooperativeUnit`, everything else `CommercialUnit`. BBR does
not say which units the cooperative lets out, so all units start as
owner-occupied.

```python
coop = HousingCooperative.from_ois("A/B Example", bfe_numbers=[6018310],
                                   owned_rate_per_sqm=650)
# or, on an existing cooperative:
coop.add_units_from_ois([6018310])

# Basements and roof floors are not units in BBR; fetch them separately
from pyabf import fetch_floors
basements = [f for f in fetch_floors([6018310]) if f.kind == "basement"]
```

### Loans

```python
>>> loan = Loan("Loan 2", principal=1_000_000, interest_rate=0.03,
...             contribution_rate=0.005, term_years=20, payments_per_year=4)
>>> round(loan.balance_after_years(10))
586248
>>> list(loan.annual_schedule().columns)
['loan', 'year', 'interest', 'principal_payment', 'total_payment', 'closing_balance', 'market_value']

```

### Budget vs. actuals

Amounts follow the bookkeeping sign convention: expenses positive, income
negative. The mapping from account numbers to budget lines is up to you.

```python
>>> import io
>>> from pyabf import (Budget, BudgetCategory, BudgetLineItem, CategoryType,
...                    AccountMapping, BudgetTracker, load_balance_sheet_csv)
>>> budget = Budget(fiscal_year="2025/2026", rent_amount=1_000_000)
>>> income = BudgetCategory("income", "Indtægter", CategoryType.INCOME)
>>> income.add_item(BudgetLineItem("rent", "Boligafgift", budgeted=-1_000_000))
>>> ops = BudgetCategory("ops", "Driftsudgifter", CategoryType.EXPENSE)
>>> ops.add_item(BudgetLineItem("insurance", "Forsikringer", budgeted=200_000))
>>> budget.add_category(income); budget.add_category(ops)
>>> mapping = AccountMapping({"11310": "rent", "13100": "insurance"})
>>> csv_text = (
...     "Fin.;Konto;Tekst;D/S;Bem.;Bev. per.;Saldo pr.;Budget året\n"
...     "1;11310;Boligafgift;;;0,00;-500.000,00;-1.000.000,00\n"
...     "1;13100;Forsikringer;;;0,00;110.000,00;200.000,00\n"
... )
>>> tracker = BudgetTracker(budget, mapping)
>>> tracker.update_actuals(load_balance_sheet_csv(io.StringIO(csv_text)))
{}
>>> budget.find_item("insurance").utilisation
0.55
>>> nxt = tracker.suggest_next_year_budget(months_elapsed=6, inflation_rate=0.02)
>>> nxt.fiscal_year, nxt.find_item("insurance").budgeted
('2026/2027', 224500)

```

### Land tax (grundskyld)

```python
>>> from pyabf import compute_property_tax
>>> tax, increase = compute_property_tax(
...     new_property_value=20_000_000, old_property_value=200_000,
...     tax_rate=0.026, tax_year=2026)
>>> round(tax), round(increase)
(245120, 19760)

```

The rule parameters (first year 2024, 2.8 % first-year increase, 4.75 %
annual cap, 20 % discount) are keyword arguments you can override.

### DCF valuation

```python
>>> from pyabf.valuation import (
...     ValuationAssumptions, PropertyDescription, RentAssumptions,
...     ModernizationPlan, OperatingCostAssumptions, EconomicAssumptions,
...     DCFModel, run_sensitivity,
... )
>>> assumptions = ValuationAssumptions(
...     property_desc=PropertyDescription(total_building_area=5_000,
...                                       residential_area=4_500),
...     rent=RentAssumptions(base_rent_per_sqm=800,
...                          modernized_rent_per_sqm=1_400,
...                          total_base_residential_rent=3_600_000),
...     modernization=ModernizationPlan(total_area_sqm=4_500,
...                                     cost_per_sqm=15_000,
...                                     duration_years=15),
...     operating=OperatingCostAssumptions(total_operating_cost=1_200_000),
...     economic=EconomicAssumptions(inflation_rate=0.02,
...                                  required_real_return=0.0325),
... )
>>> result = DCFModel(assumptions).compute()
>>> result.total_value_rounded > 0
True
>>> grid = run_sensitivity(assumptions)  # required return × rent level
>>> grid.to_dataframe().shape
(7, 5)

```

`ValuationReport(result, assumptions).to_text()` renders a full text report
with the assumptions, NPV breakdown, cash-flow table and sensitivity grid.

## License

MIT. See [LICENSE](LICENSE).
