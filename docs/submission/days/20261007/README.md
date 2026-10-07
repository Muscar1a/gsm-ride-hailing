# Hồ sơ cập nhật PoC — 07/10/2026

**Nguyễn Thành An · Week 2 · Chốt 10:41:19, Asia/Bangkok (UTC+07).**

| Tài liệu | Mục đích |
|---|---|
| [weekly_report.md](weekly_report.md) | Báo cáo PoC tổng hợp bản đã nộp 04/10 và phần hoàn thiện hiện tại |
| [progress_update.md](progress_update.md) | Báo cáo tiến độ ngắn: đã làm, bổ sung, phần thiếu và kế hoạch |
| [acceptance_review.md](acceptance_review.md) | Tài liệu đối chiếu nội bộ: sáu gate, metrics theo ô, run IDs/checksums và việc còn lại |
| [results/week2/README.md](results/week2/README.md) | Kết quả compute cuối 500/500 job, bảng metrics, checkpoint archive và checksum |

Nguồn đối chiếu là các file Markdown của [hồ sơ 04/10](../20261004/README.md),
lịch sử Git ngày 05–06/10, thay đổi cục bộ ngày 07/10 và artifacts đã kiểm tra.
Kết quả cũ giữ đúng run/profile/ngày đo; bổ sung Swissmetro, policy-value và coverage ghi
riêng. Hai tài liệu dùng cùng thời điểm chốt. Coverage tiếp tục chạy sau đó;
không suy diễn tiến độ tại thời điểm đọc từ một bản chốt.

Các đợt củng cố đã commit: `6f5fea6`, `336658f`, `574cf50` (06/10).
Phần Swissmetro/policy/runner và báo cáo mới chưa commit. Đợt soạn này đọc nội dung
Markdown của hồ sơ cũ; các tệp đính kèm được giữ khi chuyển thư mục.

**Cập nhật compute sau mốc chốt báo cáo:** giao thức 500/500 seed jobs đã hoàn
tất lúc **17:13:28 ngày 07/10/2026 (UTC+07)**. Bản lưu kết quả cuối nằm tại
[results/week2](results/week2/README.md), ngoài `.cache`, gồm metrics tổng hợp,
chi tiết, metadata, checkpoint archive và SHA-256. Hai báo cáo ở trên vẫn giữ
mốc chốt 10:41:19; cần đồng bộ sau khi rà soát nghiệm thu thống kê.

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
| Statistics | Coverage runner đang chạy | Đủ 100 seeds/DGP × 5 DGP; 199 draws/estimator được nhận dạng; bias/RMSE/coverage/null/binomial intervals/counts/failures; đánh giá kết quả theo contract |
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

Kiểm tra tiến độ lúc **07/10/2026 10:41:19 (UTC+07)**: **69 jobs thành công**,
**1 đang chạy** (job 70, RCT seed 20070), không có seed job thất bại, **430 chưa
bắt đầu**. Thời gian trung bình 69 jobs đã xong là **516,41 giây/job**. Bảng
tổng hợp đã có **65 seed RCT**; bốn seed đã xong trong batch đang chạy còn ở
checkpoint. Hai báo cáo dùng cùng snapshot; cần chốt lại sau khi đủ giao thức.

Tối ưu compute tiếp tục ở chat riêng. Giao thức coverage, seeds và checkpoint
giữ nguyên trong đợt này. Không giảm seed/draw rồi ghi là nghiệm thu đủ giao thức.

## Sửa phần nào và điền gì khi chốt hồ sơ

| Vị trí | Nội dung cần chốt | Nguồn để điền |
|---|---|---|
| `weekly_report.md`, mục 1 và 3 | Thời điểm chốt thực tế; kết luận từng gate Data/Effect/Scenario/Reproducibility/Statistics/Additional benchmarks | Bảng nghiệm thu và bằng chứng đã kiểm tra; phần chưa đủ giữ trạng thái chờ |
| Mục 5.3 | Đã bổ sung căn cứ EPFL cho nghiên cứu/giáo dục và chạy lại Swissmetro trên mã cuối; giữ giới hạn còn tồn tại | [EPFL/Biogeme, mục Data](https://biogeme.epfl.ch/) và hồ sơ nguồn/SHA-256; run cũ giữ nguyên, run closeout có manifest riêng |
| Mục 5.4 | Số seed yêu cầu/thành công/lỗi/không nhận dạng; draws; bias/RMSE/coverage/null và binomial intervals; runtime; kết quả checks cuối | Artifact/checkpoint/pooled metrics và log kiểm tra, không điền số ước đoán |
| Mục 5.5 | Đã điền value/uplift/regret, paired intervals, fallback/failures và cách chọn/chấm policy | `runs/week2-policy-final-32001-32020/policy/` và manifest đã kiểm tra; chỉ là benchmark development |
| Mục 6 và phụ lục | Chuyển việc week 2 đã đạt thành kết quả; giữ việc còn thiếu; bundle/run IDs/code hash/config/seeds/checksums/lệnh tái lập cuối | Bundle và manifests tương ứng với kết quả cuối |
| `progress_update.md` | Cùng thời điểm chốt; đồng bộ đoạn bổ sung, tiến độ/phần thiếu và kế hoạch với báo cáo PoC | Tóm tắt từ báo cáo PoC sau khi chốt, không dùng số khác kỳ |

Thông tin cá nhân đã có. Người thực hiện cần chốt **hạn nộp thực tế**, **người
kiểm tra/ngày nghiệm thu kỹ thuật**, và **kết luận hoặc ngoại lệ được chấp nhận**.
Không tự ghi thầy đã duyệt khi chưa có phản hồi. Các số liệu kỹ thuật lấy từ
thực nghiệm; người thực hiện không cần tự tính hoặc điền giả các chỉ số đang thiếu.

Thứ tự còn lại: hoàn tất/rà soát coverage → rà soát sáu gate
→ kiểm tra bundle/tái lập → cập nhật hai tài liệu cùng một thời điểm chốt.
