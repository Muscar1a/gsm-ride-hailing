# Hồ sơ cập nhật PoC — 07/10/2026

**Nguyễn Thành An · Week 2 · Chốt compute 17:13:28, Asia/Bangkok (UTC+07).**
Rà soát thống kê ngày 07/10; chưa có xác nhận nghiệm thu đầy đủ.

| Tài liệu | Mục đích |
|---|---|
| [weekly_report.md](weekly_report.md) | Báo cáo theo Problem → Approach → Method → Current data → Experiment → Reference; gắn kết quả với câu hỏi kiểm chứng và ý nghĩa |
| [progress_update.md](progress_update.md) | Báo cáo tiến độ ngắn: đã làm, bổ sung, phần thiếu và kế hoạch |
| [acceptance_review.md](acceptance_review.md) | Tài liệu đối chiếu nội bộ: sáu gate, metrics theo ô, run IDs/checksums và việc còn lại |
| [statistical_review.md](statistical_review.md) | Rà soát đủ 500 jobs: point accuracy, coverage/null, draws, stress cases và kết luận calibration |
| [results/week2/README.md](results/week2/README.md) | Kết quả compute cuối 500/500 job, bảng metrics, checkpoint archive và checksum |

Nguồn đối chiếu là các file Markdown của [hồ sơ 04/10](../20261004/README.md),
lịch sử Git ngày 05–06/10, thay đổi cục bộ ngày 07/10 và artifacts đã kiểm tra.
Kết quả cũ giữ đúng run/profile/ngày đo; bổ sung Swissmetro, policy-value và coverage ghi
riêng. Hai báo cáo dùng cùng mốc compute cuối; kết luận rà soát được ghi riêng
với timestamp trong audit JSON, không gán kết quả mới cho run lịch sử.

Các đợt củng cố đã commit: `6f5fea6`, `336658f`, `574cf50` (06/10).
HEAD trước đợt rà soát là `354fc04`; các outputs được nhận diện bằng manifest/
source hashes lúc chạy. Đợt soạn đọc nội dung Markdown của hồ sơ cũ; các tệp
đính kèm được giữ khi chuyển thư mục.

**Kết quả compute và rà soát:** giao thức 500/500 seed jobs đã hoàn
tất lúc **17:13:28 ngày 07/10/2026 (UTC+07)**. Bản lưu kết quả cuối nằm tại
[results/week2](results/week2/README.md), ngoài `.cache`, gồm metrics tổng hợp,
chi tiết, metadata, checkpoint archive và SHA-256. Hai báo cáo đã đồng bộ kết
quả cuối. RCT point accuracy đạt; Y/Y adjusted OLS/DML coverage 86/100 nên
chưa nghiệm thu calibration vô điều kiện. Rà soát đủ 60 ô/checkpoints nằm trong
[statistical_review.md](statistical_review.md), với bằng chứng bổ sung trong
`results/week2/statistical_review`; không sửa gói kết quả gốc.

[Danh mục hồ sơ](../../README.md) · [Validation lịch sử](../../../VALIDATION.md) ·
[Run/resume week 2](../../../WEEK_2_BENCHMARKS.md)

## Điều kiện chốt bản final và nghiệm thu đầy đủ week 2

Phạm vi nghiệm thu là PoC demand/choice trên public/synthetic data, evidence C,
theo [kế hoạch week 2–3](../../../task/GSM_POC_WEEK_2_CLOSEOUT_WEEK_3_PLAN.md).
Cung/simulator, hiệu chỉnh GSM và ROI thuộc các bước sau.

| Gate | Bằng chứng hiện có | Cần có khi chốt final |
|---|---|---|
| Data | TLC đối soát, train-only context; Swissmetro schema/units/splits/source manifest; EPFL nêu sử dụng nghiên cứu/giáo dục | Provenance Swissmetro đủ căn cứ cho PoC học thuật; giữ nguồn trích dẫn và giới hạn tái phân phối/sử dụng thương mại |
| Effect | OLS/DML recovery trong các run đã ghi, kiểm tra rank/support và nhiễu ẩn | Kết luận các DGP áp dụng trên profile reporting; không xem stress-case bias là bảo đảm nhận dạng |
| Scenario | Baseline học từ dữ liệu, log-price, kiểm tra hỗ trợ/xác suất, không oracle | Bundle cuối và scenario exports tương thích với config/scope/code được chốt |
| Reproducibility | Snapshot/config/lock/seeds/checksum đã đối chiếu; policy và Swissmetro chạy lại/dùng lại outputs đã xác minh | Bundle/model/effects/scenario/manifests hoàn chỉnh và một rerun/resume tương ứng với bộ bàn giao cuối |
| Statistics | Đủ 500 jobs, 238.800/238.800 refits; rà soát bias/RMSE/coverage/null/binomial intervals và stress cases hoàn tất | Giữ hạn chế coverage RCT Y/Y 86/100; cần kết luận hoặc ngoại lệ được người nghiệm thu chấp nhận, không tự đặt ngưỡng pass sau khi thấy kết quả |
| Additional benchmarks | Swissmetro đạt kỹ thuật; policy-value development đủ 40 seed jobs, chọn validation/chấm oracle test độc lập, giữ uplift âm và fallback | Đã có báo cáo development; giữ giới hạn evidence C, lưới hỗ trợ, quyền sử dụng dữ liệu và uncertainty qua seeds |

Policy benchmark phải khai báo normalized fares/owned services, dùng cùng grid
0,90/1,00/1,10 và báo cáo gross booking value trên 1.000 quote sessions,
uplift/regret/paired differences/fallbacks/failures/runtime. Kết quả có thể bằng
0 hoặc âm; không dùng evaluator của chính learner để tự chấm và không gọi đây
là doanh thu GSM.

Contract đã định RCT theta RMSE ≤0,10, scenario probability RMSE ≤0,02 và gắn
cờ bootstrap draw failures >5%. Coverage/null cần binomial intervals và mẫu số
rõ ràng; nominal 95% không tự chứng minh calibration. Hoàn tất chạy là điều
kiện để rà soát thống kê, không tự động làm các gate đạt.

Tại mốc cuối **07/10/2026 17:13:28 (UTC+07)**: **500 jobs thành công**, 0 lỗi
cuối, 0 còn lại, 100 batch hoàn tất. Collinear không nhận dạng là kết quả kiểm
tra giới hạn, không phải lỗi compute. Hai báo cáo dùng cùng kết quả đã rà soát.
Giao thức coverage, seeds, source và checkpoint giữ nguyên trong đợt rà soát.

## Sửa phần nào và điền gì khi chốt hồ sơ

| Vị trí | Nội dung cần chốt | Nguồn để điền |
|---|---|---|
| `weekly_report.md`, mục 1–4 | Problem, Approach, Method và Current data: câu hỏi giá, thiết kế kiểm chứng, phương pháp và phạm vi dữ liệu | Proposal, data contract và bằng chứng đã kiểm tra |
| Mục 5.1–5.4 | 500 jobs, recovery, coverage/null và stress cases; nêu câu hỏi, kết quả và ý nghĩa; còn kết luận calibration của người nghiệm thu | Kết quả cuối và statistical_review.md, không điền số ước đoán |
| Mục 5.5 | Kịch bản lịch sử X/Y/NONE và ý nghĩa outside option | Run 03/10 giữ nguyên provenance, không gán cho lượt chạy mới |
| Mục 5.6 | Swissmetro và ý nghĩa dự báo trên người chưa thấy; giữ giới hạn nguồn/causal evidence | [EPFL/Biogeme, mục Data](https://biogeme.epfl.ch/) và run/source manifests |
| Mục 5.7 | Value/uplift/regret, paired intervals, fallback/failures và ý nghĩa quyết định giá | `runs/week2-policy-final-32001-32020/policy/`; chỉ là benchmark development |
| Mục 5.8 và 6 | Vấn đề đã xử lý/phần còn lại và Reference: nguồn, bundle/run IDs/hashes/config/seeds/lệnh tái lập | Hồ sơ nghiệm thu và manifests tương ứng |
| `progress_update.md` | Đã đồng bộ mốc compute cuối và kết luận rà soát; còn cập nhật bundle/nghiệm thu khi có bằng chứng | Tóm tắt từ báo cáo PoC, không dùng số khác kỳ |

Thông tin cá nhân đã có. Người thực hiện cần chốt **hạn nộp thực tế**, **người
kiểm tra/ngày nghiệm thu kỹ thuật**, và **kết luận hoặc ngoại lệ được chấp nhận**.
Không tự ghi thầy đã duyệt khi chưa có phản hồi. Các số liệu kỹ thuật lấy từ
thực nghiệm; người thực hiện không cần tự tính hoặc điền giả các chỉ số đang thiếu.

Thứ tự còn lại: chốt hạn chế calibration → kiểm tra bundle/tái lập
→ xác nhận sáu gate và điền thông tin nghiệm thu thực tế.
