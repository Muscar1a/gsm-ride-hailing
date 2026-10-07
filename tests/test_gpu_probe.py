from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from sklearn.base import clone
from sklearn.model_selection import GroupKFold

script_path = Path(__file__).resolve().parents[1] / "scripts/probe_week2_gpu.py"
module_spec = importlib.util.spec_from_file_location("week2_gpu_probe", script_path)
assert module_spec is not None and module_spec.loader is not None
probe = importlib.util.module_from_spec(module_spec)
sys.modules[module_spec.name] = probe
module_spec.loader.exec_module(probe)


def test_snapshot_source_hash_preserves_windows_manifest_convention(tmp_path):
    source_folder = tmp_path / "src/gsm_poc"
    source_folder.mkdir(parents=True)
    source_bytes = b"value = 1\r\n"
    source_path = source_folder / "module.py"
    source_path.write_bytes(source_bytes)
    manifest = {r"src\gsm_poc\module.py": hashlib.sha256(source_bytes).hexdigest()}
    expected = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    assert probe.snapshot_source_hash(tmp_path) == expected
    source_path.write_bytes(b"value = 2\r\n")
    assert probe.snapshot_source_hash(tmp_path) != expected


def test_probe_preserves_existing_results_and_frozen_snapshot(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    existing_output = tmp_path / "completed_probe"
    existing_output.mkdir()
    result_file = existing_output / "report.json"
    original_bytes = b'{"status": "succeeded"}\n'
    result_file.write_bytes(original_bytes)
    shared_arguments = ["--snapshot", str(snapshot), "--backend", "gpu", "--draws", "2"]
    with pytest.raises(ValueError, match="already exists"):
        probe.main(shared_arguments + ["--output", str(existing_output)])
    assert result_file.read_bytes() == original_bytes
    invalid_output = snapshot / "probe_outputs"
    with pytest.raises(ValueError, match="outside the frozen"):
        probe.main(shared_arguments + ["--output", str(invalid_output)])
    assert not invalid_output.exists()


def test_nuisance_adapter_clone_preserves_configuration_and_output_shapes():
    rng = np.random.default_rng(7)
    features = rng.normal(size=(60, 3))
    targets = np.column_stack([features[:, 0], features[:, 1]])
    weights = np.linspace(1, 2, len(features))
    model = probe.ProbeForest(
        n_estimators=5, max_depth=3, min_samples_leaf=2, random_state=17, backend="cpu"
    )
    copied = clone(model)
    assert copied.get_params() == model.get_params()
    copied.fit(features, targets, sample_weight=weights)
    assert copied.predict(features[:4]).shape == (4, 2)
    assert np.isfinite(copied.predict(features[:4])).all()
    single = clone(model).fit(features, targets[:, 0], sample_weight=weights)
    assert single.predict(features[:4]).shape == (4,)


def test_nuisance_adapter_integrates_with_weighted_multioutput_linear_dml():
    from econml.dml import LinearDML

    rng = np.random.default_rng(11)
    features = rng.normal(size=(120, 3))
    treatments = rng.normal(size=(120, 2)) + features[:, :2]
    outcomes = treatments @ np.array([[-0.6, 0.15], [0.12, -0.5]]).T
    outcomes += features[:, :2] + rng.normal(scale=0.1, size=(120, 2))
    groups = np.repeat(np.arange(12), 10)
    forests = probe.ProbeForest(n_estimators=5, min_samples_leaf=2, backend="cpu")
    model = LinearDML(
        model_y=clone(forests),
        model_t=clone(forests),
        cv=list(GroupKFold(3).split(features, groups=groups)),
        random_state=11,
    )
    model.fit(
        outcomes,
        treatments,
        W=features,
        groups=groups,
        sample_weight=np.linspace(1, 2, len(features)),
        inference=None,
    )
    effects = np.asarray(model.const_marginal_effect())
    assert effects.shape == (1, 2, 2)
    assert np.isfinite(effects).all()


def test_nuisance_adapter_rejects_invalid_weights_and_backend():
    features = np.ones((10, 2))
    targets = np.ones((10, 2))
    with pytest.raises(ValueError, match="sample weights"):
        probe.ProbeForest(backend="cpu").fit(features, targets, sample_weight=np.zeros(10))
    with pytest.raises(ValueError, match="backend"):
        probe.ProbeForest(backend="automatic").fit(features, targets)


def install_gpu_fixture(monkeypatch, forest_type):
    cupy_module = ModuleType("cupy")
    cupy_module.asarray = np.asarray
    cupy_module.cuda = SimpleNamespace(
        Stream=SimpleNamespace(null=SimpleNamespace(synchronize=lambda: None))
    )
    cuml_module = ModuleType("cuml")
    ensemble_module = ModuleType("cuml.ensemble")
    ensemble_module.RandomForestRegressor = forest_type
    monkeypatch.setitem(sys.modules, "cupy", cupy_module)
    monkeypatch.setitem(sys.modules, "cuml", cuml_module)
    monkeypatch.setitem(sys.modules, "cuml.ensemble", ensemble_module)


def test_gpu_adapter_never_discards_nonuniform_weights(monkeypatch):
    class UnweightedForest:
        def __init__(self, **parameters):
            pass

        def fit(self, x_data, y_data):
            pytest.fail("Unsupported weighted GPU fit was executed")

    install_gpu_fixture(monkeypatch, UnweightedForest)
    with pytest.raises(ValueError, match="nonuniform weights"):
        probe.ProbeForest().fit(
            np.ones((10, 2)), np.ones((10, 2)), sample_weight=np.linspace(1, 2, 10)
        )


def test_gpu_adapter_rejects_silent_cpu_fallback(monkeypatch):
    class CpuFallbackForest:
        def __init__(self, **parameters):
            pass

        def fit(self, x_data, y_data):
            return self

    install_gpu_fixture(monkeypatch, CpuFallbackForest)
    with pytest.raises(RuntimeError, match="CPU implementation"):
        probe.ProbeForest().fit(np.ones((10, 2)), np.ones((10, 2)), sample_weight=np.ones(10))
