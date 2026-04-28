"""
Airline passenger time series forecasting.
Compares Naive, SMA, Holt-Winters, ARIMA, SARIMA, and SARIMAX across a train/test split.
"""
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    from scipy.stats import boxcox
    from scipy.special import inv_boxcox
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    from statsmodels.tsa.stattools import adfuller, kpss
    SM_AVAILABLE = True
except ImportError:
    SM_AVAILABLE = False

try:
    from sklearn.metrics import mean_squared_error
    SKLEARN_AVAILABLE = True
except ImportError:
    def mean_squared_error(a, b):
        return float(np.mean((np.array(a) - np.array(b)) ** 2))
    SKLEARN_AVAILABLE = False


class AirlinePassengerForecaster:
    """
    Fits multiple forecasting models to an airline passenger time series
    and compares RMSE and MAPE across methods.
    """

    def __init__(self, data: pd.Series, train_ratio: float = 0.8):
        n = len(data)
        split = int(n * train_ratio)
        self.train = data.iloc[:split]
        self.test = data.iloc[split:]
        self.n_test = len(self.test)
        self._boxcox_lambda: Optional[float] = None

    def rmse(self, actual: np.ndarray, predicted: np.ndarray) -> float:
        return float(np.sqrt(mean_squared_error(actual, predicted)))

    def mape(self, actual: np.ndarray, predicted: np.ndarray) -> float:
        actual = np.array(actual, dtype=float)
        predicted = np.array(predicted, dtype=float)
        mask = actual != 0
        return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)

    def test_stationarity(self) -> Dict:
        """Run ADF and KPSS tests on the training series."""
        results = {}
        if SM_AVAILABLE:
            adf = adfuller(self.train)
            results["adf"] = {
                "statistic": round(adf[0], 4),
                "p_value": round(adf[1], 4),
                "is_stationary": adf[1] < 0.05,
            }
            try:
                kpss_stat, kpss_p, _, _ = kpss(self.train, regression="c", nlags="auto")
                results["kpss"] = {
                    "statistic": round(kpss_stat, 4),
                    "p_value": round(kpss_p, 4),
                    "is_stationary": kpss_p > 0.05,
                }
            except Exception:
                pass
        return results

    def apply_boxcox(self) -> pd.Series:
        """Apply Box-Cox transformation to stabilize variance."""
        if not SCIPY_AVAILABLE:
            return self.train
        transformed, lam = boxcox(self.train + 1)
        self._boxcox_lambda = lam
        return pd.Series(transformed, index=self.train.index)

    def naive_forecast(self) -> Dict:
        """Last observed value repeated for the test horizon."""
        last_val = float(self.train.iloc[-1])
        pred = np.full(self.n_test, last_val)
        return {"model": "Naive", "rmse": self.rmse(self.test.values, pred), "mape": self.mape(self.test.values, pred)}

    def simple_average_forecast(self) -> Dict:
        avg = float(self.train.mean())
        pred = np.full(self.n_test, avg)
        return {"model": "SimpleAverage", "rmse": self.rmse(self.test.values, pred), "mape": self.mape(self.test.values, pred)}

    def simple_moving_average(self, window: int = 12) -> Dict:
        sma = float(self.train.iloc[-window:].mean())
        pred = np.full(self.n_test, sma)
        return {"model": f"SMA{window}", "rmse": self.rmse(self.test.values, pred), "mape": self.mape(self.test.values, pred)}

    def holt_winters_additive(self) -> Dict:
        if not SM_AVAILABLE:
            return {"model": "HW-Add", "rmse": None, "mape": None}
        model = ExponentialSmoothing(self.train, trend="add", seasonal="add", seasonal_periods=12)
        fit = model.fit(optimized=True)
        pred = fit.forecast(self.n_test)
        return {"model": "HW-Add", "rmse": self.rmse(self.test.values, pred.values), "mape": self.mape(self.test.values, pred.values)}

    def holt_winters_multiplicative(self) -> Dict:
        if not SM_AVAILABLE:
            return {"model": "HW-Mult", "rmse": None, "mape": None}
        model = ExponentialSmoothing(self.train, trend="mul", seasonal="mul", seasonal_periods=12)
        fit = model.fit(optimized=True)
        pred = fit.forecast(self.n_test)
        return {"model": "HW-Mult", "rmse": self.rmse(self.test.values, pred.values), "mape": self.mape(self.test.values, pred.values)}

    def fit_sarima(self, order: Tuple = (1, 1, 1), seasonal_order: Tuple = (1, 1, 1, 12)) -> Dict:
        if not SM_AVAILABLE:
            return {"model": f"SARIMA{order}x{seasonal_order}", "rmse": None, "mape": None}
        try:
            model = SARIMAX(self.train, order=order, seasonal_order=seasonal_order,
                            enforce_stationarity=False, enforce_invertibility=False)
            fit = model.fit(disp=False)
            pred = fit.forecast(self.n_test)
            label = f"SARIMA({order[0]},{order[1]},{order[2]})x({seasonal_order[0]},{seasonal_order[1]},{seasonal_order[2]},{seasonal_order[3]})"
            return {"model": label, "rmse": self.rmse(self.test.values, pred.values), "mape": self.mape(self.test.values, pred.values)}
        except Exception as e:
            return {"model": "SARIMA", "rmse": None, "mape": None, "error": str(e)}

    def fit_sarimax(self, order: Tuple = (1, 1, 1), seasonal_order: Tuple = (1, 1, 1, 12),
                    exog_train: Optional[np.ndarray] = None, exog_test: Optional[np.ndarray] = None) -> Dict:
        if not SM_AVAILABLE:
            return {"model": "SARIMAX", "rmse": None, "mape": None}
        try:
            model = SARIMAX(self.train, exog=exog_train, order=order, seasonal_order=seasonal_order,
                            enforce_stationarity=False, enforce_invertibility=False)
            fit = model.fit(disp=False)
            pred = fit.forecast(self.n_test, exog=exog_test)
            return {"model": "SARIMAX", "rmse": self.rmse(self.test.values, pred.values), "mape": self.mape(self.test.values, pred.values)}
        except Exception as e:
            return {"model": "SARIMAX", "rmse": None, "mape": None, "error": str(e)}

    def compare_all_models(self) -> pd.DataFrame:
        """Run all forecasting methods and return a comparison DataFrame sorted by RMSE."""
        results = [
            self.naive_forecast(),
            self.simple_average_forecast(),
            self.simple_moving_average(12),
            self.holt_winters_additive(),
            self.holt_winters_multiplicative(),
            self.fit_sarima((1, 1, 1), (1, 1, 1, 12)),
            self.fit_sarimax((1, 1, 1), (1, 1, 1, 12)),
        ]
        df = pd.DataFrame(results)
        df = df.dropna(subset=["rmse"])
        df["rmse"] = df["rmse"].round(2)
        df["mape"] = df["mape"].round(2)
        return df.sort_values("rmse").reset_index(drop=True)


if __name__ == "__main__":
    try:
        import statsmodels.datasets.co2 as co2_data
        raw = co2_data.load_pandas().data["co2"].dropna()
        raw.index = pd.date_range(start="1958-03", periods=len(raw), freq="W")
        series = raw.resample("MS").mean().dropna().iloc[:144]
    except Exception:
        idx = pd.date_range(start="1949-01", periods=144, freq="MS")
        np.random.seed(42)
        trend = np.linspace(100, 400, 144)
        seasonal = 30 * np.sin(np.linspace(0, 12 * np.pi, 144))
        noise = np.random.normal(0, 10, 144)
        series = pd.Series(trend + seasonal + noise, index=idx)

    forecaster = AirlinePassengerForecaster(series)
    print("Stationarity:", forecaster.test_stationarity())
    comparison = forecaster.compare_all_models()
    print("\nModel Comparison:")
    print(comparison.to_string(index=False))
