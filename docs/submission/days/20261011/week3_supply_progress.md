# Week 3 — Bàn giao nhánh khoa học cung lao động

Ngày 11/10/2026, Asia/Bangkok. Đây là phần triển khai đầu tiên sau nghiệm thu
Week 2, **chưa phải nghiệm thu hoàn tất Week 3**. Mục tiêu bám đề tài: đo hiệu ứng
incentive được đề nghị trước quyết định lên participation, tổng giờ lao động và
giờ có thể phục vụ; simulator hỗ trợ tích hợp ở bước tiếp theo.

## Đã triển khai

- Contract tài xế × cơ hội tham gia ca: giữ mọi tài xế đủ điều kiện và tất cả
  các ca đã khai báo, kể cả không tham gia/không có giờ làm; kiểm khóa, thiếu dữ
  liệu, timestamp, tiền công được đề nghị và giới hạn giờ.
- Generator controlled có các luồng ngẫu nhiên riêng cho bối cảnh, phân bổ và
  phản ứng. Observed, contract, giả định generator và oracle lưu riêng.
- Bộ ước lượng hiệu ứng incentive ngẫu nhiên, CI Welch theo trung bình của từng
  tài xế. Ca lặp lại không tạo thêm đơn vị suy luận độc lập. Conditional hours
  trong nhóm tham gia chỉ được ghi là mô tả.
- Effect/support/interval status và baseline cung không phản ứng. Không đủ tài
  xế ở một nhánh thì giữ `not_identified`; variance bằng 0 thì không tạo CI giả.
- Các lệnh `generate-supply`, `fit-supply`, `scenario-supply`, `evaluate-supply`;
  model JSON, effect CSV, scenario JSON, source snapshots và manifest/checksum.
- Kịch bản chỉ hỗ trợ hai mức incentive đã phân bổ, cùng cohort/calendar. Giờ
  kỳ vọng chưa được biến thành tài xế/xe vật lý. Từ chối mức trung gian hoặc ngoài
  khoảng thay vì nội suy không được kiểm chứng.

Contract/phương pháp/ngưỡng nằm trong [WEEK3_SUPPLY](../../../WEEK3_SUPPLY.md);
lệnh chạy và exports trong [USAGE](../../../USAGE.md#week-3-controlled-labor-supply).

## Kiểm chứng độc lập

Profile scientific: 800 tài xế đủ điều kiện, bảy cơ hội ca tám giờ, incentive
0/20 `SYNTHETIC_UNIT`. Assignment một lần theo tài xế, giữ nguyên trong follow-up.
Không dùng VND hoặc hệ số GSM. Fixture này khác demo vận hành hai xe/hai giờ.

Pilot 10 jobs dùng RCT 51001-51005 và null 52001-52005. Assessment mới dùng RCT
61001-61100 và null 62001-62100, không trùng pilot hoặc assessment Week 2.
Estimator và ngưỡng được cố định trước assessment; không chọn/tune phương pháp
trên cohort này. Hai sửa chữa giữa pilot v1/v2 chỉ dùng biến điểm có kiểu rõ
ràng và pandas Index, không đổi dữ liệu/phương pháp/ngưỡng.

**200/200 seed jobs hoàn tất, 600/600 CI khả dụng; mọi ngưỡng controlled đã khai
báo đạt.** Thời gian đánh giá 149,23 giây trong ngân sách 600 giây; đây là thời
gian thực thi phiên này, không phải benchmark hiệu năng độc lập.

| DGP | Outcome | Bias | RMSE | Coverage / 100 seeds | Báo động giả |
|---|---|---:|---:|---:|---:|
| RCT | Participation | +0,002465 | 0,012567 | 97% | Không áp dụng |
| RCT | Tổng giờ làm | +0,011333 | 0,070986 | 96% | Không áp dụng |
| RCT | Giờ phục vụ | +0,007374 | 0,062185 | 95% | Không áp dụng |
| Null | Participation | −0,000152 | 0,013263 | 98% | 2% |
| Null | Tổng giờ làm | −0,000217 | 0,067094 | 97% | 3% |
| Null | Giờ phục vụ | −0,001163 | 0,056682 | 96% | 4% |

Participation dùng xác suất; giờ dùng giờ/tài xế đủ điều kiện/cơ hội ca. Khi có
hiệu ứng, RMSE baseline không phản ứng tương ứng 0,15; 1,350038; 1,147194. Khi
null, baseline zero có RMSE 0 đúng theo DGP đã khai báo; không kết luận bộ ước
lượng luôn thắng baseline.

Coverage được đo riêng theo outcome/DGP, không gộp thành một chứng nhận. Khoảng
nhị thức exact 95% của hàng RCT giờ phục vụ, coverage 95/100, là khoảng 88,72%-98,36%.
Giữ CI individual và `nominal_coverage_certified=false`. Kết quả này không chứng
nhận coverage tuyệt đối, CI đồng thời, phụ thuộc thị trường hay calibration GSM;
không kế thừa ngoại lệ kỹ thuật của Week 2.

Kết quả một run minh họa, seed 51000: participation +16,64 điểm phần trăm,
giờ làm +1,4643 và giờ phục vụ +1,2355 giờ/tài xế/cơ hội ca. Đây là ước lượng
synthetic cho mức 0→20 đã khai báo, không phải kết luận chính sách cho GSM.

## Kiểm thử và tái lập

- **472 tests đạt**, 120,13 giây; hai Pandas FutureWarnings lịch sử trong controller
  nghiên cứu Week 2. Có 49 kiểm thử mới cho contract, oracle isolation, suy luận
  theo tài xế, unsupported action, zero supply, thất bại/budget và CLI/handoff.
- Ruff toàn bộ src/tests và ty cho năm file nguồn thay đổi đạt. Format kiểm tra
  bảy file Python thay đổi đạt; không format toàn repo. CodeGraph sync bảy file.
- Fit lại observed/contract tái tạo model chính xác; baseline/target/unsupported
  scenario replay chính xác. Summary bias/RMSE/coverage được tính lại từ 600 dòng
  raw assessment, khớp bản ghi.
- Kiểm checksum toàn bộ 20 artifact của baseline Week 2 và 23 artifact hybrid
  thành công. Không thay bundle cũ, contract `prepare-demand` hoặc kết quả nghiên cứu cũ.

Bằng chứng: [verification JSON](week3_supply_verification.json),
[600 dòng assessment](week3_supply_records.csv). Source/spec/protocol/environment,
hash dữ liệu và danh sách run được ghi trong JSON. Dữ liệu tài xế, model và source
snapshots chi tiết nằm trong `runs/`, không đưa dữ liệu lớn vào version control.

## Việc còn lại của Week 3

1. Trả công/settlement và sổ thu nhập; lời mời chuyến thực tế cùng nhận/từ chối/timeout.
2. Chuyển phản ứng cung thành lịch tài xế/xe khả thi, đồng bộ population và horizon với demand.
3. Vòng phản hồi thu nhập–cung khi có cơ sở, kiểm hội tụ/thất bại và paired price-only,
   incentive-only, combined forecasts; benchmark baseline vận hành.

Giờ phục vụ hiện dùng availability fraction khai báo trong synthetic, chưa được
đối soát từ lịch vật lý/SOC/sạc. Income elasticity chưa được nhận dạng; CI dự báo
vận hành và phản hồi chưa triển khai. GSM data/calibration/economics vẫn chờ dữ
liệu và xác nhận. Dashboard và sạc chi tiết được hoãn. **Week 3 đang triển khai.**
