# Week 3 — Nghiệm thu PoC Marketplace với lượng tài xế online cố định

**Reviewer: Bun. Ngày: 12/10/2026, Asia/Bangkok.** Quyết định trực tiếp trong phiên làm việc: **Week 3 PoC accepted**.

Week 3 được nghiệm thu trong phạm vi PoC thu hẹp theo đặc tả [WEEK3_POC_SCOPE](../../../WEEK3_POC_SCOPE.md). Toàn bộ kết quả giữ nhãn bằng chứng synthetic cấp C, **`not_calibrated`**; chưa phải kết quả thực nghiệm thực tế GSM hay hoàn thành toàn bộ đề tài nghiên cứu ban đầu.

## Phạm vi và quyết định chấp nhận

1. **Danh sách tài xế online cố định**:
   - Khai báo danh sách xe/tài xế online dùng chung cho cả dịch vụ X và Y trong suốt khoảng quan sát 2 giờ (mặc định 2 xe cho kịch bản đối chiếu).
   - Không áp dụng phân ca, phân giờ làm việc hay mô hình hóa hành vi bật/tắt ứng dụng.
   - Tài xế từ chối đơn vẫn giữ trạng thái online và sẵn sàng nhận đề nghị tiếp theo; từ chối không làm mất số giờ lao động sẵn có.

2. **Cơ chế đề nghị và nhận chuyến (Offer & Acceptance)**:
   - Mô hình hóa quyết định nhận đơn theo phân phối Bernoulli với xác suất $0.8$, phản hồi 3 giây, timeout 10 giây, tối đa 20 lượt đề nghị cho mỗi yêu cầu.
   - Xác suất nhận đơn là giả định synthetic độc lập với giá cước; không diễn giải thành hệ số co giãn cung lao động thực tế.
   - Tỷ lệ nhận đơn được tính chuẩn hóa theo mẫu số giải quyết thực tế: accepted / (accepted + rejected + timed_out). Đề nghị rút (`withdrawn`) hoặc đang chờ (`pending`) được tách riêng.

3. **Chính sách trả công tối thiểu (Compensation)**:
   - Đóng băng điều khoản giá hiển thị và mức trả công trước khi tài xế ra quyết định.
   - Thanh toán đúng **100% giá cước hiển thị** và chỉ thanh toán cho chuyến hoàn tất (`completed_only`). Hủy chuyến không phát sinh chi trả.
   - Toàn bộ tài xế trong danh sách online (kể cả tài xế có 0 chuyến) đều được giữ trong bảng tổng hợp thu nhập để tránh thiên lệch mẫu số. Đơn vị đo là `SYNTHETIC_UNIT`.

4. **Tách biệt gói cung lao động độc lập**:
   - Gói [cung lao động có kiểm soát](../../../WEEK3_SUPPLY.md) trước đó cùng bằng chứng RCT/null độc lập được bảo toàn riêng biệt như tài sản khoa học; không dùng để suy diễn co giãn cung lao động trong PoC vận hành này.

## Bằng chứng kỹ thuật được xác nhận

Căn cứ trên [Báo cáo bàn giao Week 3](week3_poc_closeout.md) và [Hồ sơ kiểm chứng](week3_poc_verification.json):

| Hạng mục kiểm tra | Kết quả ghi nhận | Trạng thái |
|---|---|---|
| **Test Suite toàn diện** | **609/609 passed**, 0 failed, 2 warnings pandas cũ | Đạt |
| **Linter & Formatter (`ruff`)** | Pass 100% trên `src` và `tests`, chuẩn `snake_case` | Đạt |
| **Kiểm tra kiểu dữ liệu (`ty`)** | Pass trên toàn bộ các module sửa đổi | Đạt |
| **Đánh giá độc lập (Evaluator)** | **303/303 jobs thành công** trên 100 seeds (73001–73100) | Đạt |
| **Cơ chế kiểm soát (Separated offers)** | 14.47 chuyến / 14.47 gross pay (sai số tuyệt đối $\le 1.2$ so với kỳ vọng 15) | Đạt |
| **Tái lập cùng seed & Checkpoint** | Khớp từng byte trên 22 tệp đầu ra; tiếp tục mượt mà qua ranh giới cửa sổ | Đạt |
| **Bảo vệ toàn vẹn dữ liệu** | 8 manifest nguồn và frozen choice v2/v3 bảo toàn checksum SHA-256 | Đạt |
| **Workload stress test** | 2, 20, 100 tài xế hoàn thành trong 2.4s – 7.7s, đỉnh RAM $\le 10.9$ MB | Đạt |
| **Dashboard UI** | AppTest nạp artifact mô phỏng độc lập, hiển thị số liệu chính xác | Đạt |
| **CodeGraph** | Đã đồng bộ (`codegraph sync`) | Đạt |

## Giới hạn giữ nguyên

1. Toàn bộ kết quả là **Evidence Level C (`not_calibrated`)**, chưa có dữ liệu thực tế từ GSM để hiệu chỉnh. Các chỉ số tài chính thực tế (doanh thu, lợi nhuận ròng, ROI) giữ trạng thái `not_evaluated`.
2. Giả định cung online cố định và tỷ lệ nhận đơn không phụ thuộc giá chỉ phục vụ kiểm chứng vận hành cơ chế PoC; không chứng minh co giãn cung lao động bằng 0.
3. Ngưỡng 10.000 requests là chặn trên kỹ thuật cấu hình, chưa load test thực tế ở mức này.

## Kế hoạch chuyển tiếp sang Week 4

Nghiệm thu gói Week 3 PoC làm cơ sở kỹ thuật để triển khai các mục tiêu Week 4:
- Triển khai so sánh các chính sách giá hữu hạn (finite policy comparisons) và đánh giá độ nhạy.
- Tích hợp các ràng buộc kinh tế / tài chính (financial guardrails và cost bridge).
- Thiết kế thử nghiệm A/A, tính toán power và lập kế hoạch thử nghiệm thực tế (experiment planning).
