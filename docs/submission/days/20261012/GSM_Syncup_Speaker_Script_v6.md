# Lời thoại sync-up GSM — Bài toán, kết quả và tiến độ PoC

Biên soạn: 13/10/2026. Số liệu chốt: 12/10/2026.

Bám theo `GSM_Syncup_Week1-3_20261013_v6.pptx`, gồm 9 slide chính. Dự kiến 12–16 phút, tùy thời lượng demo và trao đổi. Nội dung trong ngoặc vuông là chỉ dẫn trình bày, không đọc thành lời.

## Slide 1 — Tác động của chính sách giá trong thị trường gọi xe

Chào anh chị. Hôm nay em xin cập nhật phần Proof of Concept mà nhóm đã thực hiện đến thời điểm hiện tại.

Vì buổi này có anh chị mới tham gia, em sẽ bắt đầu lại từ câu hỏi nghiệp vụ, sau đó đi qua cách tiếp cận, phạm vi đã triển khai và các kết quả đã kiểm chứng. Em sẽ minh họa cách đánh giá một kịch bản tăng giá X thêm 10%, rồi chốt phần đã làm được và phần còn thiếu.

Câu hỏi xuyên suốt là: nếu giá của một dịch vụ tăng 10%, khách hàng sẽ phản ứng như thế nào, và phản ứng đó sẽ đi tiếp vào vận hành ra sao? Ví dụ, khách hàng có thể tiếp tục đặt, chuyển sang dịch vụ khác, hoặc không đặt nữa. Sau đó, số yêu cầu thay đổi sẽ ảnh hưởng đến ghép chuyến, thời gian chờ và tiền trả tài xế.

Trong bài này, X và Y là hai dịch vụ giả định. Các kết quả mô phỏng chưa được hiệu chỉnh bằng dữ liệu GSM, nên mục tiêu hôm nay là làm rõ cách hệ thống hoạt động và phần cần kiểm chứng tiếp theo.

[Chuyển slide]

Trước tiên, mình cần tách câu hỏi lớn này thành ba đáp ứng khác nhau.

## Slide 2 — Ba đáp ứng cần hiểu để đánh giá chính sách

Đáp ứng thứ nhất là độ nhạy giá của khách hàng: khi giá thay đổi, nhu cầu đặt chuyến thay đổi bao nhiêu?

Đáp ứng thứ hai là sự thay thế giữa các dịch vụ: nếu X đắt hơn, nhu cầu của Y có tăng không, và bao nhiêu khách chọn không đặt? Điểm này quan trọng vì nhìn riêng số đơn X sẽ chưa thấy được tác động lên toàn bộ hệ thống.

Đáp ứng thứ ba là cung lao động tài xế: điều kiện trả công thay đổi có làm tài xế tham gia nhiều hơn hoặc làm lâu hơn không?

Ba câu hỏi này có liên quan, nhưng cần dữ liệu và mô hình riêng. Trong PoC hiện tại, nhóm đã giữ danh sách tài xế online cố định. Nhóm có mô phỏng việc tài xế nhận hoặc từ chối từng đơn, nhưng chưa mô phỏng quyết định lên app, xuống app hay thay đổi giờ làm.

Vì vậy, phần nhận đơn mà anh chị thấy ở đây chưa phải là kết quả về độ co giãn cung lao động.

[Chuyển slide]

Để trả lời phần giá và nhu cầu, vấn đề đầu tiên là phân biệt tương quan với tác động nhân quả.

## Slide 3 — Giá và nhu cầu: tương quan chưa là nhân quả

[Chỉ vào yếu tố giờ cao điểm, mưa, sự kiện]

Ví dụ, vào giờ cao điểm hoặc khi trời mưa, nhu cầu có thể tăng và giá cũng tăng. Nếu chỉ nhìn dữ liệu thấy giá cao đi cùng nhiều chuyến, mình chưa thể kết luận tăng giá làm tăng nhu cầu.

Lý do là bối cảnh đang tác động đồng thời lên cả hai phía. Điều mình muốn biết là: trong các điều kiện có thể so sánh, nếu thay đổi giá thì nhu cầu sẽ khác bao nhiêu?

Đó là lý do nhóm xây dựng cách đối chiếu giữa các chính sách và kiểm tra khả năng tách ảnh hưởng của giá khỏi các yếu tố nền. Các phương pháp ước lượng sẽ được kiểm chứng trên dữ liệu có đáp án biết trước trước khi mình diễn giải chúng trên dữ liệu thực tế.

Khi làm với GSM, phần này còn phụ thuộc vào cách giá được thiết lập, thông tin bối cảnh mình quan sát được và có những thay đổi chính sách nào phù hợp để đối chiếu.

[Chuyển slide]

Điều này dẫn đến câu hỏi: hiện tại mình đang có dữ liệu gì và từng nguồn giúp trả lời được đến đâu?

## Slide 4 — Dữ liệu hiện có và phần cần GSM xác nhận

Ở đây mình cần phân biệt hai nguồn nhóm đã sử dụng và nguồn dữ liệu cần làm việc tiếp với GSM.

Nguồn thứ nhất là dữ liệu chuyến công khai NYC TLC, tháng 01/2024, tải từ trang công bố của cơ quan quản lý taxi và xe thuê tại New York. Nhóm kiểm tra chất lượng, chọn phạm vi khu vực và thời gian, rồi tạo các bảng thống kê và bối cảnh. Nguồn này giúp nhóm xây dựng nền xử lý dữ liệu và hiểu các chuyến đã hoàn tất. Tuy nhiên, nó thiếu các phiên khách xem giá nhưng không đặt, cũng như các yêu cầu không được phục vụ. Nếu chỉ dùng chuyến hoàn tất, mình sẽ chưa quan sát được đầy đủ nhu cầu.

Lớp thứ hai là dữ liệu synthetic, hay dữ liệu do nhóm chủ động sinh ra. Cụ thể, nhóm thiết lập các phiên báo giá, bối cảnh như khung giờ và khu vực, mức giá của X và Y, rồi đặt sẵn quy luật phản ứng với giá. Từ quy luật đó, nhóm sinh ba lựa chọn: đặt X, đặt Y hoặc không đặt.

Vì nhóm biết quy luật tạo dữ liệu, mình có một đáp án để kiểm tra mô hình có khôi phục đúng tác động hay không. Nhóm cũng có các trường hợp khó hơn, như yếu tố gây nhiễu hoặc hai mức giá biến động quá giống nhau, để kiểm tra giới hạn của phương pháp.

Phần controlled còn nằm ở mô phỏng vận hành: nhóm khai báo trước số tài xế, quy tắc nhận đơn, thời gian và cách trả công. Khi so sánh hai chính sách, nhóm ghép cặp các lần chạy để giữ điều kiện ngẫu nhiên tương ứng, giúp đọc chênh lệch rõ hơn.

Tuy nhiên, các quy luật này do nhóm thiết lập, chưa được suy ra từ hành vi GSM. Vì vậy, kết quả ở đây chứng minh hệ thống hoạt động trong điều kiện đã kiểm tra; chưa cho mình một con số tác động thực tế tại GSM.

Nguồn tiếp theo cần làm việc với anh chị là dữ liệu GSM, dùng để hiệu chỉnh và kiểm chứng trên nghiệp vụ thực tế. Project hiện chưa có dữ liệu GSM. Phần này cần anh chị xác nhận nguồn, định nghĩa trường và phạm vi dữ liệu. Đặc biệt, mình cần giữ được cả phiên không đặt, yêu cầu không được phục vụ và tài xế không có chuyến.

[Chuyển slide]

Với các nguồn đó, PoC hiện tại đã hoàn thành trong phạm vi sau.

## Slide 5 — Phạm vi PoC đã hoàn thành đến hiện tại

Có ba giả định chính cần đọc trước khi xem kết quả.

Thứ nhất, danh sách tài xế online được giữ cố định trong suốt khoảng mô phỏng. X và Y cùng sử dụng nhóm tài xế này.

Thứ hai, tài xế có thể nhận hoặc từ chối từng đề nghị. Từ chối một đơn không làm tài xế tự động offline; nhưng tài xế đang bận hoặc đã được giữ cho một chuyến sẽ không được nhận đồng thời một chuyến khác.

Thứ ba, tiền được ghi nhận khi chuyến hoàn tất. Trong thiết lập hiện tại, tài xế nhận 100% giá hiển thị và số tiền dùng đơn vị mô phỏng. Đây là giả định để kiểm tra luồng thanh toán, chưa phải chính sách trả công GSM.

Các phần như incentive, quyết định online hoặc offline, ca làm và cân bằng giữa thu nhập với giờ làm chưa nằm trong mô phỏng marketplace này.

Phạm vi đó giúp nhóm kiểm tra xuyên suốt từ lựa chọn khách hàng đến ghép chuyến và trả công, đồng thời làm rõ các phần còn cần phát triển hoặc hiệu chỉnh.

[Chuyển slide]

Em sẽ tóm tắt luồng PoC trước khi đi vào ví dụ và kết quả.

## Slide 6 — Luồng xử lý của PoC

Sơ đồ này cho thấy luồng tổng thể của PoC: kịch bản giá đi vào mô hình lựa chọn, lựa chọn đặt chuyển thành yêu cầu, rồi engine ghép chuyến và ghi kết quả vận hành.

Khi so giá gốc với X tăng 10%, mình giữ cùng mô hình, cùng tập phiên báo giá và cùng danh sách tài xế. Nhờ đó, việc đọc hai nhóm kết quả nhu cầu và vận hành sẽ có cùng điều kiện đối chiếu.

[Nếu demo trực tiếp: mở kịch bản giá gốc, sau đó X +10%. Chỉ lần lượt đầu ra nhu cầu và vận hành. Giới thiệu rõ số trên dashboard là một lần chạy, còn số trên hai slide sau là trung bình 100 quỹ đạo. Nếu không demo, chuyển thẳng sang kết quả.]

Sau đây là kết quả tổng hợp cho kịch bản đó.

## Slide 7 — Kịch bản X +10%: yêu cầu X giảm, Y tăng

Ở đây nhóm so sánh giá gốc với kịch bản tăng giá X thêm 10%, giữ giá Y như cũ. Kết quả là trung bình của 100 quỹ đạo ghép cặp, mỗi quỹ đạo kéo dài hai giờ và có hai tài xế online.

[Chỉ hai cột của X]

Yêu cầu X giảm từ khoảng 276,9 xuống 232,4.

[Chỉ hai cột của Y]

Yêu cầu Y tăng từ khoảng 208,5 lên 215,6. Tổng yêu cầu của hai dịch vụ giảm từ khoảng 485,5 xuống 447,9, tức giảm khoảng 37,6 yêu cầu trong hai giờ.

Trong thiết lập này, nhu cầu X giảm và nhu cầu Y tăng một phần. Nhưng việc Y tăng chưa đủ để kết luận từng khách rời X đều chuyển sang Y; để nói về dòng chuyển của từng khách, mình cần xem đầu ra lựa chọn chi tiết.

Điều cần giữ khi đọc biểu đồ là: đây là phản ứng được sinh từ quy luật mô phỏng, trên một tập phiên báo giá cố định. Mình chưa thể dùng các mức giảm này để dự báo tổng nhu cầu thực tế của GSM.

[Chuyển slide]

Và ngay cả khi số yêu cầu thay đổi như vậy, kết quả vận hành không nhất thiết thay đổi cùng chiều.

## Slide 8 — Nhu cầu và chuyến hoàn tất là hai đầu ra khác nhau

Trong cùng kịch bản, số chuyến hoàn tất trung bình tăng từ 3,88 lên 4,36, dù tổng yêu cầu giảm.

Lý do mình cần xem hai đầu ra riêng là chuyến hoàn tất còn phụ thuộc vào năng lực phục vụ và quá trình ghép chuyến. Với chỉ hai tài xế trong thiết lập này, năng lực phục vụ bị giới hạn rất mạnh; phần lớn yêu cầu hết hạn trước khi được đón.

Kết quả này cho thấy mình cần quan sát cả nhu cầu lẫn vận hành. Nó chưa chứng minh rằng giảm nhu cầu sẽ làm tăng chuyến hoàn tất trong thực tế, hay tăng giá X là một chính sách tốt hơn cho GSM.

Thời gian chờ trung bình ở nhóm đã được đón tăng từ khoảng 187,5 lên 198 giây. Đây là chỉ tiêu có điều kiện trên nhóm đã được đón, không phải thời gian chờ của tất cả khách gửi yêu cầu.

Tiền trả tài xế gross tăng từ 3,880 lên 4,589 đơn vị mô phỏng. Con số này chưa trừ chi phí và chưa phải đồng Việt Nam hay thu nhập ròng của tài xế.

Vì vậy, khi đánh giá một chính sách, mình cần nhìn đồng thời số yêu cầu, số chuyến hoàn tất, trải nghiệm khách hàng và thu nhập tài xế, trong một thiết lập đã được hiệu chỉnh phù hợp.

[Chuyển slide]

Trước khi kết thúc, em xin chốt lại phần nào đã làm được và phần nào còn thiếu.

## Slide 9 — Đã làm được gì và còn thiếu gì

[Chỉ lần lượt ba cột từ trái sang phải.]

Ở cột đầu tiên là những phần nhóm đã triển khai trong phạm vi PoC: nền xử lý dữ liệu NYC TLC, mô hình lựa chọn X/Y/không đặt, core engine ghép chuyến và trả công, cùng dashboard và khả năng xuất kết quả. Các phần này đã nối thành một luồng chạy được, như ví dụ vừa trình bày.

Cột giữa là những phần đã có nhưng mới giải quyết một phần bài toán. Nhóm đã so sánh kịch bản giá trên dữ liệu synthetic. Với tài xế, nhóm đã xử lý nhận hoặc từ chối từng đơn nhưng vẫn giữ danh sách online cố định. Khoảng bất định của mô phỏng hiện cũng chưa truyền đầy đủ sai số từ toàn bộ chuỗi dữ liệu, ước lượng và vận hành.

Cột cuối là những phần chưa hoàn thành: hiệu chỉnh và kiểm chứng bằng dữ liệu GSM; đưa quyết định online/offline và phản ứng giờ làm vào mô phỏng marketplace; cùng cân bằng cung–cầu và đánh giá lợi nhuận hoặc ROI thực tế.

Project có gói nghiên cứu cung lao động controlled riêng, nhưng gói đó chưa được nối vào marketplace đang trình bày. Vì vậy, mình cần phân biệt việc đã thử một phương pháp trên dữ liệu giả lập với việc đã hoàn thành hệ thống phản ánh hành vi tài xế thực tế.

Trạng thái hiện tại là nhóm đã có PoC để minh họa cách chính sách giá đi vào lựa chọn và vận hành. Để áp dụng cho GSM, bước tiếp theo cần thống nhất dịch vụ X/Y tương ứng, câu hỏi ưu tiên và các nguồn dữ liệu để hiệu chỉnh.

Em xin kết thúc phần trình bày ở đây và dành phần còn lại để nghe nhận xét, câu hỏi của anh chị.
