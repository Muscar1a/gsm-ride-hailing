# Báo cáo Tuần PoC GSM Causal Marketplace
*(Bản tổng hợp tiến độ và kết quả nghiên cứu kỳ 10/10 – 11/10/2026)*

**Người thực hiện:** Nguyễn Thành An · 26ai.annt@vinuni.edu.vn  
**Thời điểm chốt thông tin:** 15:11, ngày 11/10/2026 (Asia/Bangkok)  
**Kỳ báo cáo:** Từ ngày 10/10/2026 đến thời điểm chốt; đối chiếu với mốc báo cáo ngày 07/10/2026.

---

## 1. Tóm tắt tiến độ điều hành (Executive Summary)

Báo cáo tuần này tổng hợp toàn bộ tiến độ, các điều chỉnh thiết kế phương pháp luận và kết quả kiểm chứng kỹ thuật của dự án PoC GSM Causal Marketplace trong kỳ 10/10 – 11/10/2026.

### 1.1. Bảng hiện trạng các mốc nghiên cứu

| Mốc nghiên cứu | Trạng thái kỹ thuật | Đánh giá & Giới hạn cốt lõi |
|---|---|---|
| **Week 1 (Đặc tả bài toán)** | **Đã hoàn thành** | Khung đặc tả nhân quả đã thống nhất; mapping trường và tiêu chí kế toán GSM còn chờ đối tác bàn giao. |
| **Week 2 (Mô-đun Demand/Choice)** | **Nghiệm thu nội bộ (có ngoại lệ)** | Đóng gói mô hình độc lập; suy diễn kép bằng phương pháp toán học giúp tăng tốc ~37 lần; chấp nhận ngoại lệ độ bao phủ 88–89% ở tác động chéo. |
| **Phạm vi dữ liệu hỗ trợ (Common Support)** | **Đạt 67,5% bối cảnh** | Áp dụng ngưỡng an toàn $\ge 20$ khối quan sát; tự động từ chối dự báo 32,5% vùng thiếu dữ liệu để triệt tiêu sai lệch ngoại suy. |
| **Week 3 (Cung tài xế & Simulator)** | **Đang triển khai** | Đã có nền tảng simulator cung cố định; đang xây dựng mô hình cung lao động (participation/tổng giờ làm) và sổ cái thù lao. |
| **Dữ liệu thực tế GSM** | **Chưa bàn giao** | Sản phẩm hiện dừng ở mức độ PoC trên môi trường dữ liệu bán tổng hợp có kiểm soát (evidence C). |

### 1.2. Các kết quả và phát hiện trọng tâm trong kỳ

1. **Rà soát bài toán & chuẩn hóa thiết kế nhân quả:**
   - Nhận diện sai lệch trong cách tiếp cận trước đây (từng thu hẹp phản ứng cung của tài xế thành quyết định nhận chuyến ngắn hạn trong mô phỏng).
   - Thiết kế mới tách bạch rõ ràng ba phản ứng nhân quả độc lập: (1) độ nhạy giá của khách hàng, (2) mức độ thay thế giữa các dịch vụ X/Y, và (3) cung lao động của tài xế (tỷ lệ tham gia làm việc và tổng giờ làm việc thực tế).
   - Tái cấu trúc toàn bộ mã nguồn theo sáu nhóm chức năng tách biệt (`core`, `data`, `causal`, `simulation`, `pipeline`, `ui`) giúp tối ưu hóa khả năng bảo trì và kiểm thử.

2. **Đóng gói độc lập & tăng tốc suy diễn (~37 lần):**
   - Đóng gói hoàn chỉnh các mô hình OLS và DML thành các tệp kết quả cố định độc lập, có thể chạy lại và đưa ra dự báo mà không cần khởi chạy trình mô phỏng đội xe.
   - Bổ sung cơ chế tính khoảng tin cậy bằng **phương pháp toán học** (OLS HC3 và hàm điểm DML kết hợp Delta method). Thời gian xử lý trung vị giảm từ 1,12 giây xuống **0,03 giây/kịch bản** (nhanh hơn ~37 lần), trong khi vẫn bảo lưu tùy chọn tái lấy mẫu (bootstrap) dự phòng.

3. **Kiểm chứng thống kê khách quan & thận trọng:**
   - Triển khai kiểm chứng độc lập trên một tập mẫu (cohort) hoàn toàn mới gồm 100 seed (400/400 lượt fit thành công tuyệt đối, tạo ra 15.200 dòng kết quả dự báo).
   - Hệ số tự thân $Y/Y$ đạt độ bao phủ cao (**97–98%**). Mô hình kiểm soát tốt tỷ lệ dương tính giả (3–9%) khi không có can thiệp giá.
   - Báo cáo minh bạch **8 chỉ số kịch bản/tác động chéo** còn ghi nhận độ bao phủ ở mức **88–89%** (chưa đạt chuẩn danh nghĩa 95%), giữ nguyên cảnh báo thay vì che giấu sai số.

4. **Vướng mắc thực tế & Kế hoạch tuần tới (Week 3):**
   - **Vướng mắc chính:** Đối tác GSM chưa bàn giao dữ liệu thực tế và quy tắc kế toán doanh thu/chi phí, do đó mọi phân tích tài chính hiện thời chỉ có giá trị dự báo có điều kiện.
   - **Kế hoạch hành động:** Tập trung triển khai Week 3 bắt đầu từ mô hình hóa phản ứng cung lao động của tài xế và cơ chế trả công trên bộ dữ liệu mô phỏng có đáp án chuẩn, bảo đảm hoàn thiện khung phương pháp trước khi tiếp nhận dữ liệu thực.

---

## 2. Rà soát đề bài và điều chỉnh thiết kế

### 2.1. Cách hiểu ban đầu và điểm cần sửa

Trong quá trình rà soát lại đề bài, em nhận thấy mình đã diễn giải chưa đầy
đủ và đưa ra một số phán đoán chưa phù hợp về phạm vi triển khai. Em đã tập
trung quá nhiều vào phân cuốc, nhận chuyến và số chuyến hoàn thành, đồng thời
có lúc thu hẹp phản ứng cung của tài xế thành quyết định nhận một chuyến.
Cách hiểu này làm lệch trọng tâm nghiên cứu: đề bài yêu cầu đo tác động nhân
quả của giá và incentive lên nhu cầu khách hàng, sự thay thế giữa dịch vụ
và lượng lao động tài xế cung cấp.

Sai lệch này dẫn đến việc ưu tiên chi tiết simulator trước khi làm rõ đại
lượng cần đo về cung lao động. Tài xế đang online nhận thêm chuyến có thể
làm số chuyến hoàn thành tăng, trong khi số tài xế tham gia và tổng giờ làm
không đổi. Vì vậy, tỷ lệ nhận chuyến chưa đủ để trả lời câu hỏi incentive
làm nguồn cung thay đổi bao nhiêu.

Sau khi đối chiếu lại yêu cầu, em đã sửa đặc tả và thứ tự triển khai: tách
participation/giờ làm khỏi acceptance, xác định điều kiện nhận dạng cho từng
phản ứng, rồi dùng simulator để chuyển kết quả thành forecast thị trường.
Việc cập nhật tài liệu thiết kế đã hoàn thành; phần mô hình cung hành vi và
kết nối toàn chuỗi vẫn cần triển khai.

### 2.2. Bài toán sau khi làm rõ

Bài toán cần trả lời là: **khi thay đổi giá hoặc incentive, khách hàng và tài
xế phản ứng thế nào, thị trường thay đổi ra sao, và kết luận có độ tin cậy đến
mức nào?** Ba mục tiêu khoa học là phản ứng giá của khách, thay thế giữa X/Y
và phản ứng cung lao động của tài xế.

X/Y hiện là hai dịch vụ giả định; NONE là không đặt một trong hai dịch vụ,
chưa xác định khách chuyển sang đối thủ nào. Kịch bản giữ cố định số phiên
xem giá đo lựa chọn có điều kiện; chưa đo tác động lên lượng người xem giá,
quay lại hoặc tổng nhu cầu.

Khi đủ dữ liệu doanh thu, lương/thưởng tài xế và các chi phí thuộc phạm vi
kế toán được xác nhận, forecast phục vụ đánh giá chính sách làm GSM lãi thêm
hoặc giảm bao nhiêu sau chi phí. Số chuyến, chờ, hủy và nhàn rỗi giúp giải
thích kết quả kinh tế. Hiện chưa có dữ liệu GSM để đo lợi nhuận hoặc ROI thực.

### 2.3. Các thay đổi trong thiết kế

| Nội dung | Cách hiểu hoặc ưu tiên trước khi rà soát | Thiết kế sau điều chỉnh |
|---|---|---|
| **Cung tài xế** | Xem quyết định nhận cuốc (acceptance) là phản ứng cung chính | Đo tỷ lệ tham gia (*participation*) và tổng giờ làm việc trên toàn bộ tài xế đủ điều kiện; phân tách rạch ròi với quyết định nhận chuyến ngắn hạn |
| **Simulator** | Tập trung vào quy tắc phân cuốc và mức độ chi tiết vận hành | Ưu tiên đặc tả, ước lượng và kiểm chứng phản ứng nhân quả; simulator đóng vai trò cơ chế chuyển đổi (*translation mechanism*) thành dự báo thị trường |
| **Demand** | Kịch bản choice giữ số phiên xem giá cố định dễ bị hiểu rộng thành tổng cầu | Xác định rõ estimand có điều kiện; tác động lên tổng số lượt xem giá cần dữ liệu và nhận dạng bổ sung |
| **Hiệu quả chính sách** | Số chuyến và giá trị đặt xe (GMV) được dùng làm đầu ra trực tiếp của mô hình | Đánh giá kinh tế theo lợi nhuận sau chi phí (*incremental profit*); cần đầy đủ doanh thu, trả công, chi phí vận hành và phạm vi kế toán |

Các nguyên tắc thiết kế trọng tâm sau khi chuẩn hóa bao gồm:
1. **Nguyên tắc nhận dạng cung lao động:** Chính sách trả công và mức thưởng (*incentive*) phải được công bố trước thời điểm tài xế ra quyết định; thu nhập thực nhận chỉ là kết quả hoặc cơ chế trung gian. Mẫu nghiên cứu bắt buộc phải giữ lại toàn bộ tài xế đủ điều kiện (kể cả những người không tham gia ca làm việc, có số giờ bằng 0) để triệt tiêu sai lệch chọn mẫu (*selection bias*).
2. **Nguyên tắc phân chia dữ liệu & suy diễn:** Cơ chế chia tập huấn luyện/kiểm thử (split) và suy diễn nhân quả phải tôn trọng cấu trúc gán chính sách theo thời gian, hiện tượng lặp lại của khách/tài xế và ảnh hưởng tương tác giữa các khu vực địa lý; không áp đặt các giả định độc lập lý thuyết của dữ liệu mô phỏng sang dữ liệu thực tế.
3. **Nguyên tắc lượng hóa hiệu quả kinh tế:** Phân định rõ thứ bậc đo lường từ giá trị đặt xe -> doanh thu ghi nhận -> lợi nhuận sau toàn bộ chi phí/incentive. Do phía đối tác chưa bàn giao dữ liệu và quy tắc kế toán chính thức, mọi đánh giá tài chính hiện tại chỉ có giá trị dự báo có điều kiện (*conditional forecast*).


### 2.4. Ảnh hưởng đến kết quả đã có

Kết quả demand/choice và simulator cung cố định được giữ trong phạm vi kiểm
chứng ban đầu. Chúng tiếp tục là nền cho phần tiếp theo, nhưng chưa xác nhận
phản ứng cung lao động, cân bằng thị trường hoặc hiệu quả kinh tế toàn chuỗi.
Số liệu cũ được giữ nguyên; thay đổi cách diễn giải không tạo thêm bằng chứng
về những thành phần chưa đo.

## 3. Công việc đã thực hiện trong kỳ

### 3.1. Hoàn thiện đặc tả và tổ chức mã

Em đã xác định treatment/contrast, outcome, đối tượng, thời hạn, đơn vị và
điều kiện nhận dạng cho ba nhóm phản ứng. Kế hoạch đánh giá giữ baseline đơn
giản, học/chọn phương án trên train/validation và dùng tập cuối riêng để đánh
giá. Tiêu chí kinh doanh, mức tác động đáng thử và guardrails GSM còn chờ xác
nhận; các giá trị development minh họa chưa thay thế quyết định nghiệp vụ.

Mã được tổ chức thành `core`, `data`, `causal`, `simulation`, `pipeline`, `ui`,
tách các tab và benchmark theo trách nhiệm để thuận tiện bảo trì. Việc tổ
chức lại mã chưa phải bằng chứng cải thiện chất lượng ước lượng.

### 3.2. Mô hình lựa chọn dịch vụ và cơ chế suy diễn kết hợp

Mô hình ước lượng ma trận hệ số tác động giá ($\theta$), trong đó mỗi phần tử thể hiện mức thay đổi xác suất lựa chọn dịch vụ (hàng) khi giá của một dịch vụ thay đổi một đơn vị log giá (cột). Mô hình OLS không điều chỉnh được dùng làm mốc đối chứng để minh họa sai lệch khi bỏ qua yếu tố gây nhiễu; OLS có điều chỉnh và DML (Double Machine Learning) kiểm soát các đặc trưng bối cảnh trước thời điểm ra quyết định. Từ ma trận hệ số này và xác suất lựa chọn cơ sở, mô hình suy diễn ra độ co giãn giá của nhu cầu.

Để tính khoảng tin cậy nhanh chóng thay vì chỉ phụ thuộc vào tái lấy mẫu (bootstrap) tốn kém tài nguyên, em đã bổ sung phương pháp toán học: sử dụng sai số chuẩn vững OLS HC3 với phân phối Student-t, và hàm số điểm trực giao (orthogonal score) với phân phối chuẩn cho DML. Ma trận hiệp phương sai chung được xây dựng để lưu vết toàn bộ mối tương quan giữa các hệ số tác động và hệ số cơ sở, sau đó dùng phương pháp Delta (Delta method) để truyền bất định sang các dự báo độ co giãn và xác suất kịch bản. Các khoảng tin cậy được tính riêng cho từng kết quả đầu ra; mô hình OLS thô sơ không điều chỉnh vẫn giữ nguyên cách tính bootstrap để bảo đảm tính thận trọng.

Về mặt triển khai, mô hình lựa chọn sau khi ước lượng được đóng gói độc lập thành các tệp kết quả cố định, tách rời hoàn toàn quá trình huấn luyện nhân quả khỏi quá trình mô phỏng thị trường. Khi bổ sung phương pháp tính khoảng tin cậy bằng phương pháp toán học, hệ thống tạo một phiên bản kết quả mở rộng riêng biệt: tự động đối soát tính toàn vẹn của dữ liệu và hệ số gốc, bổ sung ma trận hiệp phương sai mà không làm thay đổi hay ghi đè lên các tệp kết quả lịch sử. Khi chạy kịch bản dự báo, hệ thống ưu tiên dùng phương pháp toán học để đạt tốc độ cao, nhưng vẫn bảo lưu tùy chọn tái lấy mẫu (bootstrap) để kiểm tra đối chiếu khi cần.

Hệ thống thiết lập cơ chế kiểm soát an toàn nghiêm ngặt: nếu ma trận hiệp phương sai bị thiếu, suy biến hoặc không tương thích với dữ liệu, hệ thống sẽ từ chối đưa ra khoảng tin cậy thay vì đưa ra con số sai lệch. Việc đạt trạng thái "ổn định về mặt kỹ thuật" (*Technically stable*) khẳng định thuật toán và phần mềm chạy đúng, không có lỗi tính toán hay đổ vỡ logic, nhưng được tách biệt rạch ròi với việc kiểm định độ bao phủ thống kê thực tế (vốn vẫn cần tiếp tục hoàn thiện để đạt mức chuẩn danh nghĩa 95%).

## 4. Kết quả kiểm chứng

### 4.1. Dữ liệu hiện có và khả năng tái lập

**GSM chưa bàn giao dữ liệu tại thời điểm chốt.** Tám nhóm nguồn dữ liệu nghiệp vụ cần thiết (gồm: phiên xem giá/quote, cuốc xe hoàn tất, cuốc xe hủy, đăng ký ca làm việc của tài xế, lịch sử phát/nhận chuyến, chính sách thù lao/thưởng, cấu trúc chi phí & hoa hồng, và bản đồ vùng hoạt động) hiện chưa có dữ liệu thực tế; mapping trường, tiêu chí kinh doanh và quy tắc kế toán vẫn đang chờ xác nhận.

**Nguồn dữ liệu bối cảnh và cơ chế mô phỏng:** Để xây dựng và kiểm chứng trước khung phương pháp luận, toàn bộ thử nghiệm hiện thời được triển khai trên tập dữ liệu mở của Ủy ban Taxi và Xe công nghệ New York (NYC TLC HVFHV, tháng 01/2024). Dữ liệu này bao gồm **970.940 chuyến xe hoàn tất** tại khu vực trung tâm, được dùng làm bối cảnh không gian – thời gian thực tế, kết hợp với cơ chế phát sinh lựa chọn bán tổng hợp có kiểm soát. Dữ liệu được chia theo các ngày hoàn toàn độc lập để chống rò rỉ thông tin theo chuỗi thời gian: tập huấn luyện gồm **4.800 khối**, tập kiểm định gồm **1.200 khối**, và tập kiểm thử độc lập gồm **1.440 khối** (mỗi khối tương ứng một khung giờ và khu vực cụ thể).

**Giới hạn của nguồn dữ liệu:** Dữ liệu NYC TLC chỉ ghi nhận các chuyến xe đã hoàn thành, hoàn toàn chưa quan sát được các phiên xem giá nhưng khách không đặt xe, cũng như chưa phản ánh đặc thù hành vi và cung lao động của tài xế GSM tại Việt Nam. Do đó, toàn bộ kết quả hiện dừng ở mức độ thực nghiệm kiểm chứng phương pháp trong môi trường giả lập; không tự ý suy rộng các hệ số này sang thị trường thực tế.

**Bảo đảm tính tái lập (Reproducibility):** Mọi thực nghiệm đều được thiết kế để bảo đảm khả năng tái lập tuyệt đối: môi trường thực thi được cố định chặt chẽ (Python 3.11.9 cùng phiên bản cụ thể của các thư viện tính toán) và seed ngẫu nhiên được ấn định rõ ràng. Mọi tập dữ liệu trung gian và mô hình đều được xác thực tính toàn vẹn bằng mã kiểm tra (checksum SHA-256). Phiên bản suy diễn bằng phương pháp toán học mới được xây dựng trực tiếp trên nền tảng mô hình cơ sở đã được kiểm chứng trước đó, bảo đảm các kết quả so sánh đều dựa trên cùng một chuẩn đối chiếu và có thể chạy lại độc lập mà không làm thay đổi các kết quả lịch sử.

### 4.2. Đánh giá phạm vi dữ liệu hỗ trợ khi can thiệp giá (Common Support)

Khi đưa mô hình vào chạy thử nghiệm kịch bản chính sách giá (ví dụ: tăng giá dịch vụ X thêm 10% và giữ nguyên giá Y), em nhận thấy hiện tượng **thiếu dữ liệu hỗ trợ (lack of common support)** xảy ra ở một bộ phận đáng kể các phiên giao dịch.

Cụ thể, để tránh rủi ro ngoại suy phi căn cứ (*extrapolation bias*), em đặt ngưỡng an toàn là trong dữ liệu huấn luyện phải có tối thiểu 20 khối quan sát ở tổ hợp giá và điều kiện tương ứng thì mới cho phép dự báo. Kết quả đối soát trên tập kiểm thử cho thấy:

| Phạm vi | Quy mô | Trạng thái dữ liệu hỗ trợ (Support) | Đánh giá |
|---|---|---|---|
| **Toàn bộ bối cảnh thử nghiệm** | 1.440 khối / 72.000 phiên xem giá | Không đủ dữ liệu trên toàn mạng lưới | Chưa thể dự báo đại trà |
| **Vùng có dữ liệu hỗ trợ** | 10/20 nhóm; 972 khối / 48.600 phiên | Đạt ngưỡng an toàn ($\ge 20$ khối) | **Dự báo tin cậy (chiếm 67,5% tổng số phiên)** |
| **Vùng thiếu dữ liệu** | 10/20 nhóm; 468 khối / 23.400 phiên | Dưới ngưỡng an toàn | **Tự động từ chối dự báo (chiếm 32,5% tổng số phiên)** |

Thay vì cố gắng dự báo trên toàn bộ dữ liệu, em chủ động cài đặt cơ chế cảnh báo và chỉ xuất kết quả cho vùng 67,5% phiên có đủ dữ liệu lịch sử hỗ trợ. Em cũng lưu ý rằng con số 67,5% này mới chỉ phản ánh độ bao phủ trong tập dữ liệu thử nghiệm hiện tại; khi nhận dữ liệu thực tế từ GSM, em sẽ cần đánh giá lại mật độ quan sát để xác định chính sách giá mới có thể áp dụng an toàn cho bao nhiêu phần trăm thị trường thực.

### 4.3. Chẩn đoán nguyên nhân biến động của khoảng tin cậy

Trước đó, em thử nghiệm hệ số Y/Y và ghi nhận coverage khoảng (86/100). Em đã tiến hành các thực nghiệm chẩn đoán đa chiều nhằm tìm hiểu nguyên nhân: liệu việc tăng số lượng mẫu bootstrap, đổi dạng khoảng (Percentile, BCa) hay điều chỉnh ước lượng phương sai có giải quyết được hiện tượng này hay không.

| Thử nghiệm chẩn đoán | Kết quả quan sát | Nhận xét & Ý nghĩa |
|---|---|---|
| Tái lấy mẫu bootstrap gốc (20 seeds OLS) | Tỷ số độ lệch chuẩn bootstrap / độ lệch chuẩn thực tế: Y/Y đạt 85,6%, Y/X đạt 78,8% | Khoảng tin cậy bị hẹp hơn thực tế trong nhóm mẫu này; chưa cô lập được nguyên nhân duy nhất |
| Tăng số lần lấy mẫu từ 199 lên 999 draws | Độ rộng khoảng Y/Y chỉ tăng trung bình ~2,3% | Việc chỉ tăng số lần lấy mẫu không giải quyết được căn nguyên thiếu độ bao phủ |
| So sánh các dạng khoảng Percentile, Basic, BCa | Tỷ lệ bao phủ Y/Y lần lượt là 17/20, 17/20, 18/20 | Chênh lệch nhỏ, chưa đủ bằng chứng để khẳng định BCa ưu việt hơn hẳn |
| Thử nghiệm Day-jackknife (tái sử dụng refit) | Độ bao phủ Y/Y đạt 19/20, độ rộng tăng ~14% | Mang tính phân tích độ nhạy, chưa tạo thêm bằng chứng độc lập |
| Thử nghiệm nhỏ DML và OLS (5 seeds mỗi môi trường) | Độ bao phủ Y/Y đạt 5/5, Y/X đạt 3/5 ở cả hai | Quy mô nhỏ chưa đủ để quy lỗi riêng cho thuật toán DML |
| Chẩn đoán ma trận điểm số kết hợp (252 lượt fit) | Đánh giá toàn diện trên hệ số, độ co giãn và các fold | Cho thấy tương quan chéo giữa các hệ số là nguyên nhân chính cần kiểm soát |

Để kiểm tra độ chuẩn xác của công thức, em sử dụng phương pháp **phương sai lý thuyết (Oracle Variance)** trên 200 bộ dữ liệu. Kết quả cho thấy phương sai OLS HC3 tính toán được khớp với phương sai lý thuyết với sai khác tối đa chỉ **$5,32 \times 10^{-14}$**, khẳng định công thức toán học được cài đặt hoàn toàn chính xác. Nguyên nhân khoảng tin cậy bị hẹp một phần bắt nguồn từ cấu trúc gom nhóm theo ngày (day grouping) trong dữ liệu mô phỏng.

### 4.4. Kiểm chứng độc lập trên tập thử nghiệm cố định

Sau khi phương pháp và tiêu chí đánh giá được cố định, em tiến hành kiểm chứng độc lập trên một cohort hoàn toàn mới gồm **100 seed (45001–45100)** trên hai môi trường dữ liệu: can thiệp giá ngẫu nhiên và không có can thiệp giá. Toàn bộ **400/400 lượt fit** đều thành công, tạo ra 15.200 dòng kết quả dự báo kèm khoảng tin cậy mà không gặp bất kỳ lỗi tính toán nào.


Coverage là số seed có CI chứa truth, mẫu số 100 cho từng ô:

| Ô outcome/price, RCT | Theta OLS | Theta DML | Elasticity OLS | Elasticity DML |
|---|---:|---:|---:|---:|
| X/X | 94/100 | 94/100 | 95/100 | 93/100 |
| X/Y | 93/100 | 89/100 | 93/100 | 90/100 |
| Y/X | 97/100 | 96/100 | 97/100 | 96/100 |
| Y/Y | 97/100 | 98/100 | 96/100 | 97/100 |

Scenario RCT có coverage riêng từng output **89–100/100 với OLS, 88–98/100
với DML**; NULL tương ứng **89–100/100 và 88–100/100**. Toàn bộ **12.000 scenario
rows** thiếu support ở full-context theo quy tắc hiện hành. Kiểm chứng thống
kê này chưa cho phép dùng full-context để quyết định giá.

| Ô theta, NULL | OLS false positives | DML false positives |
|---|---:|---:|
| X/X | 5/100 | 5/100 |
| X/Y | 9/100 | 9/100 |
| Y/X | 3/100 | 5/100 |
| Y/Y | 6/100 | 4/100 |

**Nhận xét và giới hạn thống kê cần lưu ý:**
- **Về độ bao phủ (Coverage):** Dù các hệ số tác động chính đạt độ bao phủ cao (94–98%), vẫn có **8 chỉ số kịch bản và tác động chéo** (đặc biệt là tác động thay thế $X/Y$ ở mô hình DML) chỉ đạt độ bao phủ ở mức **88–89%** (thấp hơn mức danh nghĩa 95%). Khi kiểm định đồng thời trên toàn bộ 168 chỉ số đánh giá với hiệu chỉnh Holm ($\alpha = 0,05$), sai lệch này chưa đủ lớn để bị bác bỏ về mặt thống kê. Tuy nhiên, em giữ thái độ thận trọng: việc chưa bị bác bỏ không đồng nghĩa với việc mọi khoảng tin cậy đều đã đạt chuẩn 95%. Do các đầu ra kịch bản có tương quan với nhau, 8 chỉ số này phản ánh một hạn chế thực tế là khoảng tin cậy của tác động chéo hiện tại còn hơi hẹp so với mức biến động thực tế của dữ liệu.
- **Về việc so sánh với mốc lịch sử:** Hệ số tự thân $Y/Y$ đợt này đạt 97–98%, cải thiện rõ rệt so với con số 86/100 ở báo cáo ngày 07/10. Tuy nhiên, vì hai đợt thử nghiệm được chạy trên hai tập mẫu (cohort) độc lập, em không vội quy sự chênh lệch này thành một bước nhảy vọt tuyệt đối, mà ghi nhận đây là kết quả của việc chuẩn hóa lại quy trình suy diễn bằng phương pháp toán học mới.
- **Về kiểm định giả thuyết không (NULL test):** Tỷ lệ dương tính giả (*false positive rate*) khi không có can thiệp giá được kiểm soát tốt trong ngưỡng 3–9% (phù hợp với mức danh nghĩa 5%), chứng minh mô hình không ngộ nhận tác động ảo khi giá không đổi. Dù vậy, bài kiểm tra này mới chỉ xác nhận khả năng kiểm soát sai lầm loại I (*Type I error*), chứ chưa đo lường được năng lực thống kê (*statistical power*) trong việc phát hiện các thay đổi giá nhỏ nhưng có ý nghĩa kinh doanh khi áp dụng vào dữ liệu thực tế của đối tác.

### 4.5. Tích hợp, hiệu năng và kiểm chứng kỹ thuật

**Hiệu năng tính toán của phương pháp toán học:** 
Việc tính toán ma trận hiệp phương sai cho cả hai mô hình chỉ mất **5,51 giây**, với dung lượng lưu trữ bổ sung rất nhỏ (~40 KB mỗi mô hình). Phương pháp toán học cho phép tính toán các điểm dự báo nhu cầu gần như tức thì mà không cần nạp các mẫu tái lấy mẫu nặng nề vào bộ nhớ.

| Phương pháp đánh giá (Mô hình DML) | Phương pháp toán học (Analytic) | Tái lấy mẫu (Bootstrap) |
|---|---:|---:|
| Số kịch bản đo kiểm chuẩn | 5 | 5 |
| Thời gian trung vị (Median) / kịch bản | 0,03048 giây | 1,12195 giây |

Trên cùng một mô hình và 1.440 bối cảnh kiểm định, phương pháp toán học giúp tăng tốc độ xử lý khoảng **37 lần** (từ 1,12 giây giảm xuống 0,03 giây trên mỗi kịch bản). Mức tăng tốc vượt bậc này cho phép phản hồi tức thì khi người dùng thay đổi các giả định giá trên giao diện mô phỏng.

**Kiểm thử tích hợp và tính ổn định:**
Toàn bộ hệ thống vượt qua **423 bài kiểm thử tự động**, bao gồm kiểm tra tính toán hiệp phương sai, tính đúng đắn của khoảng tin cậy, khả năng tái lập và tính tương thích với mô-đun nhu cầu. Các công cụ kiểm tra cú pháp và kiểu dữ liệu tĩnh (Ruff và Ty) đều đạt kết quả chuẩn xác, khẳng định hệ thống đạt độ ổn định kỹ thuật cao trước khi bước sang giai đoạn tiếp theo.

## 5. Trạng thái hoàn thành và giới hạn còn mở

| Hạng mục | Trạng thái tại ngày 11/10 | Đánh giá & Giới hạn |
|---|---|---|
| **Week 1 (Đặc tả bài toán)** | Đã hoàn tất khung đặc tả | Đã thống nhất 3 phản ứng nhân quả; chờ dữ liệu và quy tắc kế toán GSM |
| **Week 2 (Mô-đun Demand/Choice)** | Nghiệm thu kỹ thuật nội bộ | Thuật toán ổn định, chấp nhận ngoại lệ độ bao phủ 88–89% trên dữ liệu bán tổng hợp |
| **Dữ liệu hỗ trợ (Common Support)** | Đạt 67,5% số phiên thử nghiệm | Đạt ở 10/20 nhóm bối cảnh có $\ge 20$ khối quan sát; từ chối dự báo 32,5% vùng thiếu dữ liệu |
| **Độ bao phủ (Coverage)** | Đạt 97–98% ở hệ số tự thân | Duy trì cảnh báo tại 8 kịch bản/tác động chéo đạt 88–89% (chưa đạt chuẩn nominal 95%) |
| **Week 3 (Cung tài xế & Simulator)** | Đang triển khai | Đã có simulator cung cố định; mô hình phản ứng cung lao động và pipeline dự báo đang phát triển |
| **Kinh tế / Thực tế GSM** | Chưa đánh giá | Chưa có dữ liệu thực tế từ đối tác để đo ROI hay lợi nhuận thực |

*Lưu ý về Simulator hiện tại:* Simulator kế thừa từ giai đoạn trước gồm các yêu cầu Poisson/fixture, ghép xe, đón/chở khách, thời gian chờ, nhàn rỗi và hủy cuốc trước đón. Hệ thống hiện vẫn giả định tài xế nhận chuyến ngay, quy mô đội xe cố định và pin tĩnh. Đây là các giả định mô phỏng kỹ thuật, chưa phản ánh các quy tắc vận hành và hành vi thực tế của tài xế GSM.

## 6. Vướng mắc và kế hoạch hành động tiếp theo

### 6.1. Vướng mắc hiện tại
- **GSM chưa bàn giao dữ liệu:** Chưa kiểm chứng được bảng ánh xạ dữ liệu (mapping), hành vi thực tế của khách hàng và tài xế, cũng như tác động giá/incentive lên lợi nhuận thực của GSM. Các tiêu chí kinh doanh, ngưỡng cải thiện đáng thử và giới hạn ngân sách vận hành vẫn đang chờ đối tác xác nhận.
- **Ngoại lệ thống kê chưa đóng hoàn toàn:** Mức độ bao phủ danh nghĩa 95% cho toàn bộ các đầu ra và dữ liệu hỗ trợ cho toàn thị trường còn mở (có 8 chỉ số kịch bản/tác động chéo ở mức 88–89%).
- **Các mắt xích kinh tế toàn chuỗi chưa hoàn tất:** Mô hình phản ứng cung lao động, cơ chế trả công/thu nhập, quyết định nhận chuyến ngắn hạn, cân bằng thu nhập–cung và quy tắc kế toán lợi nhuận cần tiếp tục hoàn thiện.

### 6.2. Kế hoạch triển khai chi tiết
1. **Bắt đầu Week 3 từ phản ứng cung lao động:** Chốt định nghĩa và đại lượng đo lường cung; giữ toàn bộ tài xế đủ điều kiện nhưng không tham gia (với số giờ làm việc bằng 0) để triệt tiêu sai lệch chọn mẫu. Sử dụng dữ liệu mô phỏng bán tổng hợp có đáp án chuẩn để kiểm chứng phương pháp trong khi chờ dữ liệu GSM.
2. **Triển khai cơ chế trả công và chào cuốc xe:** Tách bạch điều khoản chào trước quyết định khỏi thu nhập thực nhận; kiểm thử các trạng thái nhận chuyến, từ chối chuyến, hết hạn và hạch toán chi phí thưởng.
3. **Ước lượng cung và tích hợp với mô-đun nhu cầu:** Bắt đầu bằng mô hình cơ sở đơn giản; kiểm tra hiệu ứng nhân quả, khoảng tin cậy và phạm vi dữ liệu hỗ trợ trên tập độc lập. Bổ sung lịch trình xe/tài xế khả thi và vòng lặp phản hồi thu nhập–cung có giới hạn số vòng lặp, có cơ chế bắt lỗi khi không hội tụ.
4. **Chuẩn bị cho Week 4–5 theo điều kiện dữ liệu:** So sánh chính sách giá, incentive và chính sách kết hợp trên phạm vi có đủ dữ liệu hỗ trợ; chuẩn bị thiết kế thí nghiệm A/B và đóng gói bộ bàn giao tái lập hoàn chỉnh.

## 7. Hồ sơ thực nghiệm và cơ sở đối soát

Báo cáo tuần này được xây dựng độc lập và tự đầy đủ, tích hợp trọn vẹn từ bản cập nhật tiến độ điều hành đến báo cáo kỹ thuật chi tiết nhằm tạo thuận tiện tối đa cho việc theo dõi và đối soát.

Toàn bộ tài nguyên kỹ thuật, mã nguồn và kết quả thực nghiệm liên quan đã được đóng gói và lưu vết trong mã nguồn PoC để sẵn sàng phục vụ việc đối soát và tái lập kết quả khi cần:
- **Dữ liệu & kết quả đánh giá độc lập:** Lưu vết 400 lượt fit đóng băng (seeds 45001–45100), 15.200 dòng dự báo kèm khoảng tin cậy, và bảng tổng hợp 168 chỉ số kiểm định (độ bao phủ coverage và tỷ lệ dương tính giả NULL false positive).
- **Hồ sơ tích hợp & nghiệm thu kỹ thuật:** Lưu vết môi trường thực thi chuẩn hóa (Python 3.11.9, uv lockfile), mã kiểm tra SHA-256 cho 20 tệp kết quả cơ sở, cùng toàn bộ 423 bài kiểm thử tự động đạt chuẩn kỹ thuật nội bộ.
- **Mã thực thi chẩn đoán:** Lưu vết các công cụ tính sai số theo phương pháp toán học (OLS HC3 / DML score), truyền sai số qua Delta method và các kịch bản đối chiếu phương sai oracle.

## Phụ lục. Các đợt kiểm chứng và phạm vi sử dụng

| Nhánh thực nghiệm | Seed / Quy mô | Vai trò & Mục đích |
|---|---|---|
| **Reporting 07/10** | Seeds 20001–20100 (5 DGP, 500 jobs) | Mốc đối chiếu lịch sử; cố định nguyên trạng, không can thiệp hay sửa đổi số liệu |
| **Chẩn đoán Bootstrap gốc** | Seeds 41001–41020 (OLS RCT/NULL; probes riêng) | Kiểm tra độ lệch chuẩn bootstrap và so sánh đầu mút giữa 199 và 999 draws |
| **So sánh dạng khoảng & Day-jackknife** | Seeds 42001–42020 (OLS RCT/NULL; 1 DML probe) | So sánh các dạng khoảng Percentile, Basic, BCa và phân tích độ nhạy gom nhóm theo ngày |
| **Thử nghiệm Pilot phương sai DML** | Seeds 43001–43005 (OLS/DML RCT/NULL) | Thử nghiệm quy mô nhỏ: 20 lượt fit điểm và 400 lượt refit theo ngày |
| **Chẩn đoán điểm số kết hợp (Joint score)** | OLS 100 seeds/DGP, DML 20 seeds/DGP (252 fits) | Đánh giá ma trận hiệp phương sai, độ co giãn kịch bản và độ nhạy trên các fold |
| **Kiểm chứng độc lập (Independent assessment)** | Seeds 45001–45100 (OLS/DML RCT/NULL) | Tiêu chí và phương pháp cố định; 400 lượt fit độc lập, 100 seed cho mỗi mô hình và môi trường |
