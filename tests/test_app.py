import dataclasses
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from gsm_poc.pipeline.pipeline import Pipeline


def test_dashboard_changes_scenario_and_withholds_unsupported_price(config, monkeypatch):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    Pipeline(config, "app-test").run_all(include_evaluation=False)
    app_path = Path(__file__).parents[1] / "src/gsm_poc/ui/app.py"
    monkeypatch.chdir(config.workspace)
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 3
    assert app.metric[0].label == "Expected bookings"
    inference = next(select for select in app.selectbox if select.label == "Inference method")
    assert inference.value == "analytic"
    assert any("88–89%" in item.value for item in app.warning)
    assert any("Technically stable" in item.value for item in app.markdown)
    inference.select("bootstrap").run()
    assert not app.exception
    assert any("day-bootstrap" in item.value for item in app.caption)
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
    app_path = Path(__file__).parents[1] / "src/gsm_poc/ui/app.py"
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


def test_dashboard_uses_source_config_for_frozen_choice_package(config, monkeypatch):
    source_config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    source = Pipeline(source_config, "app-choice-source")
    source.generate()
    source.fit()
    source.method_evaluation()
    source.scenario()
    source.run.complete()
    packaging_config = dataclasses.replace(
        source_config,
        simulation=dataclasses.replace(source_config.simulation, dgp="COLLINEAR_PRICE", seed=99),
        model=dataclasses.replace(source_config.model, min_price_cell_count=100_000),
        evaluation=dataclasses.replace(source_config.evaluation, interval_level=0.80),
        scenario=dataclasses.replace(source_config.scenario, n_sessions=1234),
    )
    package = Pipeline(packaging_config, "app-choice-package")
    package.freeze_choice(source.run.run_id)
    package.run.complete()

    app_path = Path(__file__).parents[1] / "src/gsm_poc/ui/app.py"
    monkeypatch.chdir(config.workspace)
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not app.exception
    source_warnings = [item.value for item in app.warning]
    source_support = next(item.value for item in app.markdown if "Support: **" in item.value)
    run_select = next(select for select in app.selectbox if select.label == "Run ID")
    run_select.select(package.run.run_id).run()
    assert not app.exception
    assert next(select for select in app.selectbox if select.label == "DGP").options == ["RCT_SYN"]
    assert next(select for select in app.selectbox if select.label == "Seed").value == (
        source_config.simulation.seed
    )
    source_manifest = json.loads((source.run.path / "manifest.json").read_text(encoding="utf-8"))
    assert json.loads(app.sidebar.json[0].value) == source_manifest["config"]
    assert {expander.label for expander in app.expander} >= {
        "Model environment and versions",
        "Packaging environment and versions",
    }
    assert next(item for item in app.number_input if item.label == "Quote sessions").value == (
        source_config.scenario.n_sessions
    )
    assert [item.value for item in app.warning] == source_warnings
    assert (
        next(item.value for item in app.markdown if "Support: **" in item.value) == source_support
    )
    assert any(
        f"nominal {source_config.evaluation.interval_level:.0%}" in item.value
        for item in app.caption
    )
    assert any("Calibration is not evaluated for this run" in item.value for item in app.caption)

    next(select for select in app.selectbox if select.label == "Context zone").select(161).run()
    assert not app.exception
    assert any("Scope: **Midtown Center**" in item.value for item in app.markdown)
    app.checkbox[0].check().run()
    assert not app.exception
    assert not app.metric
    assert any("outside the designed" in item.value for item in app.warning)
