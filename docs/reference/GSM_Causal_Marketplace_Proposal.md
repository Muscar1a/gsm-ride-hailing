# GSM Causal Marketplace — Mô tả thống nhất

Problem 06 | Nguyễn Thành An

Cập nhật: **20/10/2026, Asia/Bangkok**.

Đây là nguồn mô tả chính về bài toán, contribution, phạm vi và yêu cầu kiểm chứng
của đề tài. **Contribution lõi là dự báo phản thực nhu cầu khi thay đổi giá các
dịch vụ**, với khả năng nhận dạng, miền hỗ trợ và bất định được công bố cho từng
phép so sánh. Mô phỏng vận hành, kế toán, dashboard và exports phục vụ đánh giá,
kiểm chứng và sử dụng kết quả dự báo.

Nhận dạng theo từng phép đổi giá đã có **bản triển khai controlled `contrast_ols`**,
chưa ghi nhận nghiệm thu bản mới hoặc xác nhận GSM. Nó không thay đổi phạm vi PoC đã được Bun
nghiệm thu ngày 12/10/2026 hoặc các kết quả lịch sử. Trạng thái triển khai và bằng
chứng có ngày chốt được quản lý tại [danh mục tài liệu](../README.md).

## 1. Bài toán và mục tiêu

Giá cước, ưu đãi tài xế và quyền lợi thuê bao tác động tới hai phía của thị trường:
nhu cầu khách hàng và cung lao động tài xế. Dashboard lịch sử cho biết điều đã xảy
ra; tương quan chưa đủ để tách tác động của chính sách khỏi thời tiết, giờ cao điểm,
thiếu xe và các cú sốc thị trường. Giá và số chuyến có thể cùng tăng dù tác động
riêng của tăng giá lên nhu cầu là âm.

Câu hỏi trung tâm là: **trong quần thể, bối cảnh và chân trời dự báo xác định, nếu
đổi giá X/Y từ mức cơ sở sang mức ứng viên, số yêu cầu của từng dịch vụ và tổng
số yêu cầu thay đổi bao nhiêu, với bất định nào?** Ví dụ tham chiếu là tăng giá X
10% trong một cụm địa lý và cửa sổ thời gian, chỉ dự báo khi phép đổi giá có đủ cơ
sở nhận dạng và nằm trong miền hỗ trợ.

| Đáp ứng nghiên cứu | Câu hỏi | Vai trò |
|---|---|---|
| Độ nhạy giá khách hàng | Yêu cầu X/Y thay đổi thế nào khi giá thay đổi? | Thành phần trực tiếp của lõi dự báo nhu cầu |
| Thay thế giữa dịch vụ | Giá một dịch vụ làm yêu cầu dịch vụ kia và không đặt thay đổi thế nào? | Thành phần tác động chéo và tổng của lõi dự báo |
| Cung lao động tài xế | Điều kiện trả công/ưu đãi được biết trước quyết định làm việc thay đổi tham gia, giờ làm và giờ phục vụ thế nào? | Nhánh nhân quả riêng, cần khi mở rộng dự báo vận hành có cung phản ứng |

Lộ trình quyết định là **nhận dạng → ước lượng → dự báo có hỗ trợ → đánh giá chính
sách → đối chiếu thử nghiệm**. Phạm vi nghiên cứu ban đầu gồm một cụm địa lý và hai
dịch vụ. Giá trị kỳ vọng là giúp lựa chọn chính sách đáng thử và giải thích tác
động tới khách hàng, tài xế và chất lượng dịch vụ cho GSM/cơ quan quản lý. Đây là
mục tiêu, chưa phải lợi ích kinh doanh đã đo được.

## 2. Đại lượng dự báo và giới hạn diễn giải

**Câu hỏi dự báo và baseline đã được Bun chốt ngày 20/10/2026.** Kịch bản cơ sở
giữ nguyên giá hiện tại, cùng quần thể phiên báo giá, khu vực và khung thời gian;
tác động là nhu cầu kỳ vọng khi đổi giá trừ nhu cầu kỳ vọng khi giữ nguyên giá.
Baseline nhu cầu được ước lượng đúng bối cảnh, không lấy trực tiếp số chuyến hoàn
thành lịch sử. Mô hình đối chứng là adjusted OLS hiện tại, dự báo tác động bằng 0
và DML; kịch bản cơ sở và mô hình đối chứng là hai khái niệm riêng.

Mỗi kết quả phải khai báo can thiệp/phép so sánh, outcome, đơn vị, quần thể,
zone/dịch vụ, bối cảnh, chân trời hành vi, biến thiên chính sách và giả định nhận
dạng. Báo tác động tuyệt đối; chỉ báo elasticity khi định nghĩa và các mẫu số
giá/outcome dương cho phép diễn giải hợp lệ.

| Đầu ra lõi | Diễn giải |
|---|---|
| Tác động trực tiếp | Thay đổi yêu cầu X khi đổi giá X, hoặc yêu cầu Y khi đổi giá Y |
| Tác động chéo | Thay đổi yêu cầu của một dịch vụ khi đổi giá dịch vụ còn lại |
| Tác động kết hợp | Thay đổi yêu cầu X/Y khi đồng thời đổi hai giá theo phép so sánh xác định |
| Tác động tổng | Thay đổi tổng yêu cầu X+Y trong cùng quần thể và cửa sổ quan sát |
| Thay đổi không đặt | Thay đổi xác suất không đặt trong cửa sổ lựa chọn được quan sát đầy đủ |

Phải phân biệt **phiên báo giá → yêu cầu đặt xe → kết quả điều phối → chuyến hoàn
thành**. Số chuyến hoàn thành không tự xác định nhu cầu khi thiếu xe. Với tập phiên
báo giá cố định, đầu ra là nhu cầu có điều kiện trên quần thể đó; dự báo tổng nhu
cầu thị trường cần thêm dữ liệu và cơ chế nhận dạng thay đổi số cơ hội phát sinh
nhu cầu. Chưa chọn thuật toán khôi phục nhu cầu tiềm ẩn từ số chuyến hoàn thành.

Biến động ròng X/Y không xác định từng khách đã chuyển dịch vụ. `NONE` chỉ là không
đặt trong cửa sổ quan sát đầy đủ, không tự có nghĩa rời GSM hoặc chọn đối thủ.
Ưu tiên giá báo trước lựa chọn hoặc hệ số giá đã điều chỉnh đặc điểm chuyến; giá
cước thực thu trung bình bị ảnh hưởng bởi chọn mẫu và cơ cấu quãng đường. Quyền
lợi thuê bao được phản ánh vào giá hiệu dụng của nhóm thuê bao được quan sát.

Nhận/từ chối một đơn khác với quyết định tham gia thị trường hoặc số giờ lao động.
Giá khách hàng chỉ có thể tác động tới cung qua cơ chế trả công/kỳ vọng thu nhập
được khai báo và đáp ứng tài xế có cơ sở nhận dạng riêng. Thu nhập thực nhận sau
ca là outcome/mediator, không được thay cho treatment biết trước quyết định.
Cần theo dõi vùng lân cận để phân biệt cung tăng thêm với tái phân bổ xe.

<a id="demand-forecasting-contribution"></a>

## 3. Contribution lõi và cơ chế dự báo

### 3.1. Phát biểu contribution

Phương pháp dự báo phản thực nhu cầu đa dịch vụ liên kết **phép thay đổi giá được
hỏi → thông tin nhận dạng có trong dữ liệu → phạm vi kết quả được phép xuất**.
Phương pháp kiểm tra riêng miền hỗ trợ giá/bối cảnh và khả năng nhận dạng của từng
phép so sánh, rồi xuất các tác động trực tiếp, chéo hoặc kết hợp mà dữ liệu cho
phép, cùng bất định và phần chưa xác định.

Trọng tâm cần phát triển là dự báo một số thay đổi giá kết hợp khi dữ liệu chưa
đủ để tách tất cả hệ số giá riêng. Ví dụ, nếu X/Y chỉ cùng tăng theo một tỷ lệ,
một phép tăng chung trong miền hỗ trợ có thể ước lượng được dưới giả định mô hình
phù hợp, trong khi phép chỉ tăng X chưa được nhận dạng. Không suy từ ví dụ này
rằng mọi dữ liệu có giá đồng biến đều đủ cho dự báo tăng chung.

Mô phỏng, paired seeds, checkpoint và kế toán hỗ trợ kiểm chứng tác động vận hành;
chúng không thay thế bằng chứng cho mô hình nhu cầu. DML, ma trận tác động 2×2,
bootstrap, support và switchback riêng lẻ không được coi là điểm mới của đề xuất.

### 3.2. Quy tắc dự báo phiên bản 1

1. Xác định giá cơ sở/ứng viên, quần thể, bối cảnh, chân trời dự báo và cơ sở nhận
   dạng. Biến kiểm soát phải có trước can thiệp. Không điều chỉnh tùy tiện biến
   cung/chờ phát sinh sau đổi giá khi mục tiêu là tổng tác động chính sách.
2. Kiểm tra riêng khả năng nhận dạng và miền hỗ trợ. Có support hoặc biến thiên
   giá chưa đủ cho kết luận nhân quả; phải nêu assignment hoặc giả định quan sát,
   gồm các nguy cơ gây nhiễu và phụ thuộc không được xử lý.
3. Đánh giá đúng phép đổi giá được hỏi. `contrast_ols` dùng SVD để kiểm tra vector
   thay đổi log-giá thuộc không gian biến thiên giá còn lại sau điều chỉnh bối cảnh,
   rồi fit hồi quy điều chỉnh trên các tọa độ được giữ. Ngưỡng số học, support và
   HC3/t đã đóng băng trong [protocol](../BENCHMARK.md#demand-contrast-assessment--frozen-protocol-20-october-2026).
   Đây là lựa chọn triển khai phiên bản 1, chưa phải xác nhận tính mới.
4. Kiểm tra cả giá cơ sở và giá ứng viên trong bối cảnh được chọn. Một hướng thay
   đổi có thể ước lượng không bảo đảm hai mức giá tuyệt đối được hỗ trợ. Nội suy
   cần giả định riêng và dữ liệu hai phía; không nới ngưỡng theo kết quả.
5. Xuất phép so sánh được xác định và các hệ số riêng có căn cứ. Thành phần chưa
   xác định để unavailable/null với lý do, không điền 0 hoặc phân bổ tùy ý. Không
   tự thay phép hỏi thiếu nhận dạng bằng một phép hỏi gần nhất.
6. Khi lấy mẫu lại, giữ dữ liệu huấn luyện gốc làm căn cứ support; ghi nhận refit
   mất thông tin nhận dạng, toàn bộ mẫu số và trạng thái thất bại. Không chỉ tính
   trên các lần thuận lợi; quy tắc giữ/không xuất CI phải được đặc tả trước.

### 3.3. Estimator hiện tại và phần mở rộng controlled

| Thành phần | OLS/DML hiện tại | `contrast_ols` phiên bản 1 |
|---|---|---|
| Lựa chọn dịch vụ | X/Y/NONE trên tập phiên báo giá cố định; mô hình cộng tính với hệ số giá chung | Giữ quần thể và chân trời dự báo tường minh cho từng phép hỏi |
| Tác động giá | OLS/DML; các cột trực tiếp/chéo khi nhận dạng được | Dự báo theo phép so sánh được nhận dạng, kể cả một số tác động kết hợp |
| Hai giá đồng biến | Khi cả hai giá thay đổi nhưng residual covariance thiếu hạng, trả `not_identified`, không giữ model bundle | Giữ biểu diễn trên không gian nhận dạng được; hệ số riêng chưa xác định vẫn để null |
| Miền hỗ trợ | Kiểm tra giá cơ sở/ứng viên, ô giá kết hợp và bối cảnh từ dữ liệu huấn luyện | Khi thiếu hạng, kiểm tra hai mức trên một đường giá affine quan sát được; vẫn chặn ngoại suy và bối cảnh mỏng |
| Bất định | Analytic và bootstrap theo ngày, có trạng thái lỗi và giới hạn calibration | HC3/t trên thiết kế giảm hạng; không xuất CI cho hệ số chưa xác định; bootstrap giữ đủ mẫu số lỗi |
| Nhu cầu thiếu quan sát | Chưa khôi phục tổng nhu cầu tiềm ẩn từ số chuyến hoàn thành | Chỉ mở rộng khi có dữ liệu và cơ sở nhận dạng phù hợp |

Trường hợp chỉ một giá biến thiên, giá kia cố định đã có thể cung cấp một cột
tác động theo điều kiện hiện hành. Đề xuất không coi đó là khả năng mới. Hai cột
riêng cần biến thiên giá còn lại đủ độc lập; nhận dạng một tác động kết hợp không
cho phép suy ngược hai cột chưa xác định.

## 4. Dữ liệu và cơ sở nhận dạng

Yêu cầu tám nhóm nguồn thô trong 12 tháng gần nhất, gồm vùng lân cận/đối chứng.
GSM xuất Parquet, UTF-8 CSV hoặc nguồn gốc với schema, độ phân giải, khóa và
metadata hiện có; nhóm nghiên cứu xây bảng phân tích. Trường, grain, khóa và đơn
vị theo [GSM data contract](../GSM_DATA_CONTRACT.md), không định nghĩa lại tại đây.

| Nhóm nguồn | Mục đích |
|---|---|
| Booking & Demand | Funnel, phiên/yêu cầu, chuyến hoàn thành |
| Pricing & Promotion | Giá/quyền lợi hiển thị trước lựa chọn |
| Driver Supply & Status | Giờ xe, ca làm, di chuyển, sạc |
| Driver Earnings & Incentive | Điều kiện được chào trước quyết định, tiền công, thu nhập thực nhận |
| Matching & Operations | Offer, pickup/service/cancel và calibration vận hành |
| Customer Choice / Cross-service | Tập lựa chọn, người không đặt, tác động trực tiếp/chéo |
| Policy & Context | Assignment, nhận dạng, support và bối cảnh |
| Finance & Cost | Doanh thu ghi nhận, chi phí trực tiếp/cố định/chung, phân bổ được duyệt và định nghĩa lợi nhuận/ROI |

| Phương pháp | Điều kiện và giả định | Bằng chứng |
|---|---|---|
| Randomized switchback/ưu đãi | Assignment được thực thi; log exposure/outcome hợp lệ; xử lý interference/carryover, A/A trước pilot | A cho thành phần thực sự được kiểm chứng |
| DiD | Có nhóm can thiệp/đối chứng, xu hướng song song và không bỏ sót thay đổi đồng thời | B |
| DML | Bối cảnh quan sát đủ, không còn gây nhiễu chưa quan sát và overlap phù hợp | B khi các giả định có căn cứ |
| Mô phỏng biết tham số | Khôi phục tác động dưới điều kiện kiểm soát; không chuyển kết luận sang GSM | C |

DML residualize bối cảnh quan sát, không loại bỏ nội sinh do cú sốc thiếu dữ liệu.
So sánh tương quan và hồi quy điều chỉnh cho biết độ nhạy, không tự chứng minh
ước lượng nào đúng. Trước DiD cần xem phân bổ chính sách, nhu cầu dự kiến và can
thiệp đồng thời. Cung lao động ưu tiên biến thiên ưu đãi ngẫu nhiên hoặc thay đổi
chính sách có nhận dạng; ưu đãi bắt đầu từ 0 báo tác động theo lượng khi elasticity
không hợp lệ. Kiểm tra duplicate, missingness, timezone và cardinality khi nối.

Dữ liệu công khai, synthetic và GSM phải được gắn nguồn riêng. TLC là chuyến hoàn
thành, không khôi phục người xem báo giá hoặc nhu cầu không được phục vụ. Giữ
train/development/assessment tách biệt theo thời gian/đơn vị phù hợp; preprocessing
chỉ fit trên train. Lưu phiên bản dữ liệu, mô hình, cấu hình, môi trường và seed.

## 5. Phạm vi hệ thống và PoC

**PoC được Bun chốt và nghiệm thu ngày 12/10/2026:** roster tài xế online cố định,
quyết định nhận/từ chối từng offer và trả 100% giá cước hiển thị cho chuyến hoàn
thành. V3 đã có số lần offer hữu hạn, timeout/withdrawal, terms đóng băng,
checkpoint, sổ thu nhập và exports chỉ đọc. Xác suất nhận là giả định synthetic
độc lập với giá. Không triển khai ưu đãi, chia ca theo chính sách, online/offline
nội sinh hoặc cân bằng thu nhập–cung trong phạm vi này. Xem
[phạm vi PoC](../WEEK3_POC_SCOPE.md),
[nghiệm thu](../submission/days/20261012/week3_poc_acceptance.md) và
[hướng dẫn chạy](../USAGE.md#week-3-fixed-online-poc).

Nhánh controlled cung lao động được giữ làm bằng chứng khoa học riêng; không dùng
hiệu ứng ưu đãi để thay đổi roster của PoC. Cung online cố định và nhận đơn không
xác định elasticity cung lao động; nghiệm thu PoC không đóng ba đáp ứng nhân quả
GSM hoặc nghiệm thu cơ chế dự báo đề xuất ở mục 3.

| Kết quả mở rộng | Phụ thuộc |
|---|---|
| Cung phục vụ | Điều kiện trả công biết trước quyết định, mô hình participation/hours và attendance |
| Nhận đơn | Exposure offer, điều kiện offer và đáp ứng nhận/từ chối riêng |
| Chuyến hoàn thành, chờ, hủy, idle hours | Dự báo request, cung, matching và calibration vận hành |
| Simulated gross booking value | Chuyến hoàn thành nhân giá hiệu dụng trong kịch bản |
| Lợi nhuận/ROI GSM có điều kiện | Doanh thu ghi nhận và đầy đủ chi phí/định nghĩa tài chính được GSM xác nhận |

Simulator chuyển request rates (requests/giờ) và cung (giờ xe có thể phục vụ)
thành kết quả vận hành; chỉ áp dụng đáp ứng giá vào requests một lần, không áp lại
vào số chuyến hoàn thành. Idle hours là phần của cung, không đồng nhất với chênh
lệch request–capacity. Matching, pickup/service, hủy, sạc và state qua cửa sổ cần
được hiệu chỉnh/kiểm chứng riêng; khi thiếu GSM chỉ đối chiếu synthetic truth.

Giả định phát triển trả công 100% giá hiển thị được đóng băng trước mô phỏng;
hủy/expiry trả 0, completion chỉ thanh toán một lần qua các cửa sổ tương thích.
Giữ cả tài xế không có chuyến và giờ hiện diện. Quy tắc kế toán này không tự nhận
dạng đáp ứng thu nhập/cung. Nếu nghiên cứu equilibrium, vòng kỳ vọng thu nhập →
giờ phục vụ → utilization/thu nhập → kỳ vọng mới phải có damping, ngân sách hữu
hạn và trạng thái không hội tụ; cung cố định chỉ cần một lượt.

Thiết kế thuật toán/gate vận hành theo [core engine design](CORE_ENGINE_DESIGN.md)
và [benchmark](../BENCHMARK.md). Bảng dữ liệu/artifact theo
[architecture](../ARCHITECTURE.md). Tài liệu này quản lý mô tả đề tài; các đặc tả
kỹ thuật đó không phải các phiên bản contribution cạnh tranh. Chưa thực hiện giá
cá nhân, dispatch sản xuất, mô hình cạnh tranh toàn thành phố hoặc tự động triển
khai chính sách.

## 6. Kiểm chứng lõi dự báo và điều kiện triển khai

| Câu hỏi kiểm chứng | Thiết kế/bằng chứng cần đạt |
|---|---|
| Cơ chế mới mang lại gì? | So sánh OLS/DML hiện tại và baseline đơn giản trên cùng dữ liệu, quần thể, phép đổi giá và điều kiện đánh giá |
| Phân biệt đủ/thiếu nhận dạng? | Hai giá độc lập, chỉ một giá biến thiên, hai giá đồng biến, không còn biến thiên sau điều chỉnh bối cảnh |
| Chặn dự báo thiếu căn cứ? | Giá cơ sở/ứng viên ngoài support, bối cảnh mỏng, xác suất không hợp lệ, refit mất nhận dạng; giữ lý do và mẫu số |
| Thành phần nào tạo cải thiện? | Bỏ từng thành phần; tách lợi ích do thuật toán, dữ liệu và thay đổi phạm vi đánh giá |
| Tác động và bất định có đúng? | Bias/RMSE X/Y/tổng, báo sai dấu, coverage/độ rộng CI, null/placebo và tỷ lệ thất bại |
| Hiệu lực ngoài development? | Đóng băng mô hình, giả định, phép so sánh và tiêu chí trước assessment độc lập; đối chiếu thử nghiệm hợp lệ khi có dữ liệu |

Không yêu cầu mô hình phức tạp phải thắng hoặc chính sách phải có uplift dương.
Kết quả chưa nhận dạng là đầu ra minh bạch, nhưng phép đo GSM tương ứng vẫn mở.
Dữ liệu kiểm soát chỉ xác nhận điều kiện đã thử; chưa chứng nhận mọi CI đạt 95%.
[Kết quả inference hiện có](../submission/days/20261011/week2_inference_closeout.md)
giữ nguyên giới hạn coverage, support và calibration.

Estimand/quần thể, cơ chế phiên bản 1, quy tắc nhận dạng/support, baseline, suy luận
và tiêu chí assessment được đóng băng trong protocol trước assessment độc lập.
Giả định nhận dạng GSM và dữ liệu thực vẫn cần kiểm chứng riêng. Chỉ thêm phi
tuyến/heterogeneity khi có nhu cầu và bằng chứng; không điều chỉnh ngưỡng theo
kết quả assessment để đạt gate.

Với dự báo tích hợp, giữ riêng bất định thống kê, nhiễu Monte Carlo và sensitivity
với giả định vận hành. CI Monte Carlo khi giữ demand fit/rules cố định không trở
thành CI nhân quả hoặc full-chain. Kiểm chứng mô phỏng còn cần baseline holdout
cho trip/wait/cancel/idle, bất biến state/accounting, carryover và giới hạn workload.
Hội tụ, replay và kế toán đúng không thay thế kiểm chứng hành vi.

## 7. Đánh giá chính sách và đối chiếu thử nghiệm

Pricing/operations chọn tập giá/ưu đãi hữu hạn có hỗ trợ theo dịch vụ, zone và
horizon. Trước selection/assessment phải thống nhất với GSM chỉ tiêu kinh doanh,
mức tác động đáng thử, biên độ chính sách và guardrail chờ/hủy/thu nhập/ngân sách.
Không mặc định tối đa gross booking value hoặc lợi nhuận. Mỗi ứng viên được so
với baseline cùng phạm vi; báo bất định, giới hạn và lý do: đáng thử, cần thêm dữ
liệu hoặc ngoài giới hạn. Selection dùng development, đánh giá cuối dùng dữ liệu
độc lập hoặc thử nghiệm hợp lệ; không dùng mô hình chọn chính sách làm bằng chứng
duy nhất cho giá trị của chính sách đó.

Lợi nhuận/ROI và contribution margin chỉ xuất khi định nghĩa, cost coverage và
phân bổ tương ứng được GSM xác nhận. Booking value, tiền công và proxy vận hành
phải gắn nhãn riêng. Khi thiếu tài chính, kết quả kinh tế phụ thuộc giữ unavailable.

Switchback luân phiên chính sách theo cụm địa lý/time block. Độ dài block và
washout dựa trên hành trình, dịch chuyển tài xế và carryover; cần xử lý spillover
và phụ thuộc không gian/thời gian. Lịch giá X/Y phải cung cấp biến thiên phù hợp
với phép hỏi; factorial giá–ưu đãi cần các tổ hợp hỗ trợ. Chân trời của switchback
giá ngắn có thể phù hợp với requests nhưng chưa đủ cho tham gia/giờ làm.

Gói thử nghiệm cần có:

1. Assignment/exposure, cluster/block/washout, power, analysis, chỉ tiêu chính,
   guardrail và stopping rules; cỡ mẫu gắn với mức tác động đáng phát hiện.
2. A/A kiểm tra log, dựng lại metric và inference khi không có tác động; chỉ báo
   kết quả thực thi khi có log hợp lệ.
3. Ledger dự báo đóng băng: data/model/policy version, point/CI/status, quần thể,
   horizon, support và giả định.
4. Monitor guardrail tách khỏi suy luận efficacy theo lịch phân tích đã định.
5. Đối chiếu tác động đo được với dự báo cùng quần thể/horizon, chẩn đoán sai lệch
   rồi ghi phiên bản mô hình tiếp theo.

Đóng băng thiết kế, kiểm tra A/A và inference bằng mô phỏng lặp trước thực thi.
Theo dõi thời gian thực không cho phép kiểm định efficacy lặp tùy ý. Thiếu log
thực tế hợp lệ chỉ bàn giao thiết kế và giữ tác động/đối chiếu `not_evaluated`.
GSM phê duyệt thực thi chính sách; phê duyệt thiết kế không tự tạo evidence A.

## 8. Bàn giao, lộ trình và tiêu chí hoàn tất

| Bàn giao | Nội dung |
|---|---|
| Lõi dự báo nhu cầu | Estimand, tác động trực tiếp/chéo/kết hợp/tổng có nhận dạng, baseline, CI/status, support, giả định và phần chưa xác định |
| Nhánh cung lao động | Participation/hours/serviceable hours, phân biệt thêm giờ với dịch chuyển, nhận đơn báo riêng |
| Đánh giá chính sách | So sánh hữu hạn, assessment độc lập, guardrail, bất định và quyết định có lý do |
| Gói thử nghiệm | Thiết kế switchback/A/A có thể thực thi, ledger đóng băng, monitor và đối chiếu có điều kiện |
| Hệ thống hỗ trợ | Core engine, simulator một cụm, kịch bản không phụ thuộc UI, dashboard và CSV/JSON dùng cùng kết quả versioned |
| Hồ sơ tái lập | Dữ liệu/model/config/môi trường/seed, diagnostics, giới hạn và kế hoạch bổ sung dữ liệu/thử nghiệm |

Pricing/operations nhận báo cáo so sánh và demo; Group 4 nhận price sensitivity và
ma trận 2×2 đầy đủ/một phần hoặc phép so sánh được nhận dạng; Group 1 nhận đáp ứng
participation/hours và acceptance riêng; lãnh đạo/cơ quan quản lý nhận diễn giải
tác động và giới hạn bằng chứng. Mỗi đầu ra giữ đơn vị, zone/service/horizon,
uncertainty, evidence và nguồn còn thiếu.

Lộ trình năm tuần ban đầu vẫn là khung tổ chức; cập nhật contribution không tự
mở lại các mốc nghiệm thu hoặc coi cơ chế mới đã hoàn tất. Công việc còn lại và
gate theo tuần quản lý tại [roadmap](../ROADMAP.md).

| Tuần | Mục tiêu |
|---|---|
| 1 | Câu hỏi/estimand, mapping/chất lượng, nhận dạng/split, tiêu chí nghiệp vụ và kế hoạch đánh giá |
| 2 | Gói demand/choice, tác động đầy đủ/một phần, baseline, support, bất định và assessment độc lập |
| 3 | Nhánh cung riêng, demand handoff và kiểm chứng vận hành trong phạm vi PoC được chốt |
| 4 | So sánh chính sách có bất định/guardrail, thiết kế thí nghiệm, A/A và ledger dự báo |
| 5 | Hồ sơ tái lập, gate/giới hạn, kế hoạch pilot và đối chiếu có điều kiện theo dữ liệu thực |

Hoàn tất kỹ thuật cần bằng chứng độc lập cho nhận dạng/sai số/coverage trong phạm
vi đã thử, gate vận hành khi xuất kết quả vận hành, và truy vết được phiên bản.
Runtime/memory/workload phải có ngân sách chốt trước assessment. Dashboard và
exports phải hiển thị cùng scope, đơn vị và trạng thái với kết quả chạy độc lập.

Thiếu GSM thì calibration, tác động thực, lợi nhuận/ROI và đối chiếu thực nghiệm
giữ `not_evaluated`; phát triển evidence C vẫn tiếp tục. Pilot đầu tiên ưu tiên
kiểm tra quy trình; đo tác động đủ power có thể vượt năm tuần. Chỉ mở rộng pilot
khi phạm vi nhân quả/support, lý do thử chính sách, gate kỹ thuật, dữ liệu/design
và A/A/logging đủ; thực thi vẫn cần GSM phê duyệt. Thiếu nhận dạng/power thì nêu
nguồn cần thu và mốc rà soát; process/logging hoặc giới hạn thử nghiệm không đạt
thì tạm dừng rollout.

## 9. Giới hạn kết luận sáng chế và tham chiếu

Điểm sơ bộ **5,2/10** trước đây áp dụng cho tổ hợp đánh giá chính sách/mô phỏng
được mô tả lúc đó. Bản tích hợp này không chấm lại lõi dự báo và không bảo đảm
nâng điểm. Cần chọn cơ chế cụ thể, kiểm chứng và tra cứu lại cả ngoài lĩnh vực
gọi xe trước khi phát biểu tính mới hoặc trình độ sáng tạo. Cải thiện dự báo
không tự chứng minh khả năng bảo hộ; chưa kết luận cơ chế đề xuất là mới, đã
được bảo hộ hoặc đang nộp đơn.

Các tham chiếu dưới đây là điểm bắt đầu, không phải tra cứu đầy đủ hoặc ý kiến
pháp lý. Phương pháp chuẩn là nền tảng đối chiếu, không phải contribution tự thân:

- Chernozhukov và cộng sự (2018), Double/debiased machine learning:
  [tài liệu phương pháp/triển khai](https://www.pywhy.org/EconML/spec/estimation/dml.html).
- Callaway và Sant’Anna (2021), Difference-in-Differences:
  [tài liệu phương pháp](https://bcallaway11.github.io/did/).
- Bojinov, Simchi-Levi và Zhao, Design and Analysis of Switchback Experiments:
  [bản thảo](https://arxiv.org/abs/2009.00148).
- Tham chiếu sáng chế đã dùng trong tra cứu ban đầu:
  [WO2025080207A1](https://patents.google.com/patent/WO2025080207A1/en) và
  [CA3268977A1](https://patents.google.com/patent/CA3268977A1/en).
