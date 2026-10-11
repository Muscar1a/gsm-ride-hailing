from pathlib import Path
import json
import zipfile
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from gsm_poc.core.artifacts import read_json, sha256_file, write_json, write_frame, fingerprint, environment
from scripts.compare_week2_variance import verify_hashes
from scripts.diagnose_week2_score_inference import derived_outputs, summarize_scores
from scripts.validate_week2_inference import assessment_tests, METHODS

workspace = Path.cwd()
day = workspace / 'docs/submission/days/20261011'
oracle_root = workspace / '.cache/week2-oracle-variance-20261011'
final_root = day / 'results/final_inference'
oracle_archive = day / 'results/oracle_variance'
roots = [workspace / '.cache/week2-final-rct-20261011', workspace / '.cache/week2-final-null-20261011']
plan = read_json(final_root / 'frozen_plan.json')
assert fingerprint({k:v for k,v in plan.items() if k != 'plan_hash'}) == plan['plan_hash']
assert environment(workspace) == plan['environment']
assert sha256_file(workspace / 'scripts/validate_week2_inference.py') == plan['script_sha256']
assert not (final_root / 'summary.csv').exists()
historical_counts = {}
for name in ('support_interval', 'interval_comparison', 'interval_variance', 'dml_variance_pilot', 'score_inference'):
    source = day / 'results' / name
    hashes = read_json(source / 'evidence_checksums.json')
    verify_hashes(source, hashes)
    historical_counts[name] = len(hashes)

def copy_new(source, destination):
    assert not destination.exists(), destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())

oracle_status = read_json(oracle_root / 'status.json')
assert oracle_status['status'] == 'completed' and oracle_status['regenerated_datasets'] == 200
assert oracle_status['model_fits'] == 0
verify_hashes(oracle_root, oracle_status['artifacts'])
for name in (*oracle_status['artifacts'], 'status.json'):
    copy_new(oracle_root / name, oracle_archive / name)
write_json(oracle_archive / 'evidence_checksums.json', {
    str(p.relative_to(oracle_archive)): sha256_file(p) for p in oracle_archive.rglob('*') if p.is_file()
})
frames, statuses = [], []
job_keys = set()
for root, dgp in zip(roots, plan['dgps'], strict=True):
    status = read_json(root / 'status.json')
    assert status['status'] == 'completed' and status['plan_hash'] == plan['plan_hash']
    assert status['attempted_fits'] == 200 and status['expected_fits'] == 200
    assert status['failed_fits_or_inference'] == 0
    verify_hashes(root, status['artifacts'])
    statuses.append(status)
    assert read_json(root / 'protocol.json') == plan
    frame = pd.read_parquet(root / 'seed_metrics.parquet')
    assert len(frame) == 7600 and frame.interval_available.all()
    assert frame.true_value.notna().all() and frame.point.notna().all()
    assert set(frame.seed) == set(plan['seeds']) and frame.dgp_id.eq(dgp).all()
    assert not frame.duplicated(['seed','estimator','family','output_id']).any()
    assert ((frame.lower <= frame.true_value) & (frame.true_value <= frame.upper)).equals(frame.covered.astype(bool))
    assert np.allclose(frame.standard_error * frame.critical_value * 2, frame.upper - frame.lower, atol=1e-12, rtol=1e-10)
    for seed in plan['seeds']:
        paired_ids = set()
        for estimator, method in METHODS.items():
            name = f'{dgp}-{seed}-{estimator}.json'
            job = read_json(root / name)
            assert job['status'] == 'succeeded' and job['point_successful']
            assert (job['dgp_id'],job['seed'],job['estimator']) == (dgp,seed,estimator)
            job_keys.add((dgp,seed,estimator))
            paired_ids.add(job['dataset_id'])
            covariance = np.asarray(job['covariance'])
            assert np.allclose(covariance,covariance.T,atol=1e-12)
            assert np.linalg.eigvalsh(covariance).min() > -1e-12
            selected = frame[(frame.seed == seed) & (frame.estimator == estimator)].set_index(['family','output_id'])
            assert len(selected) == 38 and selected.interval_method.eq(method).all()
            assert selected.dataset_id.eq(job['dataset_id']).all()
            outputs = derived_outputs(np.asarray(job['point']), plan['config']['model']['elasticity_min_probability'])
            assert set(selected.index) == {(o['family'],o['output_id']) for o in outputs}
            for output in outputs:
                row = selected.loc[(output['family'],output['output_id'])]
                assert np.isclose(row.point, output['point'], atol=1e-12)
                expected_se = np.sqrt(max(float(output['gradient'] @ covariance @ output['gradient']),0))
                assert np.isclose(row.standard_error, expected_se, atol=1e-12, rtol=1e-10)
            if estimator == 'dml':
                folds = job['diagnostics']['folds']
                assert len(folds) == 5
                held = []
                for fold in folds:
                    assert not set(fold['train_original_days']) & set(fold['validation_original_days'])
                    assert len(set(fold['train_original_days']) | set(fold['validation_original_days'])) == 20
                    held.extend(fold['validation_original_days'])
                assert len(held) == len(set(held)) == 20
            copy_new(root / name, final_root / dgp / name)
        assert len(paired_ids) == 1
    for name in ('status.json','protocol.json'):
        copy_new(root / name, final_root / dgp / name)
    frames.append(frame)
assert len(job_keys) == 400
metrics = pd.concat(frames, ignore_index=True)
summary = summarize_scores(metrics, dict.fromkeys(METHODS,100))
summary['development_only'] = False
summary['interval_calibration_status'] = 'independent_assessment_not_certification'
assert len(summary) == 152
assert summary.attempted_seeds.eq(100).all() and summary.available_intervals.eq(100).all()
checks = assessment_tests(summary)
assert len(checks) == 168
for row in summary.to_dict('records'):
    group = metrics[(metrics.dgp_id == row['dgp_id']) & (metrics.estimator == row['estimator']) &
                    (metrics.family == row['family']) & (metrics.output_id == row['output_id'])]
    assert len(group) == 100 and set(group.seed) == set(plan['seeds'])
    for label in ('covered','false_positive'):
        values = group[label].dropna().astype(bool)
        assert len(values) == row[f'{label}_denominator'] and int(values.sum()) == row[f'{label}_count']
        if len(values):
            bounds = binomtest(int(values.sum()),len(values)).proportion_ci(method='exact')
            assert np.isclose(row[f'{label}_lower'], bounds.low, atol=1e-12)
            assert np.isclose(row[f'{label}_upper'], bounds.high, atol=1e-12)
summary['exploratory_undercoverage_flag'] = summary.covered_upper < .95
summary['exploratory_null_overreject_flag'] = summary.false_positive_lower > .05
write_frame(final_root / 'seed_metrics.parquet', metrics)
write_frame(final_root / 'summary.csv', summary)
write_frame(final_root / 'assessment_tests.csv', checks)
copy_new(workspace / 'scripts/validate_week2_inference.py', final_root / 'executed_runner.py')
copy_new(Path(__file__), final_root / 'executed_audit.py')
with zipfile.ZipFile(final_root / 'source_snapshot.zip','x',compression=zipfile.ZIP_DEFLATED) as archive:
    paths = list((workspace / 'src').rglob('*.py')) + [workspace / 'pyproject.toml',workspace / 'uv.lock']
    paths += [workspace / 'scripts' / name for name in plan['helper_sha256']]
    paths += [workspace / 'scripts/validate_week2_inference.py',workspace / 'scripts/diagnose_week2_oracle_variance.py']
    for path in paths:
        archive.write(path,path.relative_to(workspace).as_posix())
    for name in plan['context_sha256']:
        archive.write(Path(plan['context_root']) / name, 'source_context/' + name)
audit = {
    'status':'verified', 'historical_archives_unchanged':historical_counts,
    'expected_and_verified_point_fits':400, 'failed_fits_or_inference':0,
    'unique_independent_seeds_per_estimator_dgp':100,
    'verified_output_rows':len(metrics),'individual_summary_rows':len(summary),
    'distinct_coverage_tests':128,'null_false_positive_tests':40,
    'checks':['Full Cartesian identities and source hashes','OLS/DML paired dataset IDs',
              'No oracle input to fitting/interval functions','Joint covariance PSD and delta-method propagation',
              'Points/endpoints/errors/coverage and exact binomial bounds','DML disjoint original-day folds'],
    'production_method_changed':False, 'oracle_variance_used_for_inference':False,
    'core_source_sha256':plan['environment']['source_code_sha256'],
    'remaining_limits':['Evidence C, no GSM data','Individual intervals, no simultaneous coverage guarantee',
                        'No rejection of undercoverage is not certification of nominal 95%',
                        'Full-context policy support remains insufficient','Old percentile results remain historical'],
    'durations_seconds_by_dgp':{p['dgp_id']:p['duration_seconds'] for p in statuses},
}
write_json(final_root / 'audit.json',audit)
write_json(final_root / 'evidence_checksums.json',{
    str(p.relative_to(final_root)):sha256_file(p) for p in final_root.rglob('*') if p.is_file()
})
verify_hashes(final_root,read_json(final_root / 'evidence_checksums.json'))
verify_hashes(oracle_archive,read_json(oracle_archive / 'evidence_checksums.json'))
print(json.dumps({'audit':audit,'holm_rejections':int(checks.rejected.sum()),
                  'exploratory_undercoverage_flags':int(summary.exploratory_undercoverage_flag.sum())},ensure_ascii=True))
