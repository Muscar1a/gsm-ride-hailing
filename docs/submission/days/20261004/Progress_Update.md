# Cập nhật tiến độ PoC GSM

**Người thực hiện và nộp duy nhất: Nguyễn Thành An · Email: 26ai.annt@vinuni.edu.vn**

**Tiến độ hiện tại.** Hoàn thiện phiên bản PoC ước lượng tác động
giá đến lựa chọn dịch vụ và kiểm tra kịch bản giá. Pipeline gồm nhập và kiểm tra
dữ liệu, tạo bảng vận hành, sinh lựa chọn bán tổng hợp, ước lượng bằng OLS và DML,
bootstrap theo ngày, xuất kết quả và dashboard. Dữ liệu TLC tháng 01/2024 cung cấp
bối cảnh vận hành; phạm vi năm vùng gồm 970.940 chuyến hoàn tất đã được đối soát.
Các lựa chọn khách hàng và tác động giá là dữ liệu mô phỏng, không phải quan sát
GSM. Kiểm tra tự động đạt 42 bài kiểm thử. Benchmark 20 seed mới cho mỗi trường
hợp trong năm trường hợp đã hoàn tất; OLS có điều chỉnh và DML giảm sai số so với
OLS đơn giản khi nhiễu gây confounding được quan sát. Một lần chạy dùng bối cảnh
TLC hoàn tất 199/199 bootstrap cho mỗi phương pháp. Đây là bằng chứng kiểm chứng
phương pháp trong điều kiện đã thử, chưa chứng minh tăng doanh thu thực tế.

**Đối chiếu mục tiêu và vướng mắc.** Căn cứ [proposal ban đầu](../../../reference/GSM_Causal_Marketplace_Proposal.md),
PoC mới kiểm chứng cầu/thay thế chéo với ma trận chung và số phiên cố định, mức C.
Chưa có phản ứng cung, simulator một cụm hiệu chỉnh với cân bằng/nhàn rỗi, đầu ra
kinh tế/ROI, thiết kế switchback chi tiết và sổ đối chiếu. Dữ liệu GSM chưa có;
benchmark chính sách độc lập, kiểm chứng coverage nhiều run và baseline lựa chọn
Swissmetro riêng theo tài liệu yêu cầu dữ liệu còn thiếu.

**Kế hoạch tiếp theo.** Tiếp tục phần việc tuần 3–5 của proposal trên dữ liệu tổng hợp:
phản ứng cung, simulator/cân bằng, dashboard vận hành–kinh tế, thiết kế switchback
và sổ đối chiếu; bổ sung baseline Swissmetro, benchmark chính sách độc lập và coverage.
Đề nghị GSM xuất tám nhóm dữ liệu gốc trong 12 tháng gần nhất theo tài liệu yêu cầu,
gồm vùng lân cận/đối chứng; người thực hiện tự ánh xạ schema, nối khóa và xử lý.
Doanh thu/biên đóng góp/ROI thực tế cần dữ liệu hợp lệ, A/A/pilot cần đủ
điều kiện và phê duyệt. Mã nguồn đã công khai tại
[Muscar1a/gsm-ride-hailing](https://github.com/Muscar1a/gsm-ride-hailing);
demo hiện chạy cục bộ, chưa có URL công khai.

Nguồn kiểm chứng: [Kết quả đã chạy](../20261003/validation.md),
[kế hoạch benchmark](../../../BENCHMARK.md),
yêu cầu dữ liệu GSM (PDF nguồn không có trong checkout).
