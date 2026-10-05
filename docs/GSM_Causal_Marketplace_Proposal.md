# Đề xuất GSM Causal Marketplace

Problem 06 \| Nguyễn Thành An

## Bài toán và phạm vi đề xuất

**Bối cảnh.** Giá cước, thưởng tài xế và gói thuê bao là can thiệp mang tính cấu trúc trên thị trường hai phía của GSM. Mỗi thay đổi tác động cùng lúc tới cầu của khách ở một phía và nguồn cung lao động của tài xế ở phái kia. Vận hành hằng ngày là liên tục cân bằng hai phái này quanh một điểm cân bằng, theo từng khu vực và khung giờ.

**Vấn đề hiện tại.** Các can thiệp đang được đánh giá sau khi đã diễn ra, các dashboard tổng hợp số liệu quá khứ. Ba chỉ số quyết định hiệu quả chính sách vẫn được giả định từ tương quan chứ chưa được đo bằng phương pháp nhân quả:

| **Chỉ số**                 | **Câu hỏi cần trả lời**                                                     | **Vì sao tương quan dễ dẫn sai**                                                                                                               |
|----------------------------|-----------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| Độ nhạy giá của khách      | Giá dịch vụ tăng 1% thì yêu cầu đặt giảm bao nhiêu?                         | Giá thường được nâng đúng lúc cầu cao (mưa, giờ cao điểm). Dữ liệu có thể cho thấy giá cao đi kèm nhiều chuyến, dù thực chất giá làm giảm cầu. |
| Phản ứng nguồn cung tài xế | Thu nhập kỳ vọng hoặc thưởng tăng thì số giờ có thể phục vụ tăng bao nhiêu? | Thưởng thường đặt ở vùng và giờ đang thiếu xe. Xe chuyển vùng hoặc thay đổi lịch sạc dễ bị nhầm thành tăng cung thực.                          |
| Thay thế chéo giữa dịch vụ | Khi X tăng giá, bao nhiêu khách chuyển sang Y và bao nhiêu rời GSM?         | Các dịch vụ cùng chịu một cú sốc cầu chung nên thường tăng giảm cùng nhau, che mất phần chuyển dịch thực.                                      |

**Bài toán.** Tôi đề xuất xây dựng mô hình nhân quả để ước lượng ba chỉ số trên, rồi dùng chúng để dự báo phản thực tế cho từng kịch bản giá hoặc thưởng. Câu hỏi trung tâm là: “Nếu giá dịch vụ X tăng 10% tại một khu vực và khung giờ, thị trường dịch chuyển khỏi điểm cân bằng hiện tại như thế nào?” Câu trả lời gồm 4 đại lượng

| **Đại lượng dự báo** | **Cách đọc trên đồ thị cung–cầu**                    | **Độ co giãn quyết định**  |
|----------------------|------------------------------------------------------|----------------------------|
| Cầu giảm             | Khách trượt xuống dọc đường cầu                      | Độ nhạy giá của khách      |
| Cung tăng            | Tài xế leo lên dọc đường cung                        | Phản ứng nguồn cung tài xế |
| Chuyển dịch dịch vụ  | Phần cầu rời X đi sang Y hay rời khỏi GSM            | Thay thế chéo giữa dịch vụ |
| Nguồn cung nhàn rỗi  | Khoảng chênh giữa hai điểm cung và cầu ở mức giá mới | Kết hợp cả ba              |

Dự báo sau đó được kiểm chứng bằng thử nghiệm switchback: luân phiên chính sách theo khối khu vực và thời gian, rồi đối chiếu phản thực tế với kết quả thực gần như theo thời gian thực.

**Phạm vi trong năm tuần.**

| **Hạng mục**       | **Trong phạm vi**                                                                                           | **Ngoài phạm vi (giai đoạn sau)**                      |
|--------------------|-------------------------------------------------------------------------------------------------------------|--------------------------------------------------------|
| Đòn bẩy chính sách | Giá cước và thưởng tài xế. Gói thuê bao được xử lý như thay đổi giá hiệu dụng khi có dữ liệu người đăng ký. | Tự động thay đổi giá trên hệ thống thật                |
| Ước lượng          | Ba độ co giãn theo khu vực, khung giờ và dịch vụ, kèm khoảng tin cậy và mức bằng chứng A/B/C                | Định giá cá nhân hóa theo từng khách                   |
| Mô hình thị trường | Simulator một cụm, tính điểm cân bằng mới và nguồn cung nhàn rỗi cho mỗi kịch bản                           | Mô hình toàn thành phố và cạnh tranh với nền tảng khác |
| Kiểm chứng         | Thiết kế switchback và sổ đối chiếu dự báo–thực tế, sẵn sàng chạy trên một cụm khi GSM chấp thuận           | Thử nghiệm trên diện rộng                              |
| Đầu ra             | Dashboard so sánh kịch bản, xuất CSV/JSON                                                                   | Tối ưu điều phối từng chuyến                           |

**Tác động kỳ vọng.**

- Nền tảng cho định giá và phân bổ thưởng theo thuật toán, với ROI dự báo được và khoảng tin cậy thống kê chặt chẽ.

- Một mô hình thị trường minh bạch, dựa trên dữ liệu, đủ căn cứ để giải trình chiến lược giá với cơ quan quản lý đô thị.

**Đối tượng đánh giá**

*Đầu ra cho một kịch bản giá hoặc thưởng*

| **Nhóm đầu ra**         | **Nội dung**                                                                                                             |
|-------------------------|--------------------------------------------------------------------------------------------------------------------------|
| Cầu và lựa chọn dịch vụ | Thay đổi yêu cầu đặt của từng dịch vụ; chuyển dịch nội bộ; tổng yêu cầu đặt trên GSM.                                    |
| Nguồn cung khả dụng     | Thay đổi giờ tài xế có thể phục vụ; tách tăng cung thực khỏi xe chuyển vùng và thời gian sạc.                            |
| Trạng thái vận hành     | Chuyến hoàn thành, xe hoặc giờ xe nhàn rỗi, thời gian chờ và tỷ lệ hủy.                                                  |
| Hiệu quả và bằng chứng  | Doanh thu, chi phí, lợi nhuận đóng góp tăng thêm và ROI khi đủ dữ liệu; khoảng bất định và kết quả đối chiếu thử nghiệm. |

## Thiết kế hệ thống và dữ liệu

Hệ thống gồm ba lớp (Hình 1). Bên trái là dữ liệu và vận hành hiện có của GSM, ở giữa là lõi mô hình xây mới, bên phải là người dùng và đầu ra. Lõi mô hình làm ba việc:

- biến dữ liệu vận hành thành ba độ co giãn;

- ghép ba độ co giãn trong simulator để dự báo điểm cân bằng mới;

- kiểm chứng dự báo bằng switchback trên vận hành thật.

![Kiến trúc hệ thống GSM Causal Marketplace](GSM_Causal_Marketplace_Proposal_assets/architecture.png)

*Hình 1. Kiến trúc từ dữ liệu GSM đến ba độ co giãn, simulator, so sánh kịch bản và vòng lặp kiểm chứng switchback.*

Người dùng chính là đội định giá và vận hành tài xế. Người vận hành chọn dịch vụ, khu vực, khung giờ và mức thay đổi giá hoặc thưởng. Hệ thống so sánh kịch bản với chính sách hiện tại và hiển thị bốn đại lượng (cầu, cung, chuyển dịch dịch vụ, nguồn cung nhàn rỗi), cùng tác động vận hành, kinh tế và mức bất định. Chỉ kịch bản được duyệt mới chuyển sang thử nghiệm, trong biên độ GSM cho phép.

Đầu ra được chia theo người nhận:

| **Người nhận**                  | **Đầu ra**                                          | **Dạng bàn giao** |
|---------------------------------|-----------------------------------------------------|-------------------|
| Đội định giá và vận hành        | So sánh kịch bản giá và thưởng                      | Demo tương tác    |
| Nhóm 4 – Mobility Assistant     | Bảng độ nhạy giá, ma trận thay thế 2×2              | CSV/JSON          |
| Nhóm 1                          | Đường phản ứng nguồn cung, kèm ràng buộc pin và sạc | CSV/JSON          |
| Lãnh đạo GSM và cơ quan quản lý | Báo cáo giải trình tác động lên khách và tài xế     | Báo cáo           |

**Luồng hệ thống và vòng lặp cập nhật sau thử nghiệm**

**Đầu vào.** Tầng dữ liệu lấy từ bốn nhóm nguồn. Mỗi nhóm phục vụ một hoặc nhiều độ co giãn:

| **Nhóm dữ liệu**      | **Nội dung**                                                                                                | **Dùng cho**                                                |
|-----------------------|-------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| Báo giá và đặt chuyến | Phiên báo giá, kể cả phiên không đặt; giá, ETA và tập dịch vụ khách thực sự nhìn thấy; đặt, hủy, hoàn thành | Độ nhạy giá của khách; thay thế chéo                        |
| Lịch sử chính sách    | Bảng giá, thưởng, gói thuê bao và người đăng ký; cơ chế chi trả tài xế; quy tắc và lý do phân bổ            | Nguồn biến thiên để nhận diện nhân quả cho cả ba độ co giãn |
| Tài xế và xe          | Ca, vị trí, trạng thái xe, pin và thời gian sạc                                                             | Phản ứng nguồn cung; simulator                              |
| Bối cảnh              | Thời tiết, sự kiện, thời gian                                                                               | Biến điều chỉnh gây nhiễu cho cả ba                         |

**Lõi mô hình.** Dữ liệu đi qua năm khối nối tiếp:

| **Khối**                | **Việc thực hiện**                                                                                              | **Đầu ra**                                                       |
|-------------------------|-----------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| Tầng dữ liệu nhân quả   | Liên kết phiên báo giá với đặt, hủy, hoàn thành; tạo bảng cụm khu vực × khung giờ × dịch vụ và bảng tài xế × ca | Bảng dữ liệu đã kiểm tra chất lượng                              |
| Ba độ co giãn           | Ước lượng cầu theo giá, thay thế chéo và cung theo thu nhập kỳ vọng                                             | Hệ số kèm khoảng tin cậy và mức bằng chứng A/B/C                 |
| Simulator thị trường    | Mô phỏng ghép khách–xe, đón, phục vụ, hủy và sạc ở mức giá mới                                                  | Điểm cân bằng mới và khoảng chênh cung–cầu (nguồn cung nhàn rỗi) |
| So sánh kịch bản        | Đặt kịch bản cạnh chính sách hiện tại                                                                           | Lợi nhuận tăng thêm, khoảng tin cậy, cờ ngoại suy                |
| Switchback và đối chiếu | Chốt dự báo trước lượt, đo tác động sau lượt                                                                    | Sai số dự báo theo từng độ co giãn                               |

**Vòng lặp cập nhật.** Khối switchback nối lõi mô hình với vận hành thật qua bốn bước:

1.  Hệ thống gửi lịch thử nghiệm theo cụm khu vực × khung giờ.

2.  GSM áp chính sách theo lịch và trả kết quả về.

3.  Tác động đo được so với dự báo đã chốt.

4.  Ba độ co giãn được cập nhật. Mức bằng chứng nâng lên A ở những phần đã có thử nghiệm, và phiên bản mô hình mới dùng cho lượt dự báo sau.

Thiết kế thử nghiệm chi tiết trình bày ở phần switchback.

**Quy tắc dữ liệu.** Các biến dùng để điều chỉnh gây nhiễu phải có trước can thiệp. Dữ liệu phát sinh sau can thiệp được xếp là kết quả hoặc biến trung gian. Trước khi ước lượng, pipeline kiểm tra dữ liệu trùng, dữ liệu thiếu, múi giờ và khả năng liên kết bản ghi.

**Công nghệ.** Python và SQL cho xử lý dữ liệu, EconML hoặc DoWhy cho phân tích nhân quả, SimPy cho mô phỏng sự kiện rời rạc, Streamlit cho demo. Mỗi lần chạy lưu phiên bản dữ liệu, cấu hình và mô hình để tái lập được kết quả. Nguyên mẫu là công cụ hỗ trợ quyết định; việc áp dụng chính sách do GSM phê duyệt.

## Thuật toán ước lượng ba độ co giãn

Mỗi độ co giãn được xác định bởi ba yếu tố: đại lượng đo, nguồn biến thiên của chính sách, và giả định để diễn giải nhân quả. Kết quả được báo cáo theo cụm khu vực, khung giờ và dịch vụ ở mức dữ liệu cho phép. Các kết quả này là tham số đầu vào của simulator.

Giá đầu vào ưu tiên giá báo hoặc hệ số bảng giá, có điều chỉnh theo đặc điểm chuyến. Không dùng giá thực trả bình quân của các chuyến đã đặt, vì con số này bị lệch do lựa chọn của khách và cơ cấu cự ly. Gói thuê bao được quy đổi thành mức giảm giá hiệu dụng cho người đăng ký.

| **Độ co giãn**        | **Đại lượng đo**                                                                                      | **Nguồn biến thiên (ưu tiên → dự phòng)**                                                    | **Lưu ý khi diễn giải**                                                                            |
|-----------------------|-------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| Độ nhạy giá của khách | Phần trăm thay đổi yêu cầu đặt khi giá dịch vụ thay đổi 1%; báo cáo riêng tỷ lệ chuyển đổi từ báo giá | Biến thiên giá ngẫu nhiên → thay đổi bảng giá lịch sử (DiD) → DML                            | Chỉ dùng dữ liệu lịch sử khi đáp ứng giả định nhận diện                                            |
| Phản ứng nguồn cung   | Thay đổi giờ có thể phục vụ theo thu nhập kỳ vọng hoặc thưởng                                         | Thưởng phân bổ ngẫu nhiên → thay đổi chương trình thưởng theo ca (DiD)                       | Với chương trình thưởng mới (mức nền bằng 0), báo cáo tác động theo số tiền thay vì theo phần trăm |
| Thay thế chéo dịch vụ | Cầu từng dịch vụ phản ứng với giá của dịch vụ còn lại; ma trận độ co giãn 2×2                         | Biến thiên giá phân biệt được giữa hai dịch vụ; bổ sung nested logit khi có log tập lựa chọn | Nếu chỉ thay giá X, mới ước lượng được một cột của ma trận                                         |

**Phương pháp và mức bằng chứng.** Mỗi ước lượng được gắn mức bằng chứng theo phương pháp tạo ra nó:

| **Phương pháp**                                               | **Dùng khi**                                                      | **Giả định chính**                                                | **Mức bằng chứng** |
|---------------------------------------------------------------|-------------------------------------------------------------------|-------------------------------------------------------------------|--------------------|
| Thử nghiệm ngẫu nhiên (switchback, thưởng phân bổ ngẫu nhiên) | GSM chấp thuận biên độ thử nghiệm                                 | Phân bổ đúng thiết kế, được kiểm tra bằng A/A                     | A                  |
| Difference-in-Differences (DiD)                               | Có thay đổi chính sách giữa nhóm áp dụng và nhóm đối chứng        | Xu hướng song song; không có thay đổi đồng thời                   | B                  |
| Double Machine Learning (DML)                                 | Dữ liệu lịch sử có đủ biến bối cảnh quan sát được                 | Không còn gây nhiễu chưa quan sát; vùng dữ liệu so sánh được      | B                  |
| Mô phỏng với tham số đã biết                                  | Dữ liệu thật chưa sẵn sàng; cần kiểm tra khả năng thu hồi tham số | Chỉ chứng minh phương pháp chạy đúng, chưa phải ước lượng cho GSM | C                  |

**Giới hạn của DML.** DML điều chỉnh các yếu tố bối cảnh quan sát được bằng mô hình dự báo giá và cầu. Tuy vậy, DML không tự loại bỏ nội sinh khi giá và cầu cùng phản ứng với một cú sốc chưa được ghi nhận. Đây chính là vấn đề đã nêu ở phần Bài toán. Kết quả DML được đặt cạnh hồi quy tương quan để kiểm tra độ nhạy. Chênh lệch giữa hai kết quả gợi ý mức độ gây nhiễu, nhưng không tự cho biết phương pháp nào đúng.

**Điều kiện dùng DiD.** Thay bảng giá theo giai đoạn, khuyến mại theo lịch hoặc thưởng công bố trước ca mới chỉ là nguồn biến thiên ứng viên. Trước khi dùng, cần kiểm tra ba điều:

- khu vực và thời điểm áp dụng được chọn như thế nào;

- nhu cầu có bị dự đoán trước hay không;

- có thay đổi nào khác diễn ra cùng lúc hay không.

**Cơ chế chi trả và phản ứng cung.** Tăng giá khách trả chỉ kéo thêm cung khi làm thay đổi thu nhập kỳ vọng hoặc phần hành vi còn linh hoạt của tài xế. Với ca và lương cố định, thước đo là số ca nhận thêm, tỷ lệ nhận chuyến hoặc việc điều chỉnh thời điểm sạc. Theo dõi các vùng lân cận giúp phân biệt tăng tổng cung với xe chuyển vùng.

**Thay thế chéo và tổng chuyến.** Muốn có đủ hai chiều của ma trận, giá hai dịch vụ cần biến thiên độc lập với nhau. Tổng chuyến toàn nền tảng luôn được theo dõi để tách khách chuyển sang dịch vụ khác với khách rời GSM. Log tập lựa chọn cho phép phân tích sâu hơn các luồng chuyển dịch.

## Mô phỏng thị trường và kiểm chứng bằng switchback

Phần này mô tả hai việc: ghép ba độ co giãn thành dự báo cho một kịch bản (simulator), và kiểm chứng dự báo đó trên vận hành thật (switchback).

**Simulator thị trường**

**Cơ chế.** Simulator nhận dòng yêu cầu đặt theo dịch vụ, số tài xế và xe có thể phục vụ, cùng quy tắc ghép khách - xe của GSM. Mô phỏng bao gồm thời gian đón, thời gian phục vụ, hủy do chờ, xe quay lại trạng thái sẵn sàng, và sạc. Đầu ra là trạng thái vận hành dự báo trong một khoảng thời gian xác định. Khi mô phỏng nhiều khung giờ liên tiếp, trạng thái được chuyển tiếp theo bước thời gian.

**Tìm điểm cân bằng mới.** Thu nhập mỗi giờ của tài xế phụ thuộc vào mức chi trả mỗi chuyến và số chuyến nhận được. Số chuyến lại phụ thuộc vào số xe cùng hoạt động. Vì vậy simulator chạy lặp theo ba bước:

1.  Từ thu nhập kỳ vọng, độ co giãn cung cho ra số giờ phục vụ.

2.  Simulator tính mức sử dụng xe và thu nhập thực tế.

3.  Thu nhập kỳ vọng được cập nhật cho vòng lặp tiếp theo.

Vòng lặp dừng khi thu nhập kỳ vọng và thu nhập thực tế khớp nhau. Điểm khớp đó là điểm cân bằng mới trên đồ thị cung–cầu. Khả năng phản ứng theo ca và các giả định chưa mô hình hóa được ghi rõ trong báo cáo.

**Hiệu chỉnh.** Trước khi so sánh chính sách, simulator được hiệu chỉnh và đánh giá trên một giai đoạn nền tách riêng. Các chỉ số đối chiếu với số liệu thực là chuyến hoàn thành, thời gian chờ, tỷ lệ hủy và mức nhàn rỗi.

**Đầu ra của một kịch bản.** Mỗi kịch bản trả kết quả cho cả hai dịch vụ, gồm thay đổi cầu, cung, chuyển dịch và các chỉ số sau:

| **Chỉ số**                   | **Cách tính**                                                                      | **Lưu ý**                                                                                                                                                                                       |
|------------------------------|------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Nguồn cung nhàn rỗi          | Số xe hoặc giờ xe sẵn sàng nhưng chưa phục vụ                                      | Xe đang sạc và xe không đủ điều kiện vận hành được báo cáo riêng. Khoảng chênh cung–cầu tính bằng chuyến/giờ (như trên đồ thị) được quy đổi thành số xe nhàn rỗi qua mô hình thời gian phục vụ. |
| Chuyến hoàn thành            | Do simulator tạo ra từ yêu cầu đặt và nguồn cung                                   | Độ co giãn chỉ áp lên yêu cầu đặt, không áp trực tiếp lên chuyến hoàn thành, để tránh tính một tác động hai lần.                                                                                |
| Thời gian chờ, tỷ lệ hủy     | Lấy từ mô phỏng ghép khách–xe                                                      | Đã đối chiếu với giai đoạn nền khi hiệu chỉnh.                                                                                                                                                  |
| Lợi nhuận đóng góp tăng thêm | Chênh lệch so với chính sách hiện tại, sau chi trả tài xế và các chi phí liên quan | Cách phân bổ chi phí theo ca được thống nhất với GSM.                                                                                                                                           |
| ROI của ưu đãi               | Lợi ích ròng tăng thêm ÷ chi phí ưu đãi tăng thêm                                  | Chỉ tính khi mẫu số dương. Nếu thiếu dữ liệu chi phí, báo cáo doanh thu và chỉ số vận hành, ghi rõ "ROI chưa xác định".                                                                         |

**Bất định và ngoại suy.** Dữ liệu được lấy mẫu lại theo cụm và khối thời gian. Với mỗi mẫu, tham số được ước lượng lại và mô phỏng được chạy lại để tạo khoảng bất định cho mọi đầu ra. Báo cáo tách riêng bất định thống kê với độ nhạy theo giả định vận hành. Kịch bản nằm ngoài vùng giá hoặc thưởng đã có dữ liệu được gắn cờ ngoại suy, và độ chính xác của nó chỉ được đánh giá qua thử nghiệm sau đó.

**Kiểm chứng bằng switchback**

Switchback luân phiên ngẫu nhiên chính sách theo cụm khu vực × khung giờ. Các lựa chọn thiết kế chính:

| **Yếu tố thiết kế**             | **Cách chọn**                                                                    | **Rủi ro được kiểm soát**                         |
|---------------------------------|----------------------------------------------------------------------------------|---------------------------------------------------|
| Cụm và độ dài khung             | Dựa trên thời gian chuyến, sự di chuyển của tài xế và thời gian tác động kéo dài | Tác động lan sang vùng lân cận                    |
| Khoảng chuyển tiếp              | Loại dữ liệu đầu mỗi khung khỏi phân tích                                        | Ảnh hưởng còn sót từ khung trước                  |
| Thiết kế giai thừa giá × thưởng | Kết hợp các mức giá và thưởng trong cùng một lịch                                | Không tách được tác động riêng của hai đòn bẩy    |
| Lịch giá riêng cho từng dịch vụ | Chốt riêng thời điểm thay giá X và Y                                             | Thiếu biến thiên để đo đủ hai chiều thay thế chéo |
| Cỡ mẫu                          | Theo mức tác động cần phát hiện và biến động thực tế                             | Thử nghiệm quá ngắn, không đủ để kết luận         |

Sau khi chạy, vẫn phải kiểm tra tác động lan giữa các vùng và tương quan theo thời gian.

**Quy trình một lượt thử nghiệm.**

1.  **Trước lượt:** dự báo, phiên bản mô hình, chỉ số, thời lượng và kế hoạch phân tích được chốt vào sổ đối chiếu. Chạy A/A để kiểm tra phân bổ và ghi log. Chạy mô phỏng nhiều lần để kiểm tra cách tính bất định.

2.  **Trong lượt:** các chỉ số an toàn như thời gian chờ và tỷ lệ hủy được theo dõi liên tục, theo ngưỡng đã thống nhất với GSM. Kết luận hiệu quả chỉ đưa ra theo lịch đã chốt.

3.  **Sau lượt:** tác động đo được được đối chiếu với dự báo đã chốt, sau đó mới cập nhật mô hình cho lượt sau, theo vòng lặp ở phần Thiết kế hệ thống.

## Lộ trình triển khai trong năm tuần

Lịch dự kiến từ 28/09 đến 01/11/2026, tập trung vào một nguyên mẫu chạy trọn luồng. Khảo sát dữ liệu và thiết kế thử nghiệm bắt đầu ngay từ tuần đầu. Mô hình nền, dữ liệu giả lập và demo được xây song song, để tiến độ kỹ thuật không phụ thuộc hoàn toàn vào thời điểm GSM cấp dữ liệu.

| **Tuần** | **Thời gian**           | **Công việc trọng tâm**                                                                                                                              | **Đầu ra rà soát**                                                                                                                        |
|----------|-------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| 1        | 2026-09-28 - 2026-10-04 | Chốt cụm, dịch vụ, cơ chế thưởng và gói thuê bao. Khảo sát log, cơ chế chi trả và nguồn biến thiên. Lập sơ đồ nhân quả và thiết kế thử nghiệm sơ bộ. | Báo cáo dữ liệu; thiết kế nhận diện cho ba độ co giãn; ngưỡng đánh giá dự kiến.                                                           |
| 2        | 2026-10-05 - 2026-10-11 | Dựng pipeline. Ước lượng độ nhạy giá và thay thế chéo bằng DML hoặc DiD phù hợp. Kiểm tra khả năng thu hồi tham số trên dữ liệu giả lập.             | Bảng độ nhạy giá và phần ma trận thay thế đủ điều kiện ước lượng, kèm khoảng bất định và mức bằng chứng.                                  |
| 3        | 2026-10-12 - 2026-10-18 | Ước lượng phản ứng nguồn cung, tách riêng xe chuyển vùng và thời gian sạc. Xây simulator và hiệu chỉnh trên giai đoạn nền. Ghép ba độ co giãn.       | Kịch bản tăng giá và tăng thưởng chạy trọn luồng, ra được điểm cân bằng mới và nguồn cung nhàn rỗi; báo cáo sai số tái hiện vận hành nền. |
| 4        | 2026-10-19 - 2026-10-25 | Đánh giá mô hình. Phân tích tác động kéo dài (carryover) và cỡ mẫu. Hoàn thiện lịch switchback, dashboard và đầu ra CSV/JSON.                        | Demo so sánh kịch bản; kế hoạch thử nghiệm; sổ đối chiếu dự báo; báo cáo kiểm tra phương pháp.                                            |
| 5        | 2026-10-26 - 2026-11-01 | Tích hợp, chạy lại và bàn giao. Chạy A/A hoặc pilot nếu đủ điều kiện. Đối chiếu kết quả sẵn có và đề xuất bước tiếp theo.                            | Nguyên mẫu, mã nguồn, hướng dẫn, báo cáo; trạng thái từng tiêu chí nghiệm thu; kế hoạch pilot mở rộng.                                    |

**Khi chưa có dữ liệu GSM.** Pipeline và mô hình chạy trên dữ liệu giả lập. Phần hiệu chỉnh theo vận hành thật và hiệu quả kinh doanh được ghi là "chưa đánh giá". Kiểm tra trên dữ liệu giả lập chỉ cho biết phương pháp có thu hồi đúng tham số và khoảng tin cậy có bao phủ đúng dưới các cơ chế sinh dữ liệu đã thiết kế hay không. Kết quả loại này ở mức bằng chứng C và không thay thế kiểm chứng trên GSM.

Việc GSM cho phép thử nghiệm mới chỉ là điều kiện triển khai. Kết quả chỉ đạt mức A khi thử nghiệm đã chạy và qua kiểm tra hợp lệ.

**Phối hợp với GSM.** GSM cần cử đầu mối về dữ liệu, định giá và vận hành tài xế để xác nhận nghiệp vụ. Pilot tuần 5 ưu tiên kiểm tra quy trình. Thời lượng cần thiết để kết luận về hiệu quả được xác định qua phân tích cỡ mẫu và có thể kéo dài sau năm tuần.

**Kết quả tuần năm và điều kiện triển khai**

**Gói bàn giao.** Phần lớn gói bàn giao hoàn thành được mà không cần dữ liệu thật. Chỉ nhóm cuối phụ thuộc vào dữ liệu GSM:

| **Nhóm**         | **Nội dung**                                                                                           | **Phụ thuộc dữ liệu GSM**              |
|------------------|--------------------------------------------------------------------------------------------------------|----------------------------------------|
| Hệ thống         | Pipeline dữ liệu, mô hình có phiên bản, simulator một cụm, dashboard so sánh kịch bản, đầu ra CSV/JSON | Không (chạy được trên dữ liệu giả lập) |
| Thiết kế         | Thiết kế nhận diện cho ba độ co giãn, kế hoạch switchback, sổ đối chiếu dự báo                         | Không                                  |
| Tài liệu         | Mã nguồn, cấu hình, hướng dẫn chạy lại, báo cáo giả định                                               | Không                                  |
| Kết quả trên GSM | Ước lượng nhân quả, simulator hiệu chỉnh theo vận hành thật, ROI, kết quả thử nghiệm                   | Có                                     |

Mỗi kết quả phụ thuộc dữ liệu ghi rõ phạm vi khu vực, dịch vụ, thời gian, mức bất định và vùng chính sách được dữ liệu hỗ trợ. Phần chưa đủ dữ liệu đi kèm thiết kế thu thập hoặc thử nghiệm cụ thể, thay vì đưa ra một hệ số chưa có căn cứ. Khi dữ liệu thật chưa sẵn sàng, demo dùng dữ liệu giả lập và hiển thị rõ mức bằng chứng.

**Tiêu chí nghiệm thu.**

| **Tiêu chí**              | **Yêu cầu**                                                                                                                   | **Cách kiểm tra**                                                              |
|---------------------------|-------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| Tái lập                   | Cùng dữ liệu và cấu hình cho cùng kết quả; mỗi chỉ số truy vết được về dữ liệu, mô hình và giả định                           | Chạy lại từ phiên bản đã lưu                                                   |
| Đầy đủ đầu ra             | Kịch bản tăng giá 10% trả đủ cầu, cung, chuyển dịch, nguồn cung nhàn rỗi, cùng tác động vận hành và kinh tế tính được         | Chạy kịch bản mẫu trên demo                                                    |
| Minh bạch                 | Khoảng bất định, cờ ngoại suy và mức bằng chứng hiển thị ngay cạnh kết quả                                                    | Rà soát dashboard và đầu ra CSV/JSON                                           |
| Chất lượng ước lượng      | Thu hồi đúng tham số; khoảng tin cậy đạt độ bao phủ danh nghĩa; kiểm tra placebo (gán can thiệp giả) không phát hiện tác động | Mô phỏng nhiều lần trên dữ liệu giả lập                                        |
| Chất lượng simulator      | Sai số tái hiện chuyến hoàn thành, thời gian chờ, tỷ lệ hủy và mức nhàn rỗi nằm trong ngưỡng                                  | Giai đoạn nền tách riêng                                                       |
| Độ chính xác phản thực tế | Dự báo khớp với tác động đo được                                                                                              | So với kết quả thử nghiệm, hoặc thay đổi lịch sử có thiết kế nhận diện phù hợp |

Ngưỡng sai số và thời gian chạy được chốt sau khảo sát tuần 1. Tiêu chí chưa đủ bằng chứng được ghi là "chưa thể đánh giá".

**Điều kiện từ phía GSM.** Để bắt đầu, GSM cần xác nhận khả năng cung cấp bốn nhóm dữ liệu đã nêu ở phần Thiết kế hệ thống. Ngoài ra cần dữ liệu tài chính đủ để xác định các khoản thu và chi thực sự thay đổi theo chính sách. Biên độ thử nghiệm, cách ghi nhận phân bổ và ngưỡng vận hành phải được thống nhất trước khi chạy thật.

**Quyết định cuối tuần 5.**

| **Quyết định**  | **Điều kiện**                                                                                                            |
|-----------------|--------------------------------------------------------------------------------------------------------------------------|
| Mở rộng pilot   | Nguyên mẫu chạy ổn định; dữ liệu phù hợp; thiết kế thử nghiệm khả thi; các kiểm tra quy trình (A/A, ghi log) đạt yêu cầu |
| Bổ sung dữ liệu | Chưa đủ cỡ mẫu hoặc thiếu nguồn biến thiên để nhận diện. Báo cáo chỉ rõ phần cần bổ sung và thời điểm đánh giá lại       |
| Tạm dừng        | Kiểm tra quy trình không đạt, hoặc GSM không cung cấp được dữ liệu và biên độ thử nghiệm cần thiết                       |

Mục tiêu của giai đoạn này là một công cụ dự báo và kiểm chứng có căn cứ, làm nền cho định giá và phân bổ thưởng theo thuật toán, và cho báo cáo giải trình với cơ quan quản lý.

### Cơ sở phương pháp

Chernozhukov và cộng sự (2018), Double/debiased machine learning for treatment and structural parameters. Tài liệu triển khai: https://www.pywhy.org/EconML/spec/estimation/dml.html

Callaway và Sant’Anna (2021), Difference-in-Differences with multiple time periods. Tài liệu: https://bcallaway11.github.io/did/

Bojinov, Simchi-Levi và Zhao, Design and Analysis of Switchback Experiments. Bản thảo: https://arxiv.org/abs/2009.00148
