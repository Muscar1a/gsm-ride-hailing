# Hồ sơ báo cáo PoC GSM

Mỗi kỳ báo cáo lưu theo ngày tại `docs/submission/days/YYYYMMDD/`, dùng ngày
chốt theo Asia/Bangkok. Hồ sơ mới gồm **hai tài liệu cần nộp**:

- `weekly_report.md`: báo cáo PoC theo **Problem, Approach, Method, Current data,
  Experiment, Reference**. Mỗi nhóm thực nghiệm nêu câu hỏi kiểm chứng,
  kết quả, ý nghĩa và giới hạn kết luận.
- `progress_update.md`: cập nhật tiến độ ngắn, phần mới so với kỳ trước,
  vướng mắc và bước tiếp theo; trỏ tới báo cáo PoC để xem số liệu chi tiết.

Kỳ có điều chỉnh thiết kế có thể dùng bố cục riêng để giải thích cách hiểu
ban đầu, lý do điều chỉnh, thiết kế mới và phạm vi kế thừa kết quả. Báo cáo
[11/10](days/20261011/weekly_report.md) theo bố cục này; vẫn giữ dữ liệu,
phương pháp, kết quả kiểm chứng và nguồn tham chiếu.

| Ngày / kỳ | Báo cáo PoC | Báo cáo tiến độ | Hồ sơ |
|---|---|---|---|
| 11/10/2026 — tổng hợp công việc 10–11/10 | [weekly_report.md](days/20261011/weekly_report.md) | [progress_update.md](days/20261011/progress_update.md) | [README](days/20261011/README.md) |
| 07/10/2026 — Week 2 cập nhật | [weekly_report.md](days/20261007/weekly_report.md) | [progress_update.md](days/20261007/progress_update.md) | [README](days/20261007/README.md) |
| 04/10/2026 — bản đã nộp | [POC_Technical_Report.md](days/20261004/POC_Technical_Report.md) | [Progress_Update.md](days/20261004/Progress_Update.md) | [README và phân công cá nhân](days/20261004/README.md) |

Trạng thái kỹ thuật cập nhật **11/10/2026, Asia/Bangkok**: có gói choice độc lập
và saved-model replay theo [kiểm chứng bàn giao](days/20261011/choice_handoff_verification.md).
Compute reporting và số liệu chốt **07/10/2026 17:13:28** giữ nguyên.
[Chẩn đoán mới](days/20261011/support_interval_diagnostic.md) xác định phạm vi
thu hẹp đủ support bằng dữ liệu huấn luyện, giữ 67,5% trọng số phiên; toàn bộ
bối cảnh và interval calibration mọi đầu ra còn mở.
[So sánh phương pháp interval](days/20261011/interval_method_comparison.md)
ghi nhánh development percentile/basic/BCa, tách khỏi phương pháp production
và final evaluation lịch sử.
[Sensitivity variance](days/20261011/interval_variance_comparison.md) tái sử dụng
jackknife theo ngày đã lưu, không thêm fit hoặc bằng chứng độc lập.
[Pilot DML](days/20261011/dml_variance_pilot.md) áp dụng day-jackknife t trên
seeds mới, ghép cặp với adjusted OLS; đây là development nhỏ. Calibration
mọi đầu ra vẫn mở. [Chẩn đoán score](days/20261011/score_inference_diagnostic.md)
bổ sung cohort mới lớn hơn, covariance theo block/ngày, kiểm chứng riêng
elasticity/scenario và độ nhạy folds; vẫn là development evidence C.
[Báo cáo xử lý CI và tín hiệu](days/20261011/week2_inference_closeout.md) bổ sung
oracle variance audit không refit và assessment độc lập 400/400 fits trên seeds
45001–45100, cùng 410 tests đạt. Tám dòng cảnh báo coverage riêng vẫn giữ nguyên;
không có Holm rejection không chứng nhận coverage 95% cho mọi output. Methods
được Bun chọn tích hợp theo [phương án hybrid](days/20261011/week2_hybrid_acceptance.md):
**Technical exception accepted, 11/10/2026**. Giữ `Technically stable` và cảnh báo
88–89%; full-context support, calibration mọi đầu ra và nghiệm thu GSM còn mở.

Hồ sơ 04/10 đã nộp theo xác nhận được ghi trong hồ sơ; các báo cáo/PDF giữ mốc
lịch sử. Hồ sơ 11/10 là báo cáo kỳ gần nhất, tổng hợp công việc ngày 10–11/10
và bằng chứng kỹ thuật, cùng nghiệm thu Week 2 với ngoại lệ đã ghi ở hồ sơ hybrid.
Kết quả đo cũ và run artifacts được đối chiếu qua [validation lịch sử](days/20261003/validation.md).
Mỗi bản mới ghi người thực hiện, tuần công việc, phiên bản và thời điểm chốt;
tiến độ thực thi tách khỏi nghiệm thu. Phần kỹ thuật chi tiết dẫn sang
[protocol và lệnh tái lập](../BENCHMARK.md#5-reproducing-week-2-benchmarks) và manifests.
Tiến độ hiện tại và công việc còn lại nằm trong [danh mục docs](../README.md)
và [roadmap](../ROADMAP.md).

README của gói kết quả được cập nhật đường dẫn và kết luận rà soát ngày 08/10;
manifest lưu hash gốc và checksum hiện hành. Metrics, frozen source, archive
tái lập, audit thống kê và PDF lịch sử giữ nguyên.
