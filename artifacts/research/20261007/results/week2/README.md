# Kết quả compute Week 2 — 07/10/2026

Hoàn tất lúc **17:13:28, Asia/Bangkok (UTC+07)**: **500/500 seed jobs**,
100 seed cho mỗi DGP, 100 batch. Không có checkpoint `failed` ở kết quả cuối.
Seed reporting là `20001–20100`; 199 bootstrap draws cho mỗi estimator được
nhận dạng. Các trường hợp không nhận dạng vẫn được giữ trong kết quả và mẫu số.

Đây là bản lưu kết quả cuối cùng cạnh hồ sơ nộp. Kết quả số đã được đối chiếu
SHA-256 với output gốc và rà soát đầy đủ coverage, NULL_EFFECT cùng stress cases.
Dữ liệu đánh giá thuộc **evidence C**. **Nghiệm thu Week 2 còn mở**, gồm hạn chế
interval calibration và bộ demand/choice bàn giao; kết luận nằm trong
[acceptance review](../../acceptance_review.md) và
[statistical review](../../statistical_review.md).

| File | Nội dung |
|---|---|
| [evaluation_metrics.csv](evaluation_metrics.csv) | Metrics tổng hợp theo DGP, estimator, outcome và treatment |
| [seed_metrics.parquet](seed_metrics.parquet) | Metrics chi tiết của 500 seed jobs |
| [status.json](status.json) | Trạng thái hoàn tất, số seed/DGP và checksum bảng kết quả |
| [execution.json](execution.json) | Pool 30 worker, thời điểm chạy và checksum adapter I/O |
| [frozen_spec.json](frozen_spec.json) | Giao thức, cấu hình, môi trường và dấu vết nguồn đóng băng |
| [manifest.json](manifest.json) | Nguồn xuất, phạm vi đánh giá, SHA-256 hiện hành và lịch sử cập nhật README/metadata |
| [checksums.sha256](checksums.sha256) | SHA-256 để kiểm tra toàn bộ gói lưu, trừ chính file checksum |
| [reproducibility.zip](reproducibility.zip) | 500 checkpoint JSON/parquet, 100 batch manifests, bảng kết quả từng batch, source/config/lock/context của snapshot, scripts thực thi và logs |
| [recovery_audit/after_resume.json](recovery_audit/after_resume.json) | Xác nhận 412 checkpoint trước resume và giao thức giữ nguyên |

## Phục hồi lỗi checkpoint

Lượt trước dừng với 412 job hoàn tất sau hai lỗi `WinError 5` khi thay file
checkpoint. Adapter I/O ngoài snapshot thêm retry có giới hạn cho thao tác
atomic replace, giữ nguyên source thực nghiệm và kết quả số. Lượt resume với
pool 30 worker lúc 17:12:59 hoàn tất 88 job còn thiếu lúc 17:13:28. Checksum
JSON/parquet của 412 checkpoint cũ giữ nguyên; bằng chứng trước/sau nằm trong
`recovery_audit`.

Archive giữ nguyên metadata của lượt chạy, bao gồm đường dẫn workspace gốc.
Snapshot revision: `574cf501304a777827c2e04704d96a1ab563e1b2`.
Protocol fingerprint:
`f2f405f8ca5d4a2962628f4487224ea003c1bb9c01fc6abb679910d8e9747715`.

## Cập nhật tài liệu — 08/10/2026

README cập nhật link trực tiếp và kết luận sau rà soát. Manifest ghi ngày/phạm vi
cùng hash gốc của README, manifest và checksum; `checksums.sha256` phản ánh gói
hiện hành. Kết quả số, frozen spec, execution/recovery metadata,
`reproducibility.zip` và audit thống kê giữ nguyên.
[Audit ngày 07/10](statistical_review/audit.json) lưu hash của bản gốc đã được
rà soát, bao gồm README/manifest trước cập nhật tài liệu.

[Báo cáo tuần](../../weekly_report.md) ·
[Cập nhật tiến độ](../../progress_update.md) ·
[Lệnh thực thi và tái lập](../../../../../BENCHMARK.md#reporting-execution-and-compute-provenance)
