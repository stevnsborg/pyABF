"""
monte_carlo.py — Monte Carlo simulation of the DCF valuation.

Each selected input parameter is drawn independently from a normal
distribution centred on its base-case value, the DCF model is re-run for
every draw, and the resulting distribution of property values is
returned.

Default spread (one standard deviation):

    - Amounts (DKK, DKK/m², m², ...): 2.5 % of the base value
    - Rates / percentages (``*_rate``, ``*_return``, ``*_pct``,
      ``*_fraction``): 0.25 percentage points absolute (``0.0025``)

Parameters are addressed by their dotted path inside
:class:`~pyabf.valuation.ValuationAssumptions`, e.g.
``"economic.required_real_return"`` or ``"rent.modernized_rent_per_sqm"``.

Example:
    >>> from pyabf.valuation import run_monte_carlo
    >>> mc = run_monte_carlo(assumptions, n_samples=1000, seed=1)
    >>> mc.summary()                      # mean, std, percentiles
    >>> mc.samples                        # one row per draw (DataFrame)

Contains:
    ParameterDistribution — A normally distributed input parameter
    MonteCarloResult      — The sampled inputs and outputs
    run_monte_carlo       — Run the simulation
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from .assumptions import ValuationAssumptions
from .dcf_model import DCFModel

DEFAULT_N_SAMPLES = 1000
DEFAULT_REL_STD = 0.025        # 2.5 % of the nominal value
DEFAULT_RATE_ABS_STD = 0.0025  # 0.25 percentage points

#: Field-name suffixes that mark a parameter as a rate/percentage.
RATE_SUFFIXES = ("_rate", "_return", "_pct", "_fraction")

#: Parameters varied when none are selected explicitly.
DEFAULT_PARAMETERS = (
    "economic.required_real_return",
    "economic.inflation_rate",
    "rent.modernized_rent_per_sqm",
    "rent.total_base_residential_rent",
    "rent.total_commercial_rent",
    "modernization.cost_per_sqm",
    "operating.total_operating_cost",
)

#: Output columns added to ``MonteCarloResult.samples`` by the DCF model.
VALUATION_OUTPUTS = (
    "pv_budget_period",
    "pv_terminal_value",
    "terminal_noi",
    "total_value",
)


def is_rate_parameter(path: str) -> bool:
    """True if the parameter at ``path`` is a rate (by its field name)."""
    return path.rsplit(".", 1)[-1].endswith(RATE_SUFFIXES)


def set_parameter(obj: Any, path: str, value: float) -> None:
    """Set the value at a dotted attribute path (in place)."""
    *parents, name = path.split(".")
    for part in parents:
        obj = getattr(obj, part)
    if not hasattr(obj, name):
        raise AttributeError(f"Unknown parameter '{path}'.")
    setattr(obj, name, value)


def _base_value(assumptions: ValuationAssumptions, path: str) -> float:
    """Base-case value of a parameter in ``assumptions``."""
    if path == "operating.total_operating_cost":
        # Resolves the breakdown when no explicit total is set.
        return float(assumptions.total_operating_cost)
    *parents, name = path.split(".")
    obj: Any = assumptions
    for part in parents:
        obj = getattr(obj, part)
    if not hasattr(obj, name):
        raise AttributeError(f"Unknown parameter '{path}'.")
    return float(getattr(obj, name))


@dataclass(frozen=True)
class ParameterDistribution:
    """A normally distributed input parameter.

    Attributes:
        path: Dotted path of the parameter, e.g.
            ``"economic.required_real_return"``.
        mean: Mean of the distribution.  ``None`` uses the base-case value.
        std: Standard deviation, in the parameter's own units.  ``None``
            uses the default: ``rel_std`` × |mean| for amounts,
            ``rate_abs_std`` for rates.
        is_rate: Whether the parameter is a rate/percentage.  ``None``
            infers it from the field name (see :data:`RATE_SUFFIXES`).
    """

    path: str
    mean: float | None = None
    std: float | None = None
    is_rate: bool | None = None

    def resolve(
        self,
        base_value: float,
        rel_std: float = DEFAULT_REL_STD,
        rate_abs_std: float = DEFAULT_RATE_ABS_STD,
    ) -> ParameterDistribution:
        """Return a copy with ``mean``, ``std`` and ``is_rate`` filled in.

        Args:
            base_value: The parameter's base-case value.
            rel_std: Relative std for amounts (fraction of the mean).
            rate_abs_std: Absolute std for rates.
        """
        is_rate = (
            is_rate_parameter(self.path) if self.is_rate is None else self.is_rate
        )
        mean = base_value if self.mean is None else self.mean
        if self.std is not None:
            std = self.std
        elif is_rate:
            std = rate_abs_std
        else:
            std = rel_std * abs(mean)
        if std < 0:
            raise ValueError(f"std for '{self.path}' must be >= 0.")
        return replace(self, mean=float(mean), std=float(std), is_rate=is_rate)


ParameterSpec = (
    str
    | ParameterDistribution
    | Iterable[str | ParameterDistribution]
    | Mapping[str, float | None]
)


def normalize_parameters(
    parameters: ParameterSpec | None,
) -> list[ParameterDistribution]:
    """Turn the accepted ``parameters`` forms into ParameterDistributions.

    Accepts ``None`` (the :data:`DEFAULT_PARAMETERS`), a single path, a
    list of paths and/or ``ParameterDistribution`` objects, or a mapping
    ``{path: std}`` (``None`` std = default).
    """
    if parameters is None:
        parameters = DEFAULT_PARAMETERS
    if isinstance(parameters, (str, ParameterDistribution)):
        parameters = [parameters]
    if isinstance(parameters, Mapping):
        dists = [ParameterDistribution(path, std=std)
                 for path, std in parameters.items()]
    else:
        dists = [
            p if isinstance(p, ParameterDistribution) else ParameterDistribution(p)
            for p in parameters
        ]
    paths = [d.path for d in dists]
    if len(set(paths)) != len(paths):
        raise ValueError("Each parameter may only be selected once.")
    return dists


def draw_samples(
    distributions: list[ParameterDistribution],
    n_samples: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Draw ``n_samples`` independent normal samples per parameter.

    ``distributions`` must be resolved (mean and std set).
    """
    if n_samples <= 0:
        raise ValueError("n_samples must be positive.")
    means = np.array([d.mean for d in distributions], dtype=float)
    stds = np.array([d.std for d in distributions], dtype=float)
    draws = rng.normal(means, stds, size=(n_samples, len(distributions)))
    return pd.DataFrame(draws, columns=[d.path for d in distributions])


@dataclass(frozen=True)
class MonteCarloResult:
    """Result of a Monte Carlo valuation.

    Attributes:
        parameters: The resolved parameter distributions (mean/std set).
        samples: One row per draw: the sampled parameters followed by the
            output columns (``total_value``, ``pv_budget_period``, ...
            and, when run through a cooperative, ``debt_market_value``,
            ``equity`` and ``share_price``).
        base_values: The outputs of the un-perturbed base case,
            keyed like the output columns.
        n_samples: Number of draws.
        seed: The seed used, if one was given.
    """

    parameters: tuple[ParameterDistribution, ...]
    samples: pd.DataFrame
    base_values: dict[str, float]
    n_samples: int
    seed: int | None = None

    @property
    def parameter_names(self) -> list[str]:
        """Column names of the sampled input parameters."""
        return [p.path for p in self.parameters]

    @property
    def output_names(self) -> list[str]:
        """Column names of the model outputs."""
        return [c for c in self.samples.columns if c not in self.parameter_names]

    @property
    def values(self) -> np.ndarray:
        """Sampled total property values (DKK)."""
        return self.samples["total_value"].to_numpy()

    @property
    def base_value(self) -> float:
        """Total property value of the base case (DKK)."""
        return self.base_values["total_value"]

    def quantile(self, q: float | Iterable[float], output: str = "total_value"):
        """Quantile(s) of an output, ``q`` in [0, 1]."""
        return self.samples[output].quantile(q)

    def probability_below(self, threshold: float,
                          output: str = "total_value") -> float:
        """Share of draws where ``output`` is below ``threshold``."""
        return float((self.samples[output] < threshold).mean())

    def summary(
        self,
        outputs: Iterable[str] | None = None,
        percentiles: Iterable[float] = (0.05, 0.25, 0.5, 0.75, 0.95),
    ) -> pd.DataFrame:
        """Summary statistics per output.

        Args:
            outputs: Output columns to summarise.  Defaults to all.
            percentiles: Percentiles to include, as fractions.

        Returns:
            DataFrame with one row per output and columns ``base``,
            ``mean``, ``std``, ``cv`` (std / mean) and the percentiles
            (``p5``, ``p50``, ...).
        """
        outputs = list(self.output_names if outputs is None else outputs)
        percentiles = list(percentiles)
        rows = {}
        for name in outputs:
            col = self.samples[name]
            mean = float(col.mean())
            std = float(col.std())
            row = {
                "base": self.base_values.get(name, np.nan),
                "mean": mean,
                "std": std,
                "cv": std / mean if mean else np.nan,
            }
            for p in percentiles:
                row[f"p{p * 100:g}"] = float(col.quantile(p))
            rows[name] = row
        return pd.DataFrame.from_dict(rows, orient="index")

    def parameter_table(self) -> pd.DataFrame:
        """The input distributions (mean, std, is_rate) as a DataFrame."""
        return pd.DataFrame(
            [{"parameter": p.path, "mean": p.mean, "std": p.std,
              "is_rate": p.is_rate} for p in self.parameters]
        ).set_index("parameter")

    def sensitivity(self, output: str = "total_value") -> pd.DataFrame:
        """How much of the output's spread each input explains.

        Columns:
            correlation: Pearson correlation between input and output.
            std_coefficient: Standardised regression coefficient (the
                change in output, in output stds, per input std).
            contribution: Approximate share of the output variance
                explained by the input (``std_coefficient²`` normalised
                to sum to 1).  Meaningful because inputs are sampled
                independently.

        Rows are sorted by absolute ``std_coefficient`` (largest first),
        ready for a tornado chart.  Parameters with zero spread are left
        out.
        """
        y = self.samples[output].to_numpy()
        names = [p.path for p in self.parameters if p.std > 0]
        if not names or y.std() == 0:
            return pd.DataFrame(
                columns=["correlation", "std_coefficient", "contribution"])
        X = self.samples[names].to_numpy()
        Xs = (X - X.mean(axis=0)) / X.std(axis=0)
        ys = (y - y.mean()) / y.std()
        design = np.column_stack([np.ones(len(ys)), Xs])
        beta = np.linalg.lstsq(design, ys, rcond=None)[0][1:]
        corr = np.array([np.corrcoef(X[:, i], y)[0, 1] for i in range(len(names))])
        contribution = beta**2 / np.sum(beta**2)
        df = pd.DataFrame(
            {"correlation": corr, "std_coefficient": beta,
             "contribution": contribution},
            index=pd.Index(names, name="parameter"),
        )
        return df.reindex(df["std_coefficient"].abs().sort_values(
            ascending=False).index)


def _valuation_outputs(assumptions: ValuationAssumptions) -> dict[str, float]:
    result = DCFModel(assumptions).compute()
    return {name: float(getattr(result, name)) for name in VALUATION_OUTPUTS}


def resolve_parameters(
    assumptions: ValuationAssumptions,
    parameters: ParameterSpec | None = None,
    rel_std: float = DEFAULT_REL_STD,
    rate_abs_std: float = DEFAULT_RATE_ABS_STD,
) -> list[ParameterDistribution]:
    """Normalise ``parameters`` and fill in mean/std from ``assumptions``."""
    return [
        d.resolve(_base_value(assumptions, d.path), rel_std, rate_abs_std)
        for d in normalize_parameters(parameters)
    ]


def simulate_valuations(
    assumptions: ValuationAssumptions,
    samples: pd.DataFrame,
) -> pd.DataFrame:
    """Run the DCF model once per row of ``samples``.

    Args:
        assumptions: Base-case assumptions (not modified).
        samples: One column per parameter path, one row per draw.

    Returns:
        DataFrame with the :data:`VALUATION_OUTPUTS` columns, aligned with
        ``samples``.
    """
    paths = list(samples.columns)
    rows = []
    for draw in samples.itertuples(index=False, name=None):
        a = deepcopy(assumptions)
        for path, value in zip(paths, draw):
            set_parameter(a, path, float(value))
        rows.append(_valuation_outputs(a))
    return pd.DataFrame(rows, index=samples.index,
                        columns=list(VALUATION_OUTPUTS))


def run_monte_carlo(
    assumptions: ValuationAssumptions,
    parameters: ParameterSpec | None = None,
    n_samples: int = DEFAULT_N_SAMPLES,
    seed: int | np.random.Generator | None = None,
    rel_std: float = DEFAULT_REL_STD,
    rate_abs_std: float = DEFAULT_RATE_ABS_STD,
) -> MonteCarloResult:
    """Monte Carlo simulation of the DCF valuation.

    Each selected parameter is drawn independently from
    ``N(mean, std²)`` and the DCF model is re-run for every draw.

    Args:
        assumptions: Base-case assumptions (not modified).
        parameters: The parameters to vary.  ``None`` uses
            :data:`DEFAULT_PARAMETERS`.  Also accepts a path, a list of
            paths / :class:`ParameterDistribution`, or a ``{path: std}``
            mapping.
        n_samples: Number of draws (default 1000).
        seed: Seed or ``numpy.random.Generator`` for reproducible draws.
        rel_std: Default std for amounts, as a fraction of the base
            value (default 0.025 = 2.5 %).
        rate_abs_std: Default absolute std for rates (default 0.0025 =
            0.25 percentage points).

    Returns:
        A :class:`MonteCarloResult`.

    Note:
        Draws are not truncated.  With the default spreads a negative
        amount is practically impossible, but a required real return at
        or below zero gives a terminal value of 0 (see ``DCFModel``).
    """
    rng = seed if isinstance(seed, np.random.Generator) else np.random.default_rng(seed)
    dists = resolve_parameters(assumptions, parameters, rel_std, rate_abs_std)
    samples = draw_samples(dists, n_samples, rng)
    outputs = simulate_valuations(assumptions, samples)
    return MonteCarloResult(
        parameters=tuple(dists),
        samples=pd.concat([samples, outputs], axis=1),
        base_values=_valuation_outputs(assumptions),
        n_samples=n_samples,
        seed=seed if isinstance(seed, int) else None,
    )
