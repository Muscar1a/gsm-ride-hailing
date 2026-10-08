# Tài liệu GSM Causal Marketplace PoC

Đọc tài liệu theo thứ tự: tiến độ hiện tại → roadmap → contract → thiết kế hoặc
hướng dẫn kỹ thuật cần cho công việc. Cập nhật danh mục ngày **08/10/2026**;
kết quả thực nghiệm mới nhất chốt lúc **17:13:28 ngày 07/10/2026, Asia/Bangkok**.

## Tiến độ hiện tại

**Week 2 đã hoàn tất compute và rà soát số liệu, chưa nghiệm thu đầy đủ.**
Reporting hoàn thành 500/500 seed jobs; Swissmetro và policy-value development
đã có kết quả. Phần còn lại là chốt hạn chế interval calibration, hoàn thiện
bundle demand/choice cùng rerun/resume, và xác nhận nghiệm thu thực tế.

[Hồ sơ nghiệm thu](submission/days/20261007/acceptance_review.md) là nguồn kết
luận các gate; [rà soát thống kê](submission/days/20261007/statistical_review.md)
giải thích metrics. Kế hoạch thực hiện phần còn lại nằm trong [ROADMAP.md](ROADMAP.md).
Dữ liệu GSM chưa có; kết quả hành vi/vận hành mô phỏng vẫn là evidence C.

## Tài liệu đang dùng

| Tài liệu | Đọc khi cần |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Chốt tuần 2, triển khai tuần 3 và định hướng tuần 4–5 |
| [GSM_DATA_CONTRACT.md](GSM_DATA_CONTRACT.md) | Yêu cầu dữ liệu, grain, khóa, đơn vị và stage inputs/outputs |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline đang triển khai, ranh giới oracle, lưu artifacts và dashboard |
| [IDENTIFICATION.md](IDENTIFICATION.md) | Estimand, DGPs, OLS/DML, inference và giới hạn kịch bản giá |
| [BENCHMARK.md](BENCHMARK.md) | Protocol đánh giá phương pháp, lựa chọn và policy value |

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
- Giữ roadmap cho việc còn lại; tài liệu contract, architecture và benchmark
  mô tả giao diện hoặc protocol, không lưu nhật ký tiến độ lặp lại.
- Xóa kế hoạch/nhật ký đã hết vai trò sau khi gộp đặc tả hoặc lệnh còn cần
  vào tài liệu chính. Các link trỏ trực tiếp tới tài liệu đang dùng.
- Hồ sơ có bằng chứng nằm trong submission. Giữ nguyên kết quả số, source,
  checkpoint archive, audit và PDF lịch sử. Khi cập nhật README/metadata,
  ghi ngày/phạm vi cùng hash gốc trong manifest và tính lại checksum hiện hành.
- Các lệnh chạy môi trường và repository checks nằm trong [README gốc](../README.md).
