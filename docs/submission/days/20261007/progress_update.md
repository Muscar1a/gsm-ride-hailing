# Cập nhật tiến độ PoC GSM — Week 2

**Nguyễn Thành An · 26ai.annt@vinuni.edu.vn · 07/10/2026**

**Chốt số liệu:** 10:41:19, Asia/Bangkok (UTC+07). Chi tiết:
[báo cáo PoC](weekly_report.md).

**Phần đã thực hiện.** PoC có pipeline TLC, kiểm tra chất lượng/đối soát,
sinh lựa chọn mô phỏng, OLS/DML, bootstrap theo ngày, kịch bản giá, CSV/JSON và
dashboard ba màn hình. Phạm vi TLC tháng 01/2024 gồm **970.940 chuyến hoàn tất**.
Kết quả đã nộp được giữ nguyên: benchmark **20 seed/DGP × 5 DGP** hoàn tất,
điều chỉnh giảm sai số so với naive OLS khi nhiễu quan sát được; adjusted OLS
hơi tốt hơn DML trong trường hợp đó. Một run TLC-context có **199/199 bootstrap
refits mỗi estimator**. Các kết quả này chưa xác lập coverage hoặc tác động GSM.

**Bổ sung từ bản đã nộp.** Các commit 05–06/10 cập nhật thiết kế/contract và
củng cố dữ liệu, lỗi từng estimator, nhận dạng, bootstrap, artifact và type checks.
Trong đợt làm việc hiện tại đã triển khai Swissmetro với split theo người:
test **1.611 nhiệm vụ/179 người**, log loss MNL **0,781474**, baseline **0,881660**;
kiểm tra hội tụ/availability/checksum đạt. Rà soát nguồn ngày 07/10:
[EPFL/Biogeme](https://biogeme.epfl.ch/) nêu dữ liệu được dùng
cho nghiên cứu/giáo dục, đủ căn cứ provenance cho PoC học thuật; quyền tái phân
phối/sử dụng thương mại chưa được xác nhận. Swissmetro chạy lại trên mã cuối giữ
nguyên metrics/predictions. **Policy-value development đã hoàn tất 40 seed jobs**
(20 RCT + 20 observed), chọn trên validation và chấm bằng oracle test độc lập.
RCT: ba learner hòa nhau; observed: naive OLS uplift **−30,291142**, adjusted
OLS/DML cùng **+16,075210** đơn vị giá trị booking chuẩn hóa/1.000 quote sessions.
Simple rule có **7 fallback**, không fit/test failure. Đây chưa phải doanh thu GSM.
Kiểm tra mã có **131 tests passed**, Ruff đạt, ty đạt trên toàn bộ mã nguồn;
policy/Swissmetro đã xác minh dùng lại artifact. Phần bổ sung chưa commit.

**Tiến độ và phần còn thiếu.** Coverage đầy đủ **500 seed jobs**, 199 draws mỗi
estimator được nhận dạng, đã chạy nền theo batch/checkpoint: tại thời điểm chốt
**69 thành công, 1 đang chạy (job 70/seed 20070), 0 thất bại, 430 chưa bắt đầu**.
Bảng tổng hợp đã có 65 seed RCT; bốn seed mới còn ở checkpoint. DML max theta
RMSE **0,011807**, scenario RMSE **0,003620**; coverage theo ô **86,15–93,85%**,
cần rà soát trước nghiệm thu đầy đủ. NULL_EFFECT chưa chạy; bộ bàn giao cuối
chưa chốt. So với proposal, đã có
nền dữ liệu, kiểm chứng cầu/thay thế chéo và demo, nhưng chưa có mô hình cung,
simulator matching/sạc/cân bằng/nhàn rỗi, kết quả kinh tế/ROI, switchback chi tiết
hoặc sổ đối chiếu. Tất cả kết quả hành vi hiện là **evidence C**; GSM raw data
chưa có, không chuyển hệ số public/synthetic sang GSM.

**Kế hoạch tiếp theo.** Hoàn tất/rà soát coverage;
kiểm tra bundle cuối, chốt bảng nghiệm thu week 2 và đồng bộ hai báo cáo. Tuần 3–5
phát triển cung/simulator, dashboard vận hành–kinh tế, switchback và bàn giao;
A/A/pilot chỉ khi đủ điều kiện và được GSM chấp thuận. Đề nghị GSM xuất **tám
nhóm nguồn gốc trong 12 tháng gần nhất**, gồm vùng lân cận/đối chứng; người thực
hiện tự ánh xạ/nối/xử lý theo [data contract](../../../GSM_DATA_CONTRACT.md).
Demo hiện chạy cục bộ. [Bảng rà soát nghiệm thu](acceptance_review.md) ghi bằng
chứng từng gate. Week 2 **đạt một phần, chưa đóng toàn bộ**; tối ưu compute ở chat riêng.
