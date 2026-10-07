# Rà soát thống kê Week 2 — kết quả cuối 500 job

**Mốc dữ liệu: 07/10/2026 17:13:28, Asia/Bangkok (UTC+07).**
Rà soát ngày 07/10; thời điểm và phiên bản mã rà soát lưu trong
[audit.json](results/week2/statistical_review/audit.json).

**Kết luận:** đủ giao thức và dữ liệu nhất quán; point accuracy RCT đạt hai ngưỡng
đã định. Calibration của khoảng 95% còn hạn chế: adjusted OLS và DML ở ô RCT
Y/Y chỉ bao phủ **86/100 seed**. Vì vậy chưa đủ căn cứ nghiệm thu thống kê vô điều
kiện. Kết quả này hoàn tất việc rà soát, không thay thế xác nhận của người nghiệm thu.

## 1. Tính toàn vẹn và mẫu số

Đã xác minh 13 SHA-256 của gói gốc, CRC archive, 500 checkpoint JSON và SHA-256
của 500 checkpoint parquet. Toàn bộ checkpoint rows khớp bảng pooled; tính lại
các trường thống kê số của **60 ô** khớp CSV ở sai số tuyệt đối ≤1e−12.
Khoảng binomial được kiểm tra độc lập bằng beta quantiles.

| Hạng mục | Kết quả |
|---|---:|
| Seed jobs yêu cầu / thành công / thất bại | 500 / 500 / 0 |
| Seed mỗi DGP; batch hoàn tất | 100; 100/100 |
| Seed reporting | 20001–20100; loại probe 19001 |
| Coefficient rows; ô tổng hợp | 6.000; 60 |
| Estimator fits có hệ số hợp lệ | 1.200 |
| Fits bị từ chối ở COLLINEAR_PRICE | 300; giữ 1.200 rows với estimates/intervals N/A |
| Bootstrap refits yêu cầu / thành công / thất bại | 238.800 / 238.800 / 0 |
| Invalid baseline draws; invalid scenarios ở fits hợp lệ | 0; 0/1.200 |

Mỗi ô DGP/estimator/outcome/price có **100 seed**, không gộp bốn ô hệ số hoặc ba
estimators thành các quan sát độc lập. Mỗi fit tạo bốn coefficient rows, nên
không cộng draws trên bốn rows để tính tổng refits. Một ô hợp lệ có 19.900
requested/successful draws; fits không nhận dạng không chạy bootstrap.
`failed_or_unidentified_estimates` trong CSV gộp hai trạng thái: 100 ở mỗi ô
collinear là **không nhận dạng**, không phải 100 lỗi compute.

Đã kiểm tra khóa đầy đủ/không trùng, finite values, `error = theta − truth`,
squared errors, thứ tự interval bounds, coverage và NULL_EFFECT false-positive
flags; giữ missing khác zero. Các fits hợp lệ đều có `interval_status=ok`;
trạng thái này chỉ xác nhận đủ draws và kiểm tra kỹ thuật, không chứng minh
coverage đạt nominal 95%.

## 2. Bias, RMSE và kịch bản

Theta có đơn vị probability/log-price. Bias là trung bình sai số; theta RMSE
là căn bậc hai trung bình squared errors qua 100 seed, theo từng ô.
Scenario RMSE là **căn trung bình bình phương của các per-seed scenario RMSE**,
không phải trung bình số học. Kịch bản được đánh giá trên frozen test contexts.
Max và min–max trong bảng là qua bốn ô hệ số, không phải confidence intervals.

| DGP | Estimator | Max absolute bias | Max theta RMSE | Scenario RMSE | Coverage theo ô |
|---|---|---:|---:|---:|---:|
| RCT | naive_ols | 0,001489 | 0,012475 | 0,003637 | 90–96% |
| RCT | adjusted_ols | 0,001300 | 0,012603 | 0,003591 | 86–95% |
| RCT | dml | 0,001695 | 0,012680 | 0,003602 | 86–94% |
| Observed confounding | naive_ols | 0,129793 | 0,130368 | 0,016680 | 0–4% |
| Observed confounding | adjusted_ols | 0,001727 | 0,012319 | 0,003758 | 89–96% |
| Observed confounding | dml | 0,003463 | 0,012798 | 0,003777 | 89–95% |
| NULL_EFFECT | naive_ols | 0,002045 | 0,012574 | 0,003653 | 92–95% |
| NULL_EFFECT | adjusted_ols | 0,001834 | 0,011479 | 0,003608 | 92–94% |
| NULL_EFFECT | dml | 0,002136 | 0,011758 | 0,003617 | 92–95% |
| Hidden confounding | naive_ols | 0,130073 | 0,130618 | 0,021053 | 0% |
| Hidden confounding | adjusted_ols | 0,025143 | 0,027836 | 0,013850 | 41–67% |
| Hidden confounding | dml | 0,025052 | 0,027878 | 0,013877 | 43–67% |

**RCT đạt** ngưỡng theta RMSE ≤0,10 ở toàn bộ 12 ô và scenario RMSE ≤0,02 ở cả
ba estimators. Adjusted OLS/DML giảm mạnh bias của naive OLS trong observed
confounding; DML không cần thắng adjusted OLS để chứng minh recovery ở DGP
additive này. Không áp hai ngưỡng RCT cho mọi stress case để gọi chúng đạt.

## 3. Coverage 95%

Mỗi dòng dưới có 100 valid estimates/intervals, 0 fit hoặc interval failure.
Các bounds là **Clopper–Pearson hai phía 95%**, theo từng ô, chưa hiệu chỉnh
đa so sánh; individual intervals không phải joint 95% cho cả ma trận.

| RCT estimator | Outcome/price | Bias | RMSE | Covered/100 | Binomial 95% |
|---|---|---:|---:|---:|---|
| adjusted_ols | X/X | 0,000061 | 0,010374 | 91 | [83,60%; 95,80%] |
| adjusted_ols | X/Y | −0,000710 | 0,011335 | 93 | [86,11%; 97,14%] |
| adjusted_ols | Y/X | 0,001223 | 0,009463 | 95 | [88,72%; 98,36%] |
| adjusted_ols | Y/Y | 0,001300 | 0,012603 | **86** | **[77,63%; 92,13%]** |
| dml | X/X | −0,000195 | 0,010649 | 92 | [84,84%; 96,48%] |
| dml | X/Y | −0,000752 | 0,011541 | 93 | [86,11%; 97,14%] |
| dml | Y/X | 0,001360 | 0,009688 | 94 | [87,40%; 97,77%] |
| dml | Y/Y | 0,001695 | 0,012680 | **86** | **[77,63%; 92,13%]** |
| naive_ols | X/X | −0,000347 | 0,012013 | 92 | [84,84%; 96,48%] |
| naive_ols | X/Y | −0,000444 | 0,012427 | 93 | [86,11%; 97,14%] |
| naive_ols | Y/X | 0,000576 | 0,010586 | 96 | [90,07%; 98,90%] |
| naive_ols | Y/Y | 0,001489 | 0,012475 | 90 | [82,38%; 95,10%] |

Chẩn đoán bổ sung **sau khi có kết quả**: kiểm định binomial một phía coverage
<0,95, hiệu chỉnh Holm trên 36 ô RCT/observed/null × ba estimators × bốn hệ số.
Hai ô RCT Y/Y trên có p thô **0,0004633**, p Holm **0,0148247**. Bốn ô naive
OLS ở observed cũng có p Holm <0,05, phù hợp baseline bị confounding.
Observed Y/Y của adjusted OLS/DML có coverage 89% và khoảng [81,17%; 94,38%];
p thô 0,01147 nhưng p Holm 0,34417: cần ghi nhận, không kết luận thêm từ riêng
ô được chọn. Chi tiết đầy đủ trong [cell_metrics.csv](results/week2/statistical_review/cell_metrics.csv).

Family kiểm định và mức chẩn đoán 0,05 được chọn ở bước rà soát, **không phải
acceptance rule đăng ký trước**. Holm xử lý việc nhìn nhiều ô ở lần rà soát
cuối, không hiệu chỉnh việc theo dõi tiến độ lặp lại trước đó. Protocol giữ
100 seed cố định, không dừng sớm theo kết quả. Binomial inference giả định
các seed độc lập có điều kiện trên bối cảnh đóng băng; các ô/estimators/DGP
có thể phụ thuộc nhau. Không suy rộng sang quần thể GSM hoặc uncertainty do
chọn context. Protocol ghi nominal coverage và exact intervals, chưa đóng
băng một equivalence/tolerance band: không đặt lại ngưỡng pass từ kết quả này.

## 4. NULL_EFFECT

Truth bằng 0; false positive là individual 95% interval không chứa 0.
Mỗi ô có **100 null seed**, không gộp các ô thành n=1.200.

| Estimator | X/X | X/Y | Y/X | Y/Y |
|---|---:|---:|---:|---:|
| adjusted_ols | 6/100 | 8/100 | 8/100 | 8/100 |
| dml | 7/100 | 7/100 | 5/100 | 8/100 |
| naive_ols | 8/100 | 7/100 | 7/100 | 5/100 |

| False positives | Exact binomial 95% |
|---|---|
| 5/100 | [1,64%; 11,28%] |
| 6/100 | [2,23%; 12,60%] |
| 7/100 | [2,86%; 13,89%] |
| 8/100 | [3,52%; 15,16%] |

Các khoảng đều chứa nominal 5%. Chưa có bằng chứng mạnh về mức dương tính giả
vượt 5% ở các ô null; đây **không chứng minh tương đương 5%** hoặc calibration
đã đạt. Undercoverage test cho null tương đương kiểm định false positives >5%,
không tính chúng thành hai bằng chứng độc lập. Tỷ lệ family-wise “ít nhất một
ô false positive” là estimand khác, không được thay cho tỷ lệ theo ô.

## 5. Stress cases và quyết định nghiệm thu

**HIDDEN_CONFOUNDING:** adjusted OLS/DML vẫn có bias và coverage chỉ 41–67% /
43–67%. Fit có số và đủ bootstrap không bảo đảm nhận dạng nhân quả khi thiếu
confounder. Đây là bằng chứng giới hạn phương pháp, không phải recovery nhân
quả thành công; không loại các seed này để nâng coverage.

**COLLINEAR_PRICE:** cả ba estimators từ chối tách hiệu ứng ở 100/100 seed.
Các estimates, coverage/null rates và scenario RMSE là N/A, denominator 0;
không điền zero. Kết quả phù hợp positive control về phát hiện không nhận dạng.

| Phần nghiệm thu | Kết luận rà soát |
|---|---|
| Giao thức, toàn vẹn, draws/failures | Đạt kỹ thuật; 500 jobs, 0 final compute errors, 0 failed refits |
| RCT point accuracy | Đạt hai ngưỡng đã định |
| Observed confounding | Recovery với adjusted OLS/DML; naive baseline thất bại như kỳ vọng |
| NULL_EFFECT | Đã có đủ kết quả; 5–8% theo ô, uncertainty còn rộng |
| Hidden / collinear | Giữ đúng giới hạn nhân quả và từ chối không nhận dạng |
| Interval calibration / Statistics gate | Rà soát hoàn tất; **chưa nghiệm thu vô điều kiện**, giữ hạn chế RCT Y/Y |

Có thể dùng hồ sơ này để xem xét nghiệm thu có điều kiện với hạn chế interval
calibration được ghi rõ. Người nghiệm thu cần xác nhận kết luận hoặc ngoại lệ
thực tế; chưa có xác nhận đó. Bộ demand/choice bàn giao cuối và kiểm tra tái
lập tương ứng còn là việc riêng của Scenario/Reproducibility gates.

Nếu cải thiện calibration, cần kiểm tra cơ chế resampling theo ngày, xử lý
folds và loại interval trên **development seeds mới**, rồi đóng băng phương
pháp/ngưỡng và đánh giá trên holdout mới. Rà soát này chưa xác định nguyên
nhân undercoverage; không tự quy cho 199 draws hoặc chỉnh tham số trên final
seeds 20001–20100. Chưa thực hiện thêm compute trong đợt rà soát này.

## 6. Bằng chứng và tái lập rà soát

- [Kết quả gốc và manifest](results/week2/README.md) giữ nguyên bytes/hash;
  metadata `pending review` ở gói xuất phản ánh thời điểm xuất trước rà soát.
- [Audit JSON](results/week2/statistical_review/audit.json),
  [60 ô metrics](results/week2/statistical_review/cell_metrics.csv),
  [bảng tổng hợp](results/week2/statistical_review/dgp_estimator_summary.csv) và
  [SHA-256 audit](results/week2/statistical_review/checksums.sha256) là bằng chứng bổ sung.
- [Script rà soát](../../../../scripts/review_week2_statistics.py) chỉ đọc outputs;
  không fit model, không sửa frozen source/config hoặc bảng kết quả gốc.
- Tham chiếu phương pháp: [SciPy binomtest/exact proportion CI](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html),
  [Holm trong tài liệu statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html).
  Rà soát dùng SciPy **1.17.1** đã cài; không thêm dependency.
- Kiểm tra script rà soát: **9 tests passed (1,28 giây)** cho exact intervals,
  Holm/order và invalid inputs; Ruff check/format đạt. Đây là checks của bước
  rà soát, tách khỏi tests lịch sử của model/runner.

```powershell
.venv/Scripts/python.exe scripts/review_week2_statistics.py
```

Snapshot thực nghiệm revision `574cf501304a777827c2e04704d96a1ab563e1b2`,
source `8459df189c1da3d4252f1ac2445854ac684c4ee15cecf951d80cbfd5402648a0`;
revision/script hash của bước rà soát được ghi riêng trong audit JSON.
Runtime từ checkpoint (mean giây/job): RCT **647,25**, observed **1.109,05**,
null **1.092,87**, hidden **979,33**, collinear **1,24**. Đây là metadata các lượt
thực thi với lịch chạy khác nhau, không phải benchmark cấu hình; tổng thời
gian jobs chạy song song không phải elapsed wall-clock. Tất cả kết luận hành
vi ở đây thuộc **semi-synthetic, evidence C**.
