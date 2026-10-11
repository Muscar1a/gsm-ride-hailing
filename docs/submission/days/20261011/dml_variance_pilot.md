# Week 2 — Fresh DML variance pilot

Ngày thực hiện: **11/10/2026**, Asia/Bangkok. Trạng thái: **development evidence C; chưa xác nhận calibration hoặc nghiệm thu Week 2**.

## Kết luận

Đã chạy hết pilot đã đóng băng: **20/20 estimator jobs**, gồm DML và adjusted OLS
trên 5 seeds mới cho mỗi DGP RCT_SYN/NULL_EFFECT. **20 point fits và 400 original-day
refits đều thành công**; 80/80 candidate intervals khả dụng. Không chạy bootstrap.

DML RCT Y/Y bao phủ 5/5 seeds, nhưng **Y/X chỉ bao phủ 3/5**. NULL Y/X có **1/5
false positives**. OLS gặp cùng hạn chế Y/X, nên chưa có cơ sở quy vấn đề riêng
cho DML hoặc đổi phương pháp production. Pilot cho thêm một cell cần rà soát,
thay vì chỉ tập trung vào Y/Y ở nghiên cứu trước.

## Kế hoạch, giới hạn và thực thi

[Plan](results/dml_variance_pilot/development_plan.json) được đóng băng trước khi
generate cohort mới. Seeds **43001–43005**, DGPs **RCT_SYN và NULL_EFFECT**, cùng
TLC-derived frozen context, source config, weights, split dates và nominal 95%.
Không gộp với các cohort 41001/42001 hoặc final lịch sử 20001–20100.

Mỗi estimator/dataset có một full-data point fit và 20 delete-one-original-day
refits. Point fit dùng `fit_all` với singleton estimator, giữ identification,
finite-coefficient và validation-probability gates; lỗi DML không xóa kết quả
OLS. Bounds dùng công thức `day_jackknife_t` đã đóng băng trong
[variance sensitivity](interval_variance_comparison.md): original point ± t19 ×
jackknife SE, đủ G=20 omissions. Thiếu/lỗi/chưa chạy bất kỳ omission nào thì
candidate unavailable; không giảm G, đổi scale hoặc dùng fallback.

Actual bootstrap fits/draws bằng **0**. Các cấu hình reporting bootstrap của
source giữ nguyên, không được gọi ở pilot này. Paired baseline là adjusted OLS
trên cùng generated dataset; không có percentile/basic/BCa comparison trên
seeds mới này. Phạm vi chỉ gồm bốn theta cells, chưa gồm elasticity/scenario.

| Giai đoạn đã chốt | Dataset jobs | Estimator jobs | Point fits | Day refits | Thời gian stage |
|---|---:|---:|---:|---:|---:|
| RCT 43001 probe | 1 | 2 | 2 | 40 | 74,74 s |
| RCT 43002–43005 | 4 | 8 | 8 | 160 | 274,76 s |
| NULL 43001–43005 | 5 | 10 | 10 | 200 | 343,26 s |
| Tổng | 10 | 20 | 20 | 400 | — |

Probe DML mất **71,33 s**, không lỗi, dưới guard 180 s trước khi mở rộng.
RCT remainder và NULL chạy đồng thời, tối đa hai tiến trình, native threads=1;
thời gian các stages không được cộng thành wall time. Probe được giữ trong toàn
bộ thống kê; không rerun hoặc loại probe theo kết quả. Fit count ở đây là một
lượt fit estimator, bao gồm các learned components bên trong.

## Kết quả trên cùng 5 seeds

Coverage RCT_SYN là số intervals chứa đúng theta:

| Outcome / price treatment | Adjusted OLS | DML |
|---|---:|---:|
| X / X | 4/5 | 5/5 |
| X / Y | 5/5 | 5/5 |
| Y / X | 3/5 | 3/5 |
| Y / Y | 5/5 | 5/5 |

DML có một paired coverage gain ở X/X, không loss; các cells còn lại có cùng
coverage với OLS. Mean paired DML/OLS width ratios RCT lần lượt **1,107288;
1,097805; 1,096613; 1,122177** cho XX/XY/YX/YY. Bounds rộng hơn chưa giải quyết
hai lần miss ở Y/X.

NULL_EFFECT false positives:

| Outcome / price treatment | Adjusted OLS | DML |
|---|---:|---:|
| X / X | 0/5 | 0/5 |
| X / Y | 0/5 | 0/5 |
| Y / X | 1/5 | 1/5 |
| Y / Y | 0/5 | 0/5 |

Exact 95% binomial bounds thể hiện độ chính xác hạn chế của pilot: coverage
**5/5 → [47,82%; 100%]**, **3/5 → [14,66%; 94,73%]**;
false-positive rate **0/5 → [0%; 52,18%]**, **1/5 → [0,51%; 71,64%]**.
Các bounds là theo từng cell, không có multiple-comparison adjustment.
Không dùng kết quả 5/5 để xác nhận coverage 95%, hoặc kết luận global calibration
từ một cell trong pilot nhỏ.

RMS jackknife SE / empirical point SD, cùng năm valid seeds trong từng cell:

| Outcome / price treatment | RCT OLS | RCT DML | NULL OLS | NULL DML |
|---|---:|---:|---:|---:|
| X / X | 0,709050 | 0,790597 | 0,728609 | 0,822358 |
| X / Y | 1,806264 | 1,639967 | 1,687845 | 1,418246 |
| Y / X | 0,489821 | 0,529326 | 0,638988 | 0,656571 |
| Y / Y | 1,651487 | 1,471195 | 2,059518 | 1,846672 |

DML RCT Y/X: RMS SE **0,010033**, empirical SD **0,018955**, ratio **0,529326**.
Các ratios không ổn định theo cell; empirical SD chỉ có 5 seeds nên cũng rất
thiếu chính xác. Không lấy ratio làm multiplier được tối ưu trên pilot.
Full bias/RMSE, exact bounds, widths và failure denominators có ở
[summary](results/dml_variance_pilot/summary.csv),
[per-seed metrics](results/dml_variance_pilot/seed_metrics.csv) và
[paired estimator comparison](results/dml_variance_pilot/paired_estimators.csv).

## Kiểm chứng và truy vết

- **152 tests đạt**, gồm 16 tests mới; Ruff lint, format hai files mới, ty và
  diff check đạt. Fixtures kiểm tra lỗi point/validation, lỗi omission,
  not-attempted counts, nguồn bị sửa, không overwrite và oracle boundary.
- Hashes của toàn bộ nguồn được kiểm tra trước khi đọc/generate và sau chạy;
  model/helper/source config giữ nguyên. Cả hai estimator dùng cùng dataset ID
  cho từng DGP/seed. Kết quả cũ được giữ nguyên.
- Root đối chiếu độc lập 80 cells với đúng union của ba stages; recompute variance,
  SE, t19 bounds, coverage/false-positive flags và exact binomial bounds. Số fit
  thành công/lỗi/chưa chạy được đếm lại từ job records và jackknife tables.
- Full DML fold records được đối chiếu với point diagnostics. Mỗi omission có
  đủ configured folds, đúng 19 remaining days và không có day leakage. Omission
  fold records mô tả deterministic assignment plan; trạng thái refit ghi execution.
- [JSON report](dml_variance_pilot.json),
  [400 day-refit records](results/dml_variance_pilot/jackknife.csv),
  [executed source](results/dml_variance_pilot/executed_pilot_runner.py) và
  [evidence checksums](results/dml_variance_pilot/evidence_checksums.json) giữ
  protocol/status/fold metadata của từng stage và job.

Plan hash: `cf8ab5dc793085fe9cecb1d9eaa02c61180af96bd09dacc02613c578ef7ecef2`.
Pilot script hash: `eda3e7afb63fb7b30454c3ad5d1fec4816dadeddbca010de4b57df0a3bcb0ac2`.
Numerical source hash: `1654258a72a6098d12fca3cb96314d67d43526c5d4ac548ff52d14234a2919f6`.

Hai Pandas FutureWarnings vẫn ở fixture unavailable của controller trước;
assertions đạt trên dependency đã khóa. Không thay controller đã dùng cho
nghiên cứu cũ. Không chạy lại UI hoặc whole-repo format cho script độc lập này.

## Công việc còn lại

Chưa chọn phương pháp production hoặc chạy final/calibration mới. Nhánh mới
chạy được trên nhiều DML seeds, nhưng các kết quả Y/X và SE/SD cần tiếp tục
đánh giá bằng development cohort lớn hơn, cùng rà soát variance assumptions
cho sampling/assignment unit và day/fold sensitivity. Không giải quyết chỉ
bằng tăng bootstrap draws hoặc điều chỉnh scale theo số đo hiện tại.

Các full datasets giữ cùng 20-day calendar grid; việc bỏ một ngày có thể làm
GroupKFold đổi partitions, thêm perturbation ngoài omission. DML jackknife SE
không được coi là bảo đảm sampling uncertainty. Sau khi chốt phương pháp và
criteria, dùng unused seeds cho final evaluation; elasticity/scenario cần kiểm
chứng riêng. X/Y vẫn là dịch vụ giả định, GSM chưa có data hoặc bằng chứng thực địa.
