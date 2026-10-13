# Week 3 — Cơ chế trả công tối thiểu

Ngày kiểm chứng: 12/10/2026, Asia/Bangkok.

Bun đã thống nhất giữ gói cung hiện có và giả sử tài xế nhận **100% giá cước
hiển thị trên app** khi chưa biết chính sách GSM. Cơ chế này đã được triển khai
vào luồng vận hành hiện có, với đầu ra tiền công riêng. Đây là giả định synthetic,
evidence C và `not_calibrated`, chưa phải chính sách thực tế của GSM.

## Đã triển khai

- `--compensation configs/week3_compensation.json` bật cơ chế trả công trong
  `simulate-marketplace`. Luồng cũ vẫn chạy được khi không bật cơ chế này.
- Biểu giá gốc minh họa X=Y=1 `SYNTHETIC_UNIT`; giá hiển thị bằng giá gốc nhân
  hệ số giá baseline và `(1 + delta)` của chính sách demand đã đóng băng. Đây là
  đơn vị chuẩn hóa, không phải VND hoặc giá GSM. Cơ chế tiền công không áp dụng
  lại tác động giá vào xác suất đặt chuyến.
- Điều khoản được xác định từ biểu giá/chính sách trước khi mô phỏng; xuất riêng
  giá hiển thị, tiền công tài xế được thông báo và khoản thực trả khi hoàn thành.
  Chuyến hủy/hết hạn trả 0 theo quy tắc tối thiểu; chuyến còn mở chưa thanh toán.
- Thu nhập theo tài xế/ca giữ cả người không có chuyến. Mẫu số là giờ hiện diện
  gồm thời gian idle và unavailable, loại offline. Không có giờ hiện diện thì
  thu nhập/giờ là unavailable. Đây là tiền công gộp, chưa trừ chi phí.
- Nối cửa sổ giữ nguyên phiên bản trả công và điều khoản giá; chỉ thanh toán sự
  kiện hoàn thành trong cửa sổ hiện tại. Thay đổi/bỏ điều khoản đã đóng băng bị
  từ chối. Bật hoặc bỏ cơ chế tiền công trên một run đã có kết quả yêu cầu run ID
  mới để tránh giữ lại đầu ra tiền công cũ.

Các đầu ra CSV/Parquet: `quote_terms`, `driver_pay_terms`, `earnings_ledger`,
`driver_income`; báo cáo JSON: `earnings_result.json`. Các đầu vào và đầu ra
được đăng ký checksum trong manifest. Xem [hướng dẫn chạy](../../../USAGE.md#week-3-minimal-compensation).

## Kết quả chạy thật

Tất cả dòng dưới dùng seed 42, đội xe cố định hai xe/hai giờ và biểu giá synthetic.
Chúng kiểm tra nối demand–giá–tiền công, không ước lượng hiệu quả chính sách GSM.

| Run (`20261012-v2`) | Yêu cầu mới | Chuyến hoàn thành | Tiền tài xế (`SYNTHETIC_UNIT`) |
|---|---:|---:|---:|
| `week3-pay-fixture` | 3 | 2 | 2,0 |
| `week3-pay-fixture-x-plus10` | 3 | 2 | 2,1 |
| `week3-pay-baseline` | 479 | 3 | 3,0 |
| `week3-pay-x-plus10` | 436 | 4 | 4,3 |
| `week3-pay-window-first` | 3 | 2 | 2,0 |
| `week3-pay-window-second` | 0 | 0 | 0,0 |

Run ID đầy đủ thêm `-20261012-v2` vào tên trong bảng. Hai cửa sổ chia tại 08:11
local, đúng lúc hai chuyến hoàn thành; cửa sổ sau không trả lại hai chuyến này.
Sổ tiền công, chuỗi sự kiện và checkpoint cuối khớp chạy liên tục. Một run replay
riêng tái tạo **18 đầu ra CSV/Parquet/JSON giống từng byte**.

Chênh lệch 3 và 4 chuyến ở hai luồng Poisson là kết quả của từng quỹ đạo synthetic
với giá/rate khác nhau; không phải kết quả thực nghiệm nhân quả hoặc bằng chứng
tăng cung. Giờ hiện diện vẫn xấp xỉ 4 giờ tài xế ở cả hai luồng.

[Bằng chứng kiểm chứng](../../../../artifacts/research/20261012/week3_compensation_verification.json) lưu run ID đầy đủ,
scope, kết quả, seed/protocol, môi trường, Git revision, hash nguồn/config/lock và
checksum manifest. Sáu gói nguồn được kiểm tra checksum và giữ nguyên: hai demand
baseline/target, Week-2 baseline/hybrid và supply fit/assessment.

## Kiểm tra kỹ thuật

- Toàn bộ **524 tests đạt**, trong 114,58 giây; hai Pandas FutureWarning lịch sử
  trong các script chẩn đoán Week 2, không có cảnh báo mới ở phần tiền công.
- 147 tests riêng về tiền công và vận hành đạt, gồm trả đủ cước, hủy/dang dở,
  tài xế không có chuyến, mẫu số bằng 0, chạy nối tại thời điểm hoàn thành,
  phiên bản/checksum sai, dữ liệu tiền không hợp lệ và tràn giá trị.
- Ruff kiểm tra `src/tests` đạt; format chỉ các file Python thay đổi; `ty` kiểm
  tra bốn file nguồn tiền công/CLI/pipeline/vận hành đạt. CodeGraph đã sync.
- Đã sửa và thêm kiểm tra chống lưu đầu ra tiền công cũ khi đổi chế độ trên cùng
  run, và kiểm tra thời lượng dùng cùng độ chính xác nanosecond với vận hành.

Không chạy lại assessment lớn của Week 2 hoặc supply: phương pháp của các gói
này không thay đổi, checksum bàn giao giữ nguyên và regression toàn repo đã đạt.

## Giới hạn và phần tiếp theo

Gói cung khoa học giữ nguyên phương pháp và đánh giá độc lập trước đó. Cơ chế trả
đủ cước cung cấp sổ tiền công; chưa nối thu nhập kỳ vọng vào quyết định tham gia
hay giờ làm. Kết quả ưu đãi 0/20 của gói cung không được diễn giải thành độ co giãn
theo thu nhập. Quy mô/cohort của gói cung cũng chưa chuyển thành lịch tài xế/xe
khả thi của mô hình vận hành.

Attendance, immediate acceptance và SOC cố định vẫn là các giả định vận hành.
Chưa triển khai phản ứng cung theo thu nhập, cân bằng cung–cầu, chi phí/lợi nhuận/
ROI, khoảng tin cậy toàn chuỗi hoặc hiệu chỉnh bằng dữ liệu GSM. Gói này hoàn thành
cơ chế trả công tối thiểu được giao, chưa hoàn thành toàn bộ Week 3.
