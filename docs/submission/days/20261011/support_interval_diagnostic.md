# Chẩn đoán support và khoảng tin cậy — 11/10/2026

**Phạm vi:** X/Y vẫn là hai dịch vụ giả định; dữ liệu semi-synthetic, evidence C.
GSM chưa bàn giao dữ liệu. Đã triển khai công cụ chẩn đoán, replay một phạm vi
đủ support và chạy development seeds mới. Chưa đổi phương pháp khoảng tin cậy
hoặc nghiệm thu calibration 95%.

## 1. Support: phạm vi có thể sử dụng

Nguồn là gói `week2-choice-handoff-20261011-v2`, giữ mô hình DML của
`20261003T130951-df24a7e4`. Kịch bản giữ giá ban đầu X/Y bằng 1, tăng X 10%,
giữ Y không đổi. Ngưỡng vẫn là **20 block huấn luyện** cho từng tổ hợp giá và
nhóm zone × weekend × peak; kiểm tra conditioning giữ nguyên.

`diagnose_week2_support.py` ghi bảng counts và quyết định phạm vi từ
`train_support` trước khi đọc contexts đánh giá. Không dùng kết quả lựa chọn,
oracle, độ rộng khoảng hoặc kết quả forecast để chọn nhóm. Nhóm chưa thấy trong
huấn luyện bị loại với mẫu số riêng.

| Mục | Kết quả |
|---|---:|
| Nhóm training đủ support ở cả baseline và target | 10/20 |
| Context blocks giữ / toàn bộ | 972/1.440 |
| Trọng số quote sessions giữ / toàn bộ | 48.600/72.000 — **67,5%** |
| Blocks / sessions loại ra | 468 / 23.400 |
| Replay toàn bộ bối cảnh | `insufficient_support`, khớp nguyên kết quả trước chẩn đoán |
| Replay phạm vi giữ lại | `status=ok`, `support_status=ok` |

Phạm vi giữ lại gồm cả năm vùng ngoài cao điểm ngày thường; bốn vùng trong
cao điểm ngày thường (loại vùng 162); chỉ vùng 162 ngoài cao điểm cuối tuần.
Không nhóm cao điểm cuối tuần nào đủ support.

| Bối cảnh | Sessions giữ / toàn bộ |
|---|---:|
| Ngày thường, ngoài cao điểm | 34.000/34.000 |
| Ngày thường, cao điểm | 11.200/14.000 |
| Cuối tuần, ngoài cao điểm | 3.400/17.000 |
| Cuối tuần, cao điểm | 0/7.000 |

Forecast giả định 10.000 quote sessions **trong phạm vi giữ lại**, với trọng số
bối cảnh tương ứng. Không áp dụng tỷ lệ này cho toàn thị trường hoặc xem 67,5%
là coverage dữ liệu GSM. Support đạt không xác nhận calibration của khoảng.
Muốn sử dụng toàn bộ phạm vi cần bổ sung training coverage rồi fit/kiểm chứng
mới; không chuyển trạng thái all-context thành đạt.

Run cuối là `week2-support-diagnostic-20261011-v3`. Sáu artifacts được đăng ký
checksum; 20 artifacts của gói nguồn và manifest được kiểm trước load model,
kiểm lại sau replay và giữ nguyên byte. Bằng chứng nhỏ được lưu trong
[support](../../../../artifacts/research/20261011/results/support_interval/support); contexts/model bundles ở run
cục bộ theo manifest.

## 2. Chẩn đoán khoảng lịch sử

Đối chiếu lại 500 checkpoints, 6.000 coefficient rows và 60 ô tổng hợp; nguồn
báo cáo 07/10, archive và kiểm chứng thống kê cũ giữ nguyên. Các mẫu số và
checksum được kiểm lại; không fit lại trên final seeds 20001–20100.

| RCT Y/Y, 100 seeds | Adjusted OLS | DML |
|---|---:|---:|
| Bias | +0,00130 | +0,00169 |
| Sample SD giữa seeds | 0,01260 | 0,01263 |
| Độ rộng khoảng trung bình | 0,04023 | 0,04205 |
| SE xấp xỉ từ độ rộng / SD thực | 81,5% | 84,9% |
| Khoảng chứa truth | 86/100 | 86/100 |
| Khoảng nằm trên / dưới truth | 6 / 8 | 7 / 7 |

SE xấp xỉ là `mean_width / (2 × 1,96)`, **không phải SD bootstrap đã đo**.
Reporting cũ không lưu raw draws. Bias nhỏ và misses ở hai phía gợi ý uncertainty
quá hẹp; chưa xác định cơ chế chỉ từ bảng này. Exact binomial 95% interval cho
coverage 86/100 vẫn là **[77,63%; 92,13%]**.

[Hồ sơ lịch sử mới](../../../../artifacts/research/20261011/results/support_interval/historical) giữ source chẩn đoán,
CSV, JSON và audit/checksums. Source chạy được vào thư mục kết quả mới; từ chối
ghi đè bằng chứng đã xuất bản. Cấu hình model/source/simulation/evaluation
lịch sử và hiện tại giống nhau: 50 cây, năm folds, 20 ngày train,
30 phút/block, 50 sessions/block, năm vùng và min cell 20.

## 3. Development có raw draws

Protocol được ghi trước khi generate; fresh seeds **41001–41020**, ngoài final
seeds cũ. Giữ nguyên training context, fit và individual day-bootstrap percentile
95%. Chọn adjusted OLS để kiểm tra phần uncertainty dùng chung; kiểm tra riêng
một seed DML với cấu hình nuisance gốc. Oracle chỉ được dùng ở evaluator.

| Nhóm chạy | Jobs | Requested/successful refits | Wall time |
|---|---:|---:|---:|
| Adjusted OLS, RCT + NULL, 20 seeds mỗi DGP, 199 draws | 40/40 | 7.960/7.960 | 468,77 giây |
| Adjusted OLS, RCT seeds 41001–41003, 999 draws | 3/3 | 2.997/2.997 | 206,73 giây |
| DML, RCT seed 41001, 199 draws | 1/1 | 199/199 | 500,95 giây |

Các nhóm chạy song song; không cộng wall time thành elapsed tổng. Lượt đo chi
phí một seed adjusted OLS mất 10,79 giây cho fit/bootstrap, được lặp trong nhóm
development. Lượt kiểm chứng công cụ cuối lặp cùng seed để đối chiếu; cả hai
probe không được cộng vào mẫu số independent seeds.

| Ô RCT adjusted OLS, n=20 | SD giữa seeds | RMS SD bootstrap thực | Tỷ số bootstrap/thực | Coverage |
|---|---:|---:|---:|---:|
| Y/Y | 0,012540 | 0,010731 | **85,6%** | 18/20 |
| Y/X | 0,013781 | 0,010865 | **78,8%** | 16/20 |

SD bootstrap tính trực tiếp từ hệ số draws, `ddof=1`; RMS lấy căn trung bình
bình phương các SD theo seed. Đây là chẩn đoán variability, không dùng width
để suy ra SD. Exact binomial 95% interval cho Y/Y 18/20 là **[68,30%; 98,77%]**;
20 seeds chưa đủ chứng minh calibration 95%. Không gộp với final seeds cũ hoặc
coi 18/20 là cải thiện phương pháp: phương pháp chưa đổi.

NULL có false positives **1/20, 1/20, 2/20, 2/20** theo X/X, X/Y, Y/X, Y/Y;
uncertainty còn rộng. DML probe có 199 draws thành công nhưng một seed không
đo được SD giữa seeds hay coverage quần thể. Kết quả từng ô và mẫu số đầy đủ
nằm trong CSV của [development](../../../../artifacts/research/20261011/results/support_interval/development),
[endpoints](../../../../artifacts/research/20261011/results/support_interval/endpoints) và
[DML probe](../../../../artifacts/research/20261011/results/support_interval/dml_probe).

So sánh 199/999 dùng **cùng 199 requested draws đầu**, kiểm cả hệ số và nhóm
ngày; không chọn 199 draws thành công sau khi bỏ failures. Trong ba seeds,
độ rộng Y/Y trung bình tăng khoảng **2,3%**, đầu mút thay đổi lớn nhất khoảng
0,00284 probability/log-price. Tăng draws ảnh hưởng đầu mút nhưng chưa có bằng
chứng rằng riêng tăng draws xử lý được undercoverage. Số ngày train và cách
dựng khoảng vẫn là giả thuyết, chưa phải nguyên nhân được cô lập.

## 4. Công cụ, kiểm chứng và tái lập

Hai scripts tái sử dụng fit, bootstrap, scenario, support và artifact helpers
hiện có. Không sửa công thức mô hình, resampling hoặc khoảng percentile.
Protocol/config/environment, source context hashes và per-job artifacts được
giữ cùng raw coefficient draws trong `.cache/week2-ci-*`. Raw draws/models
không đưa vào Git; hồ sơ này lưu summaries, protocols, statuses và checksums.

Đã sửa trường hợp metric lỗi sau bootstrap: raw draws và số failures vẫn được
giữ, nhưng tỷ số SD unavailable khi cohort seeds có estimate và cohort có SD
bootstrap không khớp. Có trạng thái riêng cho thiếu replicates và zero variance.
Snapshot controller thực thi được giữ trong
[executed_interval_runner.py](../../../../artifacts/research/20261011/results/support_interval/executed_interval_runner.py).
Sau sửa validation/type, summary không có failures được đối chiếu giữ nguyên;
lượt 199-draw cuối kiểm lại point estimates, bounds và raw coefficients đúng
với baseline. Phiên bản controller tách khỏi source hash của phương pháp.

- **100 kiểm thử liên quan đạt**, gồm support, diagnostic statistics,
  generation/day folds, estimation, failure handling và choice handoff.
- Ruff lint, format bốn tệp script/test mới và `ty 0.0.82 --error-on-warning`
  cho hai scripts đạt. Không format toàn repo.
- Kiểm checksum mọi run hoàn tất, SD từ raw draws, coverage flags, prefix 199,
  nguồn choice bất biến và cohort comparison sau sửa đều đạt.

[Đối chiếu JSON](../../../../artifacts/research/20261011/support_interval_diagnostic.json) ghi run/protocol/code/lock
identities và kết quả assertions; [checksums hồ sơ](../../../../artifacts/research/20261011/results/support_interval/evidence_checksums.json)
giữ hashes của bằng chứng đã xuất bản. Lệnh chạy nằm trong
[USAGE](../../../USAGE.md#week-2-support-and-interval-diagnostics).

## 5. Kết luận và phần còn mở

**Support đã giải quyết cho phạm vi thu hẹp được công bố**, chưa cho toàn bộ
bối cảnh. **Chẩn đoán interval đã triển khai và có bằng chứng mới** về mức
variability bootstrap thấp ở các ô Y; chưa cô lập được nguyên nhân hoặc sửa
calibration. Statistics gate và nghiệm thu Week 2 vẫn mở.

Bước tiếp theo là phát triển/so sánh cách inference phù hợp trên development,
giữ phương pháp hiện tại làm baseline, chốt phương pháp cùng tiêu chí trước
khi chạy final seeds độc lập. Không tune lại final seeds 20001–20100, không
tự nới khoảng hoặc đổi ngưỡng nghiệm thu từ kết quả đã thấy. Dữ liệu và xác
nhận nghiệp vụ GSM vẫn cần trước khi kết luận về thị trường thực.
