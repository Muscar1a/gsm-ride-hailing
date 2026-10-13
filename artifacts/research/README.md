# Bằng chứng nghiên cứu

Thư mục này lưu bằng chứng kỹ thuật theo ngày chốt Asia/Bangkok.
[Submission](../../docs/submission/README.md) chỉ chứa báo cáo và danh mục hồ sơ;
code đang sử dụng nằm trong `src/` và `scripts/`.

| Ngày | Bằng chứng | Báo cáo |
|---|---|---|
| 07/10/2026 | [Week-2 reporting và thống kê](20261007/results/week2/) | [Hồ sơ 07/10](../../docs/submission/days/20261007/README.md) |
| 11/10/2026 | [Chẩn đoán và assessment](20261011/results/), [inference closeout](20261011/week2_inference_closeout.json), [cung lao động](20261011/week3_supply_verification.json) | [Hồ sơ 11/10](../../docs/submission/days/20261011/README.md) |
| 12/10/2026 | [PoC verification](20261012/week3_poc_verification.json), [compensation](20261012/week3_compensation_verification.json), bảng quỹ đạo/controlled/workload | [Week-3 closeout](../../docs/submission/days/20261012/week3_poc_closeout.md) |

Ngày 12/10/2026, 824 file bằng chứng được chuyển nguyên byte từ submission.
[relocation.json](relocation.json) ghi từng đường dẫn cũ, đường dẫn mới và SHA-256.
Checksum, protocol, code đã thực thi và archive ZIP giữ nguyên. Các bản `.py`
ở đây là snapshot phục vụ đối soát, không phải bản code cần tiếp tục phát triển.

Đối soát sau chuyển xác nhận 803 mục checksum lịch sử khớp. Riêng
`20261011/results/final_inference/executed_audit.py` đã khác checksum được ghi
trong gói từ trước đợt chuyển; hash thực tế trước/sau chuyển vẫn giống nhau.
Sai lệch có sẵn này được ghi riêng trong `preexisting_checksum_mismatches` của
relocation manifest; không sửa code đóng băng hoặc đổi checksum để che sai lệch.

Đường dẫn trong snapshot code, JSON, ZIP và README lịch sử giữ layout tại thời
điểm thực thi. Khi tái lập lịch sử, dùng workspace/nguồn đóng băng trong archive;
dùng relocation manifest để đối chiếu vị trí file hiện tại. README nằm bên trong
gói Week-2 là metadata đã được checksum, nên các liên kết ra ngoài gói của bản
README đó cũng giữ đường dẫn cũ; dùng danh mục báo cáo bên trên để mở tài liệu.
Lệnh hiện hành và liên kết trong báo cáo đã được cập nhật trong
[USAGE](../../docs/USAGE.md). Không ghi đè bằng chứng đã đóng băng khi chạy lại;
đầu ra mới dùng run ID hoặc thư mục mới trong `runs/`/`.cache/`.

Dữ liệu nguồn lớn, mô hình và cache tiếp tục nằm ngoài version control theo
quy ước repository. Thư mục này chỉ chứa các gói bằng chứng đã được quản lý trước
đợt chuyển vị trí và hồ sơ đối soát; không bổ sung dataset mới.
