# Week 2 — Joint score inference diagnosis

Ngày thực hiện: **11/10/2026**, Asia/Bangkok. Trạng thái: **development evidence C;
chưa chọn phương pháp production hoặc nghiệm thu calibration**.

## Kết quả chính

Đã thực thi đầy đủ protocol đóng băng: **252/252 point fits**, không lỗi fit hoặc
inference. Cohort chính gồm adjusted OLS trên **100 seeds/DGP** và DML trên
**20 seeds/DGP**, với RCT_SYN và NULL_EFFECT. Mười hai fit DML bổ sung kiểm tra
4/10 folds trên ba seeds đã có; các fit này không tăng denominator coverage.
Không chạy bootstrap hoặc jackknife refits.

OLS block HC3/t cho theta RCT Y/Y **96/100**, Y/X **92/100**; DML block score
cho cả Y/Y và Y/X **19/20**. Các số đo này thuộc cohort mới, không phải paired
improvement so với percentile lịch sử hoặc pilot 43001–43005. Chúng không chứng
minh nominal 95% và không giải quyết mọi đầu ra: scenario còn có undercoverage.

## Phương pháp và phạm vi

- Giữ context, point estimator, support minimum, nuisance settings và split
  train/validation/test. DML chỉ thêm khả năng giữ residuals ngoài mẫu trong
  `FitResult` khi được yêu cầu; default fit không giữ thêm dữ liệu. Kiểm tra
  residual row order và tái dựng theta từ score phải khớp point đã fit.
- OLS: block HC3, hiệu chỉnh leverage, Student-t với `N-rank` degrees of freedom.
  DML: covariance từ orthogonal scores ngoài mẫu, tham chiếu normal.
- Cả hai: sensitivity CR1 bằng tổng scores trong ngày, correction
  `G/(G-1)*(N-1)/(N-rank)` và t19, với G=20. Đây không phải CR2/CV3 hoặc bảo đảm
  inference DML khi có ít nhóm.
- Joint covariance gồm theta XX/XY/YX/YY và hai baseline probabilities. Baseline
  influence giữ hiệu ứng do ước lượng theta và covariance giữa các dịch vụ.
  Elasticity dùng delta method có cả đạo hàm theo baseline; scenario giữ joint
  covariance của mọi hệ số liên quan.
- Mỗi job có **38 đầu ra**: bốn theta, bốn elasticity, và mười chỉ số cho mỗi
  scenario +10% X, +10% Y, +10% cả hai, với 10.000 quote sessions. Intervals và
  exact binomial bounds là riêng từng đầu ra, chưa hiệu chỉnh nhiều so sánh.
- Generator giữ calendar/context cố định, gán giá và multinomial counts độc lập
  theo block. Block inference là mốc kiểm tra có cơ sở trong DGP này; grouping
  theo ngày là sensitivity. Chưa biết assignment/dependence unit của GSM.

Nguồn công thức: [HC3 trong statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLSResults.HC3_se.html),
[score variance của DoubleML](https://docs.doubleml.org/stable/guide/se_confint.html),
[clustering và cross-fitting](https://docs.doubleml.org/stable/examples/py_double_ml_multiway_cluster.html).
Các nguồn này không chứng nhận calibration cho cấu hình đang thử.

## Theta: đủ bốn ô

Coverage là số khoảng chứa true theta; NULL FP là số khoảng không chứa 0.

| Method | Cell | RCT coverage | NULL false positives |
|---|---|---:|---:|
| OLS block HC3/t | X/X | 96/100 | 5/100 |
| OLS block HC3/t | X/Y | 98/100 | 2/100 |
| OLS block HC3/t | Y/X | 92/100 | 5/100 |
| OLS block HC3/t | Y/Y | 96/100 | 8/100 |
| OLS day CR1/t19 | X/X | 95/100 | 5/100 |
| OLS day CR1/t19 | X/Y | 96/100 | 3/100 |
| OLS day CR1/t19 | Y/X | 93/100 | 5/100 |
| OLS day CR1/t19 | Y/Y | 95/100 | 8/100 |
| DML block score/normal | X/X | 18/20 | 1/20 |
| DML block score/normal | X/Y | 20/20 | 0/20 |
| DML block score/normal | Y/X | 19/20 | 1/20 |
| DML block score/normal | Y/Y | 19/20 | 1/20 |
| DML day CR1/t19 | X/X | 18/20 | 2/20 |
| DML day CR1/t19 | X/Y | 20/20 | 0/20 |
| DML day CR1/t19 | Y/X | 19/20 | 0/20 |
| DML day CR1/t19 | Y/Y | 20/20 | 1/20 |

RCT RMS SE / empirical SD của block method: OLS XX **1,0158**, XY **1,0609**,
YX **0,8941**, YY **0,9578**; DML lần lượt **0,8915**, **1,2939**, **0,9101**,
**1,0956**. Không dùng ratios làm multiplier bù. Empirical SD của DML chỉ có
20 seeds, vẫn thiếu chính xác. Exact 95% bounds của coverage 96/100 là
[90,07%; 98,90%]; 19/20 là [75,13%; 99,87%], nên không thể coi point coverage
bằng hoặc gần 95% là nghiệm thu calibration.

## Elasticity và scenario

Elasticity RCT theo block method:

| Cell | OLS | DML |
|---|---:|---:|
| X/X | 95/100 | 19/20 |
| X/Y | 98/100 | 20/20 |
| Y/X | 93/100 | 18/20 |
| Y/Y | 93/100 | 19/20 |

Theta và elasticity không có coverage invariance khi baseline được ước lượng.
Các khoảng NULL elasticity cho kết quả false positives giống theta trong cohort
này, vì true ratio bằng 0 và baseline dương; đây không phải bảo đảm tổng quát.

Scenario RCT OLS block có coverage riêng từng metric trong khoảng **88–99/100**;
DML block **18–20/20**. NULL OLS block **89–98/100**, DML block **16–20/20**.
Một số điểm cần giữ mở:

- RCT OLS `both_plus10:Y_after_probability`: **88/100**, exact 95% coverage upper
  **93,64%**; `Y_delta_percentage_points` cùng scenario: **89/100**.
- NULL OLS `both_plus10:Y_after_probability`: **89/100**.
- NULL DML `Y_before_probability`: **16/20**, upper **94,27%**; cùng baseline
  xuất hiện trong cả ba scenario, không phải ba bằng chứng độc lập.
- Day covariance cho baseline OLS RCT X có RMS-SE/SD **0,8079**, so với block
  **0,9621**. Kết quả cho thấy lựa chọn nhóm ảnh hưởng variance trong target
  fixed-calendar này; chưa đủ để quy toàn bộ undercoverage lịch sử cho một nguyên nhân.

Flags dựa vào exact upper coverage <95% hoặc exact lower FP >5% được đóng băng
trước chạy, mang ý nghĩa khám phá từng output. Có nhiều outputs phụ thuộc nhau;
không dùng flags này để tuyên bố global calibration hoặc global rejection.

Support được kiểm tra bằng quy tắc hiện tại cho baseline và target và giữ riêng
trong metrics. Coverage trên full frozen test contexts là chẩn đoán thống kê;
full-context population vẫn có nhóm thiếu support, nên các số đo không cấp quyền
ra quyết định chính sách trên population đó.

## Folds và chi phí

Thay 5 folds bằng 4/10 folds trên cùng ba seeds không tạo quan sát độc lập.
Trong 48 theta comparisons, độ dịch point lớn nhất khoảng **0,2405** lần block SE
của fit gốc; toàn bộ 38 outputs có cực đại **0,2407**. Probe này chưa đủ để kết luận
folds luôn ổn định hoặc giải thích tín hiệu Y/X của cohort trước.

| Stage | Point fits | Thời gian stage |
|---|---:|---:|
| OLS RCT/null | 200 | 313,41 s |
| DML cost probe, tính vào cohort | 2 | 11,12 s |
| DML RCT/null remainder | 38 | 165,44 s |
| DML 4/10-fold sensitivity | 12 | 67,48 s |

Stages có phần chạy song song; không cộng các thời gian trên thành wall time.
Probe DML từng job mất 4,51/2,66 s, dưới guard 30 s đã đóng băng.

## Bằng chứng và việc còn lại

[Plan](../../../../artifacts/research/20261011/results/score_inference/development_plan.json),
[summary](../../../../artifacts/research/20261011/results/score_inference/summary.csv),
[18.240 main output rows](../../../../artifacts/research/20261011/results/score_inference/seed_metrics.csv),
[paired block/day comparison](../../../../artifacts/research/20261011/results/score_inference/paired_methods.csv),
[fold sensitivity](../../../../artifacts/research/20261011/results/score_inference/fold_sensitivity.csv),
[audit](../../../../artifacts/research/20261011/results/score_inference/audit.json),
[source snapshot](../../../../artifacts/research/20261011/results/score_inference/source_snapshot.zip) và
[checksums](../../../../artifacts/research/20261011/results/score_inference/evidence_checksums.json) giữ protocol/status,
252 job records, covariance, fold maps và source/config/environment identities.
Raw per-block influence files ở các output roots `.cache/week2-score-*-20261011`,
được registry của từng stage kiểm tra hashes; không đưa các files lớn này vào Git.

Đối chiếu độc lập đã tính lại covariance từ block influence/day sums, baseline
truth từ fixed context, mọi endpoint, coverage/FP flags, exact binomial bounds,
matched RMS-SE/SD, dataset pairing và đầy đủ disjoint folds. Snapshot source mới
chỉ thêm capture residuals opt-in; lịch sử, numerical point và production
percentile intervals được giữ nguyên. Seed 45001–45100 chưa chạy.

Nhánh chẩn đoán đã hoàn thành. Undercoverage của mọi đầu ra chưa được giải quyết;
đặc biệt cần tiếp tục kiểm tra joint scenario/baseline uncertainty trước khi chọn
method, đóng băng final protocol và chạy cohort độc lập. GSM chưa có dữ liệu,
X/Y vẫn là hai dịch vụ giả định.

Kiểm tra phần code liên quan đạt **38 tests**; toàn bộ phần không có AppTest đạt
**399 tests**, với hai Pandas FutureWarnings ở fixtures của controller trước.
Ruff, ty và diff check đạt. Lượt toàn repo bị dừng khi bài AppTest đầu tiên
không hoàn tất; [JSON report](../../../../artifacts/research/20261011/score_inference_diagnostic.json) giữ trạng thái
kiểm tra. Không coi lượt bị dừng là đạt, chưa xác nhận phần giao diện.
