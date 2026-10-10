# Tài liệu GSM Causal Marketplace PoC

Đọc tài liệu theo thứ tự: tiến độ hiện tại → roadmap → contract → thiết kế hoặc
hướng dẫn kỹ thuật cần cho công việc. Cập nhật danh mục ngày **11/10/2026**;
kết quả reporting tuần 2 chốt lúc **17:13:28 ngày 07/10/2026, Asia/Bangkok**.

Mục tiêu là ước lượng và kiểm chứng nhân quả **độ nhạy giá khách hàng, cung lao động
tài xế và thay thế giữa dịch vụ**, rồi dự báo, đánh giá chính sách và đối chiếu
bằng thí nghiệm. [Proposal](reference/GSM_Causal_Marketplace_Proposal.md) quản lý
mục tiêu/phạm vi; [core engine design](reference/CORE_ENGINE_DESIGN.md#11-engine-delivery-standard)
quản lý thuật toán và tiêu chuẩn hỗ trợ. Các đặc tả và trạng thái hiện hành được
dẫn bên dưới; kết quả thiếu dữ liệu hoặc nhận diện giữ `not_evaluated`.

## Tiến độ hiện tại

**Đặc tả Week 1 được Bun duyệt ngày 11/10/2026.** Phạm vi duyệt gồm
câu hỏi/estimand trong [IDENTIFICATION.md](IDENTIFICATION.md), đặc tả trạng thái
nguồn và mapping trong [ARCHITECTURE.md](ARCHITECTURE.md#research-table-schemas),
khung xác nhận tiêu chí kinh doanh và kế hoạch đánh giá trong [BENCHMARK.md](BENCHMARK.md).
Điều kiện đóng tuần nằm trong
[roadmap tuần 1](ROADMAP.md#week-1-specification-and-closure).

Rà soát ngày 11/10 xác nhận nền public/synthetic có thể tái sử dụng: run
`20261003T131251-0b5e2209` có tám artifact ingest/build tồn tại và khớp checksum,
silver/mart cùng đối soát **970.940 chuyến**, và split của choice run
`20261003T130951-df24a7e4` có 4.800/1.200/1.440 block train/validation/test,
không trùng ngày. **49 kiểm thử liên quan** về dữ liệu, độ phủ, generator,
estimation và artifact/CLI đạt trong lần rà soát; thư mục tạm được đặt trong
workspace. Số liệu lịch sử nằm trong [validation 03/10](submission/days/20261003/validation.md).
Các kiểm tra này xác nhận phạm vi TLC và controlled choice, chưa xác nhận
mapping/coverage GSM hoặc độ bao phủ khoảng tin cậy của mọi đáp ứng.

Theo xác nhận của Bun ngày 11/10, GSM đang xử lý và chưa bàn giao dữ liệu.
Mapping/độ phủ thực chưa được kiểm chứng; tiêu chí kinh doanh, mức cải thiện
đáng thử, biên độ chính sách và ngưỡng chờ/hủy/thu nhập/ngân sách còn chờ GSM
xác nhận. **Week 1: đặc tả đã duyệt; phần GSM chờ dữ liệu và xác nhận nghiệp vụ**.

**Week 2 đã hoàn tất compute và rà soát số liệu, chưa nghiệm thu đầy đủ.**
Reporting hoàn thành 500/500 seed jobs; Swissmetro và policy-value development
đã có kết quả. Phần còn lại là chốt hạn chế interval calibration, hoàn thiện
bundle demand/choice cùng rerun/resume, và xác nhận nghiệm thu thực tế.

[Hồ sơ nghiệm thu](submission/days/20261007/acceptance_review.md) là nguồn kết
luận các gate; [rà soát thống kê](submission/days/20261007/statistical_review.md)
giải thích metrics. Kế hoạch thực hiện phần còn lại nằm trong [ROADMAP.md](ROADMAP.md).
Kết quả hành vi/vận hành mô phỏng là evidence C; các kết luận GSM giữ trạng thái
theo dữ liệu và nhận diện tương ứng.

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
| [ROADMAP.md](ROADMAP.md) | Đặc tả/điều kiện đóng tuần 1, yêu cầu theo tuần, chốt tuần 2 và định hướng tuần 3–5 |
| [GSM_DATA_CONTRACT.md](GSM_DATA_CONTRACT.md) | Request dữ liệu gửi GSM: nguồn, phạm vi, định dạng, khóa và đơn vị |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline, schema và trạng thái mapping/coverage, quy ước artifacts, ranh giới oracle và dashboard |
| [IDENTIFICATION.md](IDENTIFICATION.md) | Ba câu hỏi nhân quả, estimand/nhận diện, DGP demand/choice và giới hạn bằng chứng |
| [BENCHMARK.md](BENCHMARK.md) | Kế hoạch đánh giá theo estimand, quyết định kinh doanh còn chờ xác nhận và protocol/ngưỡng hiện có |

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
