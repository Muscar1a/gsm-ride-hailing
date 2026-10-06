import dataclasses
from pathlib import Path

from streamlit.testing.v1 import AppTest

from gsm_poc.pipeline import Pipeline


def test_dashboard_changes_scenario_and_withholds_unsupported_price(config, monkeypatch):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    Pipeline(config, "app-test").run_all(include_evaluation=False)
    app_path = Path(__file__).parents[1] / "src/gsm_poc/app.py"
    monkeypatch.chdir(config.workspace)
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 3
    assert app.metric[0].label == "Expected bookings"
    app.slider[0].set_value(0).run()
    assert not app.exception
    assert app.metric[0].delta == "+0"
    app.checkbox[0].check().run()
    assert not app.exception
    assert not app.metric
    assert any("outside the designed" in element.value for element in app.warning)


def test_dashboard_saves_selected_zone_scope_in_export(config, monkeypatch):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    Pipeline(config, "app-test-scope").run_all(include_evaluation=False)
    app_path = Path(__file__).parents[1] / "src/gsm_poc/app.py"
    monkeypatch.chdir(config.workspace)
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not app.exception

    # Initially "All zones"
    zone_select = [s for s in app.selectbox if s.label == "Context zone"][0]
    assert zone_select.value == "All zones"
    assert any("Scope: **All zones**" in str(getattr(el, "value", "")) for el in app.markdown)

    # Change to a specific zone (161 -> Midtown Center)
    zone_select.select(161).run()
    assert not app.exception
    assert any("Scope: **Midtown Center**" in str(getattr(el, "value", "")) for el in app.markdown)
