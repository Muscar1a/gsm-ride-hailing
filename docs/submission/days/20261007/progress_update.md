# Cập nhật tiến độ PoC GSM

**Người thực hiện:** Nguyễn Thành An · 26ai.annt@vinuni.edu.vn

**Ngày cập nhật:** 07/10/2026 · So với bản đã nộp ngày 04/10/2026

## 1. Tiến độ chung


Bản ngày 04/10 đã có luồng xử lý từ kiểm tra dữ liệu đến mô hình, kịch bản
giá và xuất kết quả. Phạm vi TLC gồm **970.940 chuyến hoàn tất**, đã được
đối soát; lượt kiểm tra ban đầu trên dữ liệu tổng hợp hoàn tất 100 lượt
mô phỏng. TLC cung cấp bối cảnh cho một phần thực nghiệm, còn dữ liệu
lựa chọn là tổng hợp hoặc bán tổng hợp, chưa phải hành vi quan sát của GSM.

## 2. Những phần bổ sung từ bản ngày 04/10

- **Đánh giá trên nhiều phép lặp:** đã hoàn thành **500/500 lượt mô phỏng**,
  gồm 100 phép lặp cho mỗi trong năm trường hợp mô phỏng, không có lỗi
  chạy cuối cùng. Số liệu đã được đối chiếu và tính lại. Khi giá ngẫu
  nhiên, sai số xác suất kịch bản khoảng **0,36 điểm phần trăm**, dưới
  ngưỡng 2 điểm phần trăm đã đặt ra.

- **Kiểm tra dự báo trên Swissmetro:** bổ sung bộ dữ liệu khảo sát lựa
  chọn giả định, được đánh giá riêng với TLC. Trên **1.611 nhiệm vụ của
  179 người** chưa xuất hiện trong tập huấn luyện, mô hình có thời gian
  và chi phí đạt độ chính xác **66,98%**, so với **57,48%** của mô hình
  chỉ có hằng số. Các thuộc tính này bổ sung thông tin dự báo lựa chọn.

- **Kiểm tra quyết định giá:** hoàn thành 40 lượt mô phỏng, gồm 20
  phép lặp khi giá ngẫu nhiên và 20 khi có nhiễu quan sát được. Phương án
  được chọn và đánh giá trên hai tập riêng. Khi có nhiễu quan sát được,
  hồi quy không điều chỉnh bối cảnh làm giá trị đặt xe giảm **30,29**,
  còn hồi quy có điều chỉnh và phương pháp học máy DML cùng làm tăng
  **16,08** so với giữ nguyên giá. Đơn vị là giá trị chuẩn hóa trên 1.000
  phiên xem báo giá. Kết quả cho thấy sai lệch ước lượng có thể dẫn đến
  quyết định giá bất lợi, chưa phải mức thay đổi doanh thu GSM.

Em cũng đã củng cố kiểm tra đầu vào, xử lý lỗi và việc lưu tiến độ để tiếp
tục các lượt chạy. Kết quả được lưu cùng cấu hình và thông tin nguồn để
đối chiếu. Số liệu và phương pháp chi tiết nằm trong
[weekly report](weekly_report.md).

## 3. Vướng mắc và phần còn lại

Trong trường hợp giá ngẫu nhiên, khoảng tin cậy 95% của hồi quy có điều
chỉnh và DML cho tác động của giá Y lên xác suất chọn Y chỉ chứa tác động
thật ở **86/100 lần đánh giá**. Vì vậy, sai số ước lượng nhỏ chưa bảo đảm
độ tin cậy của khoảng ước lượng. Cần ghi nhận hạn chế này và thống nhất
cách nghiệm thu với người kiểm tra. **Không còn chờ kết quả chạy.**

Bộ mô hình cầu và lựa chọn bàn giao cuối cùng, các tệp kết quả đi kèm và
lần kiểm tra tái lập tương ứng vẫn cần hoàn thiện. Dữ liệu gốc GSM chưa có,
nên chưa thể đánh giá tác động giá hoặc kết quả kinh tế thực tế. Mô hình
cung và mô phỏng vận hành thuộc phần việc tiếp theo.

## 4. Kế hoạch tiếp theo

1. **Chốt tuần 2:** thống nhất cách ghi nhận hạn chế của khoảng tin cậy,
   hoàn thiện bộ mô hình và kết quả bàn giao, kiểm tra khả năng tái lập.
   Nếu cải thiện phương pháp, dùng dữ liệu phát triển và tập đánh giá mới.

2. **Tuần 3:** kết nối mô hình cầu với mô phỏng vận hành, bắt đầu bằng
   đội xe có cung cố định. Kiểm tra phân xe, thời gian chờ, hủy chuyến,
   nhàn rỗi và sạc trước khi bổ sung phản ứng cung và cân bằng cung–cầu.

3. **Dữ liệu và các bước tuần 3–5:** cần tám nhóm dữ liệu gốc của GSM trong
   12 tháng gần nhất, gồm vùng lân cận và đối chứng, như nêu trong weekly
   report. Tiếp tục đánh giá vận hành–kinh tế, thiết kế thử nghiệm luân
   phiên chính sách theo thời gian và đối chiếu dự báo với thực tế. Thử
   nghiệm trên GSM chỉ thực hiện khi đủ dữ liệu và được chấp thuận.
