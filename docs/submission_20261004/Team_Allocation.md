# Vai trò và kế hoạch công việc cá nhân — PoC GSM

- Hình thức thực hiện: **Cá nhân**
- Người thực hiện: **Nguyễn Thành An — 26ai.annt@vinuni.edu.vn**
- Mục tiêu Phase 3 làm căn cứ kế hoạch (theo [proposal ban đầu](../GSM_Causal_Marketplace_Proposal.md)): **Ước lượng ba độ co giãn (cầu theo giá, phản ứng cung, thay thế chéo); tích hợp simulator một cụm; bàn giao dashboard kịch bản và thiết kế switchback.** Đánh giá doanh thu, biên đóng góp và ROI khi đủ dữ liệu. PoC hiện tại thực hiện phần đầu của lộ trình năm tuần.
- Mã nguồn: **[Muscar1a/gsm-ride-hailing](https://github.com/Muscar1a/gsm-ride-hailing)** — công khai. Demo: chạy cục bộ, chưa có URL công khai.
- Dữ liệu GSM: theo [tài liệu yêu cầu dữ liệu](<../GSM Causal Marketplace - Data Requirements.pdf>), tám nhóm nguồn gốc trong 12 tháng gần nhất; giữ schema gốc, bao gồm vùng lân cận/đối chứng.

## Vai trò và phần việc trong PoC hiện tại

Bảng dưới mô tả các phần việc đã có trong PoC cùng bằng chứng đối chiếu.

| Vai trò | Phần việc PoC đã hoàn thành | Bằng chứng trong repo |
|---|---|---|
| Thiết kế và dữ liệu | Thiết kế phạm vi hai tuần; pipeline TLC, cờ chất lượng, silver và mart; đối soát 970.940 chuyến | `docs/ARCHITECTURE.md`; `docs/VALIDATION.md`; `src/gsm_poc/` |
| Mô hình và đánh giá | Bộ sinh năm DGP; baseline OLS, DML và bootstrap; benchmark 20 seed mỗi DGP; một run TLC-context với 199 refit mỗi estimator | `docs/IDENTIFICATION.md`; `docs/VALIDATION.md`; manifest các run đã ghi |
| Kịch bản và demo | Kịch bản giá có kiểm tra hỗ trợ; dashboard ba màn hình; xuất CSV/JSON | `src/gsm_poc/scenario.py`; `src/gsm_poc/app.py`; `README.md` |
| Kiểm chứng và báo cáo | 42 kiểm thử; lint/format; tám kiểm tra browser; báo cáo kỹ thuật, cập nhật tiến độ và đề xuất dữ liệu GSM | `tests/`; `scripts/check_dashboard.py`; `docs/VALIDATION.md`; hồ sơ hiện tại |

## Kế hoạch cá nhân cho giai đoạn tiếp theo

Kế hoạch bám lộ trình năm tuần trong proposal. Mô hình cung và simulator có thể
phát triển trên dữ liệu giả lập; hiệu chỉnh theo vận hành thật và kết quả kinh tế
phụ thuộc dữ liệu GSM.

| Mốc theo proposal | Phần việc tiếp theo | Đầu ra cần bàn giao |
|---|---|---|
| Tuần 2: 05–11/10 | Bổ sung baseline Swissmetro riêng; hoàn thiện thu hồi tham số, độ bao phủ nhiều seed và benchmark giá trị chính sách độc lập | So sánh baseline, khoảng bất định, mức bằng chứng và giới hạn |
| Tuần 3: 12–18/10 | Mô hình phản ứng cung; simulator ghép khách–xe, hủy và sạc; tích hợp ba độ co giãn | Kịch bản giá/thưởng, điểm cân bằng và nguồn cung nhàn rỗi giả lập; hiệu chỉnh khi có dữ liệu nền GSM |
| Tuần 4: 19–25/10 | Hoàn thiện dashboard; phân tích carryover/cỡ mẫu; thiết kế lịch switchback và sổ đối chiếu | Demo trọn luồng, kế hoạch thử nghiệm và dự báo được chốt trước lượt |
| Tuần 5: 26/10–01/11 | Tích hợp, kiểm thử và bàn giao; A/A hoặc pilot khi đủ dữ liệu và được GSM chấp thuận | Mã nguồn, hướng dẫn, báo cáo trạng thái nghiệm thu và kế hoạch pilot |

**Điều kiện cần GSM xác nhận:** dữ liệu, cơ chế chi trả, biên độ thử nghiệm và ngưỡng vận hành. GSM trích xuất, giả danh hóa ổn định và giải thích nghiệp vụ; người thực hiện ánh xạ schema, nối khóa, kiểm tra chất lượng và xây mô hình. Lịch trên là kế hoạch dự kiến; ROI và hiệu quả trên GSM hiện chưa đánh giá.
