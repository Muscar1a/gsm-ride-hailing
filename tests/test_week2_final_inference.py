import pandas as pd
import pytest

from scripts.validate_week2_inference import assessment_tests


def summary_row(output_id, coverage=95, false_positives=5):
    return {
        "dgp_id": "NULL_EFFECT",
        "estimator": "adjusted_ols",
        "family": "scenario",
        "output_id": output_id,
        "covered_count": coverage,
        "covered_denominator": 100,
        "false_positive_count": false_positives,
        "false_positive_denominator": 100,
    }


def test_final_family_deduplicates_baseline_without_hiding_changes():
    rows = pd.DataFrame(
        [
            summary_row("x_plus10:Y_before_probability"),
            summary_row("y_plus10:Y_before_probability"),
            summary_row("both_plus10:Y_before_probability"),
            summary_row("both_plus10:Y_delta_percentage_points", 50, 50),
        ]
    )
    checks = assessment_tests(rows)
    assert len(checks) == 4
    assert set(checks.output_id) == {
        "x_plus10:Y_before_probability",
        "both_plus10:Y_delta_percentage_points",
    }
    assert not checks.loc[checks.output_id.str.contains("before"), "rejected"].any()
    assert checks.loc[checks.output_id.str.contains("delta"), "rejected"].all()


def test_final_has_no_successful_looking_empty_assessment():
    row = summary_row("x_plus10:Y_before_probability")
    row["covered_denominator"] = row["false_positive_denominator"] = 0
    with pytest.raises(ValueError, match="No assessable"):
        assessment_tests(pd.DataFrame([row]))


def test_null_overrejection_is_checked_in_upper_tail():
    checks = assessment_tests(
        pd.DataFrame([summary_row("x_plus10:Y_delta_percentage_points", 95, 40)])
    )
    assert not checks.loc[checks.check.eq("covered"), "rejected"].any()
    assert checks.loc[checks.check.eq("false_positive"), "rejected"].all()
