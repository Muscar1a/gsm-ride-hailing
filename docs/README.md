# Tài liệu GSM Causal Marketplace PoC

Đọc tài liệu theo thứ tự: tiến độ hiện tại → roadmap → contract → thiết kế hoặc
hướng dẫn kỹ thuật cần cho công việc. Cập nhật danh mục ngày **10/10/2026**;
kết quả reporting tuần 2 chốt lúc **17:13:28 ngày 07/10/2026, Asia/Bangkok**.

Mục tiêu chính là ước lượng và kiểm chứng nhân quả **độ nhạy giá khách hàng, cung lao động
tài xế và thay thế giữa dịch vụ**, rồi dự báo tác động chính sách, đánh giá quyết định
và đối chiếu bằng thí nghiệm. Kết quả có khoảng tin cậy, phạm vi áp dụng, bằng chứng
và tiêu chí kinh doanh cùng giới hạn chất lượng dịch vụ/thu nhập tài xế được chốt trước.
Simulator, core engine, dashboard và exports hỗ trợ các đầu ra này. Doanh thu,
contribution margin, lợi nhuận và ROI thực cần định nghĩa và dữ liệu GSM tương ứng;
chỉ tiêu thiếu đầu vào giữ `not_evaluated`. Engine chạy độc lập với UI, có kiểm chứng
mô hình, vận hành, failure handling, tái lập và benchmark tải.
Dashboard và exports dùng cùng kết quả có version từ engine. Tiêu chuẩn đích nằm trong
[core engine design](reference/CORE_ENGINE_DESIGN.md#11-engine-delivery-standard);
trạng thái bên dưới mô tả phần đã triển khai, không mặc định các tiêu chuẩn đã đạt.

## Tiến độ hiện tại

**Week 2 đã hoàn tất compute và rà soát số liệu, chưa nghiệm thu đầy đủ.**
Reporting hoàn thành 500/500 seed jobs; Swissmetro và policy-value development
đã có kết quả. Phần còn lại là chốt hạn chế interval calibration, hoàn thiện
bundle demand/choice cùng rerun/resume, và xác nhận nghiệm thu thực tế.

[Hồ sơ nghiệm thu](submission/days/20261007/acceptance_review.md) là nguồn kết
luận các gate; [rà soát thống kê](submission/days/20261007/statistical_review.md)
giải thích metrics. Kế hoạch thực hiện phần còn lại nằm trong [ROADMAP.md](ROADMAP.md).
Dữ liệu GSM chưa có; kết quả hành vi/vận hành mô phỏng vẫn là evidence C và lợi
nhuận thực của GSM chưa được đánh giá.

Week 3 bước 1 đã triển khai: `prepare-demand` đóng gói choice run đã kiểm tra
checksum, xuất request rates theo zone/block/service và snapshot fleet dùng chung.
Xem [lệnh chạy development](USAGE.md#week-3-demand-handoff). Supply, calibration
và equilibrium vẫn là các bước tiếp theo; chưa có block-rate intervals.

Week 3 bước 2 đã triển khai: `simulate-marketplace` dùng fleet/ca làm cố định,
request Poisson hoặc fixture CSV, xuất trajectories, trips hoàn thành, wait,
idle hours và end snapshot. Xem [hướng dẫn simulation](USAGE.md#week-3-fixed-supply-simulation).
Matching/OD/thời gian là giả định synthetic C; SOC giữ cố định. Phần state/carryover
và cancellation của bước 3 đã triển khai: chạy nối từ checkpoint busy/queued,
expiry theo pickup deadline và hủy trước pickup. Năng lượng/sạc, supply response
và equilibrium vẫn còn phía trước.

## Tài liệu đang dùng

| Tài liệu | Đọc khi cần |
|---|---|
| [USAGE.md](USAGE.md) | Cài đặt, CLI, profiles, exports, đọc status và repository checks |
| [ROADMAP.md](ROADMAP.md) | Yêu cầu I/O theo tuần, chốt tuần 2, triển khai tuần 3 và định hướng tuần 4–5 |
| [GSM_DATA_CONTRACT.md](GSM_DATA_CONTRACT.md) | Request dữ liệu gửi GSM: nguồn, phạm vi, định dạng, khóa và đơn vị |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline, schema nghiên cứu, quy ước artifacts, ranh giới oracle và dashboard |
| [IDENTIFICATION.md](IDENTIFICATION.md) | Nguồn/evidence, estimand, DGPs, OLS/DML, inference và giới hạn kịch bản giá |
| [BENCHMARK.md](BENCHMARK.md) | Protocol, ngưỡng đánh giá phương pháp/choice/policy và quy tắc diễn giải kinh tế |

## Thiết kế và hồ sơ

| Nguồn | Mục đích |
|---|---|
| [Proposal](reference/GSM_Causal_Marketplace_Proposal.md) | Mục tiêu, phạm vi và lộ trình năm tuần |
| [Core engine design](reference/CORE_ENGINE_DESIGN.md) | Thiết kế thuật toán, supply, simulator và equilibrium; chưa phải trạng thái triển khai |
| [Submission](submission/README.md) | Báo cáo/PDF và bằng chứng theo ngày; hồ sơ mới nhất là [07/10](submission/days/20261007/README.md) |
| [Validation lịch sử](submission/days/20261003/validation.md) | Bằng chứng TLC/model/browser ngày 03/10 |

## Quy ước cập nhật

- Cập nhật tiến độ ở đây bằng tóm tắt và link đến bằng chứng có ngày chốt;
  kết luận nghiệm thu chi tiết nằm trong hồ sơ tương ứng.
- Giữ roadmap cho việc còn lại và yêu cầu đầu vào/đầu ra theo tuần; architecture
  và benchmark mô tả cấu trúc hoặc protocol, không lưu nhật ký tiến độ lặp lại.
- Schema/artifacts nằm trong architecture; phương pháp/evidence trong identification;
  metrics, ngưỡng và diễn giải kinh tế trong benchmark. Tài liệu tham chiếu trỏ
  về nguồn quản lý chính khi cần dùng các đặc tả này.
- Giữ `GSM_DATA_CONTRACT.md` ổn định cho request dữ liệu gửi GSM; chỉ sửa khi
  yêu cầu nguồn, trường dữ liệu, phạm vi hoặc quy cách bàn giao thay đổi.
  Yêu cầu đầu vào/đầu ra theo từng bước chỉ trao đổi trong chat, không ghi vào
  tài liệu hoặc file khác. Lệnh chạy nằm trong `USAGE.md`.
- Xóa kế hoạch/nhật ký đã hết vai trò sau khi gộp đặc tả hoặc lệnh còn cần
  vào tài liệu chính. Các link trỏ trực tiếp tới tài liệu đang dùng.
- Hồ sơ có bằng chứng nằm trong submission. Giữ nguyên kết quả số, source,
  checkpoint archive, audit và PDF lịch sử. Khi cập nhật README/metadata,
  ghi ngày/phạm vi cùng hash gốc trong manifest và tính lại checksum hiện hành.
- README gốc giữ mô tả dự án và cấu trúc code; hướng dẫn chạy và repository
  checks nằm trong [USAGE.md](USAGE.md).
