# Week 4–5 — Chính sách giá và bộ bàn giao PoC

Ngày kiểm chứng: **16/10/2026, Asia/Bangkok**. Đã triển khai và chạy luồng kỹ thuật
tuần 4–5 trong phạm vi fixed-online Bun nghiệm thu ở tuần 3. **Chưa ghi nhận Bun
nghiệm thu tuần 4–5.** Toàn bộ hành vi giữ nhãn synthetic evidence C,
`not_calibrated`; chưa có kết luận causal, lợi nhuận hoặc ROI thực tế của GSM.

## Nghiệp vụ đã triển khai

1. So sánh một tập hữu hạn chính sách giá X/Y có baseline, cùng quote population,
   roster và các seed ghép cặp; kiểm tra support và xác suất trước mô phỏng.
2. Truyền bootstrap refit theo ngày qua nhu cầu và vận hành; giữ riêng khoảng
   Monte Carlo conditional, đếm đầy đủ các draw/lượt thất bại hoặc metric thiếu.
3. Kiểm tra tiêu chí lựa chọn và ràng buộc chờ/thu nhập, cùng độ nhạy khi tỷ lệ nhận
   đơn thấp hơn hoặc di chuyển chậm hơn. Các ngưỡng hiện tại là giả định development.
4. Nối chi phí theo chuyến, giờ online và toàn khoảng quan sát. Chi phí thiếu giữ
   unavailable. Với quy tắc trả tài xế 100%, thu cước và trả tài xế triệt tiêu;
   không tự tạo hoa hồng hoặc lợi nhuận.
5. Đánh giá độc lập bằng phản ứng thật đã biết của generator và seed vận hành mới;
   xuất sai số dự báo, ràng buộc và regret theo tập ứng viên hữu hạn, giữ nguyên
   lựa chọn đã đóng băng.
6. Lập lịch A/A–A/B có seed, washout, tính cỡ mẫu từ phương sai được khai báo;
   đối soát assignment/exposure, mẫu số, missingness và dự báo đóng băng.
7. Dashboard đọc/xuất đúng artifact đã kiểm checksum; đóng gói transitive source
   runs, dữ liệu, mô hình, mã, cấu hình và hướng dẫn chạy lại trong ZIP.

Contract, giới hạn và lệnh chạy: [WEEK4_5.md](../../../WEEK4_5.md).

## Kết quả đã chạy

| Kiểm chứng | Kết quả |
|---|---|
| Toàn bộ kiểm thử trên mã bàn giao | **637 passed**, 2 cảnh báo pandas cũ; 176,59 giây |
| Ruff và định dạng `src/tests` | Đạt; 86 tệp đúng định dạng |
| `ty` trên toàn bộ `src/gsm_poc` | Đạt, bật error-on-warning |
| CodeGraph | Đã sync sau thay đổi mã |
| So sánh development | **690/690 quỹ đạo thành công**, khoảng 198,44 giây |
| Đánh giá oracle riêng | **500/500 quỹ đạo thành công**, 100 seed mới cho mỗi ứng viên |
| A/A replay có provenance | 20 block, 10 cặp đầy đủ; không thiếu outcome hoặc sai exposure |
| Giao diện | AppTest trong bộ kiểm thử; đọc bảng và tải artifact cùng nguồn |

Hai cảnh báo cũ đến từ `compare_week2_variance.py:324` và
`compare_week2_intervals.py:349`. Một lỗi định dạng có sẵn trong chữ ký
`freeze_artifacts` được chuẩn hóa để repository format check đạt, không đổi hành vi.

690 quỹ đạo gồm 300 point-fit lượt trên ba giả định vận hành và 390 lượt từ 39 mô
hình bootstrap, hai replicate mỗi mô hình và năm ứng viên. Seed point-fit
82001–82020, bootstrap vận hành 92001–92078; assessment dùng 99001–99100.
Đây là số lượt chạy, không phải 1.190 thí nghiệm độc lập hoặc bằng chứng GSM.

## Quyết định chính sách

Tiêu chí development: tăng số chuyến hoàn tất trong hai giờ, dưới các ràng buộc
và sensitivity đã khai báo. Cùng hai tài xế và các bối cảnh synthetic cố định:

| Chính sách | Chuyến hoàn tất trung bình | Thay đổi so với baseline | Khoảng bootstrap của thay đổi |
|---|---:|---:|---|
| Baseline | 3,95 | 0,00 | [0,00; 0,00] |
| X +5% | 3,95 | 0,00 | [-2,50; 2,025] |
| X +10% | 4,55 | +0,60 | [-0,525; 3,00] |
| Y +5% | 4,15 | +0,20 | [-1,525; 2,55] |
| X/Y +5% | 4,55 | +0,60 | [-1,025; 2,05] |

**Luồng lựa chọn giữ baseline.** Những mức tăng điểm ước lượng chưa chứng minh
được mức cải thiện tối thiểu khi xét bất định và độ nhạy. Các khoảng trên là
percentile 95% của 39 per-model paired-replicate means, có nhiễu Monte Carlo do
chỉ hai replicate; chưa chứng nhận coverage danh nghĩa hoặc lựa chọn tối ưu.

Evaluator độc lập cho baseline 3,89 chuyến và ứng viên tham chiếu X +10% 4,49
chuyến, tương ứng regret điểm 0,60 chuyến trong tập hữu hạn, dưới rules cố định.
Regret chưa có khoảng tin cậy; evaluator không đổi lựa chọn baseline. Fixture hai
tài xế bị giới hạn công suất mạnh, không phải cơ sở khuyến nghị tăng giá cho GSM.

## Kế hoạch và đối soát A/A

Lịch minh họa một cluster, 10 cặp block hai giờ, washout giả định 30 phút; cả hai
arm áp dụng baseline. Lịch tương lai chỉ phục vụ thiết kế synthetic, chưa được
triển khai ngoài thực tế. Phương sai đầu vào chưa cung cấp nên cỡ mẫu mục tiêu
giữ `unavailable_missing_variance`; công thức power đã có kiểm thử với giá trị biết trước.

Replay ánh xạ 20 quỹ đạo baseline có sẵn theo thứ tự seed vào thứ tự dòng lịch.
`replay_provenance.json` giữ ánh xạ và checksum nguồn. **Không có mẫu độc lập mới,
quan sát tương lai hoặc thí nghiệm GSM.** Đối soát thu được chênh lệch -0,70 chuyến,
khoảng t [-2,051; 0,651] chứa 0, đủ 20 block/10 cặp. Đây là kiểm tra luồng đối soát
dưới giả định độc lập đã khai báo; không xác nhận washout hay tác động causal thực tế.

## Nguồn và tái lập

| Mục đích | Run |
|---|---|
| Nguồn mới, có sáu tệp dữ liệu generator đầy đủ | `week45-choice-20261016-v1` |
| Demand baseline | `week45-demand-20261016-v1` |
| Chính sách đã kiểm chứng | `week45-policies-20261016-v2` |
| Đánh giá độc lập | `week45-assessment-20261016-v1` |
| Kế hoạch thử nghiệm | `week45-experiment-20261016-v1` |
| Dữ liệu A/A replay và provenance | `week45-aa-replay-20261016-v1` |
| Đối soát | `week45-reconciliation-20261016-v1` |
| Hồ sơ kiểm chứng | `week45-verification-20261016-v1` |
| Gói bàn giao | `week45-handoff-20261016-v1` |

Các artifact lớn nằm trong `runs/` và `data/` được Git bỏ qua. Hồ sơ nhỏ được giữ
tại [week45_verification.json](../../../../artifacts/research/20261016/week45_verification.json).
Gói ZIP có inventory SHA256 và các source run/data liên quan. Dùng ID mới khi
rerun dưới mã/môi trường mới. Nguồn mới không khôi phục hoặc sửa sáu tệp training
thiếu của run tuần 3 cũ; các gói đã nghiệm thu trước đó được giữ nguyên.

Run development `week45-policies-20261016-v1` được giữ trạng thái failed vì lỗi
tổng hợp giá trị chi phí thiếu trong nhánh bootstrap. Đã sửa nguyên nhân và thêm
hai kiểm thử hồi quy; chỉ v2 hoàn chỉnh được dùng cho assessment/bàn giao. Chạy lại
cùng seed sau sửa lỗi không được cộng thành bằng chứng độc lập mới.

Các ngưỡng nghiệp vụ/kế toán GSM, calibration, nominal coverage, kiểm chứng phụ
thuộc/carryover, thí nghiệm thực tế và nghiệm thu vẫn cần dữ liệu/xác nhận tương ứng.
