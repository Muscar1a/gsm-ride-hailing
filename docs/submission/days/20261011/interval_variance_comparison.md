# Week 2 — Day-jackknife variance sensitivity

Ngày thực hiện: **11/10/2026**, Asia/Bangkok. Trạng thái: **development evidence C; chưa nghiệm thu calibration**.

## Kết luận

Đã triển khai và chạy so sánh `day_jackknife_t` trên đúng các points và day refits
đã lưu của [nhánh percentile/basic/BCa](interval_method_comparison.md), không fit
thêm. OLS RCT Y/Y tăng coverage từ **17/20 lên 19/20**, với mean paired width ratio
**1,142689** so với percentile. NULL Y/Y vẫn có **3/20 false positives**.
Đây là kết quả sensitivity có ích, chưa đủ căn cứ chọn phương pháp production.

## Phạm vi và phương pháp đã đóng băng

[Development plan](../../../../artifacts/research/20261011/results/interval_variance/development_plan.json) được ghi trước
khi tính candidate. Cả bốn phương pháp dùng cùng point estimate, không điều chỉnh
multiplier theo oracle và không thay support hoặc nominal 95%.

Với 20 original training-day omissions đã lưu, tính cho từng theta cell:

$$
\hat V_J=\frac{G-1}{G}\sum_{g=1}^{G}
  (\hat\theta_{(-g)}-\overline{\hat\theta}_{(-g)})^2,
\qquad
CI=\hat\theta_{\mathrm{full}}\pm t_{G-1,0.975}\sqrt{\hat V_J},
\quad G=20.
$$

Tâm interval là point gốc; df=19. Thiếu, trùng, lỗi hoặc chưa chạy bất kỳ omission
nào, coefficient không hữu hạn hoặc variance suy biến thì candidate unavailable;
không giảm G hoặc thay bằng interval khác. Attempted, failed, not attempted và
missing groups được đếm riêng. Bootstrap counts của nguồn chỉ là metadata tham
chiếu, không quyết định technical status của candidate này.

Công thức variance theo [rbmi, §3.8.2](https://www.stat.ethz.ch/CRAN/web/packages/rbmi/vignettes/stat_specs.html).
Trong linear regression, mean-centered jackknife này liên quan CV3J, khác tâm
full-estimate của CV3; xem [MacKinnon, Nielsen và Webb](https://econ.queensu.ca/faculty/mackinnon/working-papers/qed_wp_1483.pdf).
Generic DML refits không được tự động kế thừa bảo đảm của linear regression.
Lựa chọn t19 là quy tắc sensitivity đã đóng băng, chưa chứng minh calibration.

## Thực thi

| Cohort đã lưu | Jobs | Day refits được dùng lại | Fit mới | Candidate unavailable | Thời gian postprocess |
|---|---:|---:|---:|---:|---:|
| OLS, seeds 42001–42020, RCT_SYN + NULL_EFFECT | 40 | 800 | 0 | 0/160 | 2,91 s |
| DML, RCT_SYN seed 42001 | 1 | 20 | 0 | 0/4 | 0,77 s |

Thời gian trên là phần postprocess, không bao gồm khởi động Python và chi phí
fit/bootstrap ở nghiên cứu trước. Không thêm seeds hoặc bằng chứng độc lập.
Các kết quả không được gộp với cohort 41001–41020 hoặc final lịch sử 20001–20100.

## OLS: kết quả cùng seeds

Coverage RCT_SYN dưới đây là số interval chứa đúng theta trong 20 seeds:

| Outcome / price treatment | Percentile | Basic | BCa | Day jackknife t |
|---|---:|---:|---:|---:|
| X / X | 18/20 | 17/20 | 19/20 | 18/20 |
| X / Y | 19/20 | 19/20 | 19/20 | 19/20 |
| Y / X | 20/20 | 20/20 | 20/20 | 20/20 |
| Y / Y | 17/20 | 17/20 | 18/20 | 19/20 |

RCT Y/Y có hai paired coverage gains, không có loss. Mean interval width tăng
từ **0,039730 lên 0,045157**; mean paired width ratio là **1,142689**. Coverage
19/20 có exact 95% binomial interval **[75,13%; 99,87%]**, nên số đo 95% trong
20 seeds chưa xác lập nominal coverage 95%.

False positives NULL_EFFECT, cũng trên cùng 20 seeds:

| Outcome / price treatment | Percentile | Basic | BCa | Day jackknife t |
|---|---:|---:|---:|---:|
| X / X | 2/20 | 3/20 | 2/20 | 2/20 |
| X / Y | 1/20 | 1/20 | 1/20 | 1/20 |
| Y / X | 1/20 | 0/20 | 2/20 | 0/20 |
| Y / Y | 3/20 | 3/20 | 3/20 | 3/20 |

NULL Y/Y không có paired gain/loss; false-positive rate 3/20 có exact 95%
binomial interval **[3,21%; 37,89%]**. Không thể kết luận lỗi báo động giả đã được
giải quyết, hoặc chọn phương pháp chỉ dựa trên cải thiện RCT Y/Y.

RMS jackknife SE so với empirical point SD, dùng đúng cùng 20 valid seeds/cell:

| Outcome / price treatment | RCT_SYN: RMS SE / empirical SD | NULL_EFFECT: RMS SE / empirical SD |
|---|---:|---:|
| X / X | 0,790841 | 0,813283 |
| X / Y | 1,146695 | 1,172109 |
| Y / X | 1,045724 | 1,050000 |
| Y / Y | 0,894290 | 0,926361 |

Các ratios vẫn lệch theo cell; không dùng chúng làm hệ số bù được tối ưu trên
development. Full summaries giữ bias, RMSE, exact bounds, width và denominators:
[OLS summary](../../../../artifacts/research/20261011/results/interval_variance/development/summary.csv),
[per-seed metrics](../../../../artifacts/research/20261011/results/interval_variance/development/seed_metrics.csv).

## DML probe

RCT Y/Y point **−0,505757**; jackknife SE **0,011303**, candidate bounds
**[−0,529415; −0,482099]**, chứa true theta −0,5. Percentile/basic/BCa và
candidate đều bao phủ truth ở seed này.

Đây là một execution probe; 20 omitted days không phải 20 Monte Carlo seeds.
Empirical point SD và RMS-SE/SD ratio được giữ unavailable vì chỉ có một seed.
Xem [DML summary](../../../../artifacts/research/20261011/results/interval_variance/dml_probe/summary.csv) và
[per-seed metrics](../../../../artifacts/research/20261011/results/interval_variance/dml_probe/seed_metrics.csv).

## Kiểm chứng và truy vết

- **136 tests đạt**, gồm 17 tests mới. Mean fixture cho variance đúng bằng
  sample variance/G và interval đúng textbook Student-t của sample mean.
- Ruff lint, format của hai file mới, ty và diff check đạt.
- Tất cả source artifacts được kiểm tra hashes trước khi đọc bảng và sau tính.
  Points, endpoints, flags và metadata của ba phương pháp cũ được đối chiếu nguyên vẹn.
- Root recompute độc lập variance, SE, t19, bounds, coverage/false positives cho
  toàn bộ 164 candidate cells; xác nhận đủ 820 saved refits và zero new fits.
- Source code hash: `1654258a72a6098d12fca3cb96314d67d43526c5d4ac548ff52d14234a2919f6`.
  Postprocessor hash: `bdb5632011f35c791ba5b3bfba1b281046c6a724a154726f76d30b5428fe3437`.
  Plan hash: `13a9e35fa24e1cda5ff870a8fdd446ea43ad146d0b9bada96e10d99e38f6919b`.
- [JSON report](../../../../artifacts/research/20261011/interval_variance_comparison.json),
  [executed source](../../../../artifacts/research/20261011/results/interval_variance/executed_variance_runner.py),
  [evidence checksums](../../../../artifacts/research/20261011/results/interval_variance/evidence_checksums.json) và mỗi
  cohort's protocol/status giữ source identities, environment và execution duration.

Hai Pandas FutureWarnings chỉ xuất hiện ở fixture toàn bộ candidate unavailable
(concatenation mới và reused summarizer); assertions đạt trên dependency đã khóa.
Không sửa controller đã dùng cho nghiên cứu cũ để tránh đổi lịch sử thực thi.
Không chạy lại UI hoặc toàn bộ repo format cho script nghiên cứu độc lập này.

## Công việc còn lại

Chưa đổi phương pháp production, chưa chạy final/calibration mới và chưa đóng
nghiệm thu Week 2. Tiếp theo cần pilot DML nhiều seeds gồm RCT và NULL để xem
variance/fold sensitivity, sau đó chốt phương pháp và acceptance criteria trước
benchmark final độc lập. Elasticity/scenario intervals cần kiểm chứng riêng;
calibration theta không tự chuyển sang các đầu ra đó. GSM chưa có data, nên
chưa có bằng chứng thực địa hoặc xác nhận kinh doanh.

Giữ X/Y theo mô hình giả định đã được Bun chấp thuận. Các ngày lịch cố định của
bối cảnh semi-synthetic không được khẳng định IID hoặc đại diện cho thị trường GSM.
