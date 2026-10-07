# Báo cáo PoC GSM Causal Marketplace

**Người thực hiện:** Nguyễn Thành An · 26ai.annt@vinuni.edu.vn

## 1. Problem

Bài toán của PoC là ước lượng sự thay đổi trong lựa chọn của khách hàng khi
giá dịch vụ thay đổi. Trong mô phỏng, **X và Y là hai dịch vụ giả định**;
**NONE** nghĩa là không đặt dịch vụ nào trong hai dịch vụ. Nếu giá X tăng,
một phần khách có thể chọn Y, còn một phần có thể không đặt xe. Phân biệt
hai phản ứng này là cơ sở để đánh giá một
phương án giá, bởi lượng đặt xe tăng ở Y chưa chắc bù được lượng giảm ở X.
Đây là phần mô hình cầu và lựa chọn trong đề xuất.

Khó khăn chính là giá và nhu cầu thường cùng chịu ảnh hưởng của giờ cao điểm,
khu vực hoặc các yếu tố khác. Khi số chuyến và giá cùng tăng, chưa thể kết
luận tăng giá làm tăng nhu cầu. Dữ liệu chuyến đã hoàn thành cũng không ghi
nhận đầy đủ những người xem giá rồi không đặt. Nếu bỏ qua các yếu tố này,
mô hình có thể ước lượng sai tác động của giá và đề xuất một phương án làm
giảm giá trị đặt xe.

Trong báo cáo này, em thực hiện tập trung vào kiểm tra mô hình trước khi áp dụng
cho GSM: mô hình có ước lượng đúng tác động giá khi biết đáp án, có chuyển
kết quả đó thành kịch bản lựa chọn và có chỉ ra những trường hợp chưa thể
kết luận hay không. Phạm vi này chưa bao gồm phản ứng của tài xế, ghép chuyến,
hủy chuyến, sạc xe và cân bằng cung–cầu. Dự báo doanh thu thực thu, biên đóng
góp và ROI còn cần dữ liệu kinh tế cùng các bước đánh giá trên GSM.

## 2. Approach

Hiện chưa có dữ liệu về các phiên xem báo giá của GSM. Vì vậy, PoC dùng dữ
liệu TLC để tạo bối cảnh theo vùng và thời gian, sau đó sinh giá và lựa chọn
với tác động đã biết trước. Cách làm này cho phép so sánh kết quả ước lượng
với đáp án, đồng thời chủ động tạo các trường hợp giá ngẫu nhiên, có nhiễu
hoặc không đủ thông tin để tách tác động.

Để kiểm tra thêm khả năng dự báo lựa chọn trên một nguồn độc lập, PoC sử dụng
Swissmetro. Mô hình có thời gian và chi phí được so sánh với mô hình chỉ có
hằng số, trên những người chưa xuất hiện trong tập huấn luyện. Thực nghiệm
này bổ sung kiểm tra dự báo bên cạnh kiểm tra tác động giá của bộ dữ liệu mô phỏng.

Cuối cùng, các mô hình được dùng để chọn giá trên tập validation và đánh giá
phương án đã chọn trên tập test. Bộ đánh giá dùng đáp án của mô phỏng, không
dùng dự báo của mô hình để tự chấm. Nhờ đó, có thể xem sai số ước lượng có
dẫn đến quyết định giá kém hơn phương án giữ nguyên giá hay không.

Các thực nghiệm trên chạy riêng, không ghép bản ghi hoặc chuyển hệ số giữa
TLC, Swissmetro và GSM. Đáp án cùng cơ chế gán giá không được đưa vào mô hình
học; biến ẩn chỉ dùng để sinh dữ liệu và đánh giá. Kết quả hành vi hiện thuộc
**mức bằng chứng C**: lựa chọn trên bối cảnh TLC là bán tổng hợp, thực nghiệm
chọn giá dùng dữ liệu tổng hợp, còn Swissmetro là khảo sát lựa chọn giả định.

Hệ thống đã triển khai luồng xử lý sau:

```text
TLC → dữ liệu gốc → kiểm tra chất lượng → bảng tổng hợp/bối cảnh huấn luyện
    → sinh lựa chọn X/Y/NONE → OLS/DML → bootstrap theo ngày
    → kịch bản giá → lưu kết quả → xuất CSV / JSON
```

Các kịch bản giữ cố định số phiên xem báo giá để đánh giá riêng sự thay đổi
trong lựa chọn của khách hàng. Việc áp dụng cho GSM còn cần dữ liệu thực tế
và kiểm chứng độ tin cậy của mô hình.

## 3. Method

### 3.1. Mô hình tác động giá

Mỗi đơn vị quan sát là một nhóm gồm **50 phiên xem báo giá**. Mô hình ước lượng
tỷ lệ chọn từng dịch vụ theo log tự nhiên của hệ số giá. Nhóm quan sát này
được gọi là **block** trong dữ liệu kết quả. Các ký hiệu trong mô hình được
hiểu như sau:

| Ký hiệu | Ý nghĩa |
|---|---|
| `W` | Bối cảnh có trước quyết định giá: vùng, giờ, thứ, cuối tuần, cao điểm và khoảng cách. |
| `T` | Cặp log tự nhiên của hai hệ số giá. Mỗi hệ số giá (`price_multiplier_X`, `price_multiplier_Y`) là tỷ số giữa giá áp dụng và giá cơ sở của dịch vụ tương ứng. |
| `p(W, T)` | Cặp xác suất chọn X và chọn Y trong bộ sinh dữ liệu, ký hiệu là `p_X` và `p_Y`. Xác suất không đặt là `p_NONE = 1 − p_X − p_Y`. |
| `b(W)` | Cặp xác suất cơ sở khi giữ nguyên cả hai giá; khi đó hệ số giá bằng 1 và `T` bằng 0. |
| `theta` | Ma trận tác động giá: hàng là dịch vụ được chọn, cột là dịch vụ thay đổi giá. |

Với các ký hiệu trên, cơ chế cơ sở của bộ sinh dữ liệu có dạng:

```text
p(W, T) = b(W) + theta × T
T = [log(price_multiplier_X), log(price_multiplier_Y)]
theta = [[-0.60, 0.15], [0.12, -0.50]]
```

Các phần tử đường chéo của theta thể hiện tác động giá riêng; hai phần tử
còn lại thể hiện tác động chéo. Chẳng hạn, hệ số −0,60 ở hàng X, cột X cho
biết xác suất chọn X giảm khi log giá X tăng. Hệ số 0,12 ở hàng Y, cột X
cho biết xác suất chọn Y tăng khi log giá X tăng. Theta có đơn vị
**thay đổi xác suất trên một đơn vị log giá** (probability/log-price).
Để tính độ co giãn tương ứng, cần chia hệ số cho xác suất lựa chọn ban đầu
đủ lớn.

Trong các bảng sau, **X/X, X/Y, Y/X và Y/Y** dùng cùng quy ước hàng/cột:
phần trước là dịch vụ được chọn, phần sau là dịch vụ thay đổi giá; dấu `/`
không phải phép chia. Ví dụ, Y/Y là tác động của giá Y lên xác suất chọn Y.
Ma trận trên là đáp án dùng để kiểm chứng, không phải đầu vào của mô hình
học. Mô hình học từ tỷ lệ lựa chọn quan sát được trong mỗi nhóm 50 phiên.
Trường hợp không có tác động giá dùng theta bằng 0; trường hợp nhiễu ẩn
bổ sung biến `U` ảnh hưởng đồng thời đến giá và lựa chọn, nên có thêm thành
phần ngoài công thức cơ sở trên. U chỉ dùng để sinh dữ liệu và đánh giá.

Ba phương pháp được so sánh gồm **OLS** (Ordinary Least Squares, hồi quy
bình phương tối thiểu) và **DML** (Double/Debiased Machine Learning, dùng
học máy để điều chỉnh bối cảnh trước khi ước lượng tác động):

| Phương pháp | Cách ước lượng | Vai trò trong so sánh |
|---|---|---|
| OLS không điều chỉnh (Naive OLS; mã `naive_ols`) | Hồi quy tỷ lệ lựa chọn theo log giá X và Y | Mô hình đối chiếu khi không điều chỉnh bối cảnh |
| OLS điều chỉnh (Adjusted OLS; mã `adjusted_ols`) | Bổ sung vùng, giờ, thứ, cuối tuần, cao điểm và khoảng cách | Phương pháp đơn giản, phù hợp cấu trúc cộng của bộ sinh hiện tại |
| DML (LinearDML; mã `dml`) | Dùng rừng ngẫu nhiên (random forest) dự báo tỷ lệ lựa chọn và log giá từ bối cảnh, sau đó hồi quy phần dư với cross-fitting | Kiểm tra khả năng điều chỉnh bối cảnh bằng học máy |

DML loại phần biến thiên được bối cảnh giải thích khỏi giá và lựa chọn
(orthogonalization), rồi ước lượng tác động trên phần dư. Cross-fitting
chia dữ liệu thành các nhóm: các mô hình dự báo tỷ lệ lựa chọn và log giá
từ bối cảnh được học trên những nhóm khác trước khi tính phần dư cho nhóm
đang xét. Cách này hạn chế việc dùng cùng một quan sát để vừa học mô hình
phụ vừa tính phần dư. Phương pháp dựa trên
[Chernozhukov và cộng sự](https://arxiv.org/abs/1608.00060), triển khai bằng
[EconML LinearDML](https://www.pywhy.org/EconML/_autosummary/econml.dml.LinearDML.html).
Để diễn giải hệ số như tác động nhân quả, dữ liệu vẫn cần chứa đủ các yếu tố
gây nhiễu và có biến thiên giá phù hợp. Biến ẩn, đáp án và thông tin từ cơ chế
gán giá không được dùng làm đặc trưng học. DML cũng không giải quyết được
nhiễu do những yếu tố chưa quan sát.

### 3.2. Thiết kế thực nghiệm và khoảng tin cậy

**DGP** là viết tắt của *Data Generating Process*, tức cơ chế sinh dữ liệu.
Mỗi mã dưới đây là tên của một tình huống mô phỏng dùng để kiểm chứng mô
hình. **Yếu tố gây nhiễu** là yếu tố ảnh hưởng đồng thời đến giá và lựa
chọn, có thể làm sai lệch tác động giá nếu không được điều chỉnh.

| Trường hợp mô phỏng | Mã trong dữ liệu | Cơ chế và mục đích kiểm tra |
|---|---|---|
| Giá ngẫu nhiên | `RCT_SYN` | RCT là *Randomized Controlled Trial*; SYN chỉ dữ liệu tổng hợp. Giá được gán ngẫu nhiên, độc lập với bối cảnh gây nhiễu, để kiểm tra khả năng ước lượng lại tác động đã biết. Đây là mô phỏng điều kiện thí nghiệm ngẫu nhiên, chưa phải thí nghiệm trên GSM. |
| Nhiễu quan sát được | `OBSERVED_CONFOUNDING` | Các yếu tố có trong dữ liệu, như vùng và thời gian, cùng ảnh hưởng đến giá và lựa chọn. Kiểm tra việc điều chỉnh các yếu tố này có giúp giảm sai lệch so với OLS không điều chỉnh hay không. |
| Nhiễu ẩn | `HIDDEN_CONFOUNDING` | Biến U cùng ảnh hưởng đến giá và lựa chọn nhưng không được đưa vào mô hình học. Kiểm tra giới hạn của phương pháp khi thiếu yếu tố gây nhiễu. |
| Không có tác động giá | `NULL_EFFECT` | Tác động thật của cả hai giá bằng 0. Kiểm tra mô hình có kết luận sai rằng giá làm thay đổi lựa chọn hay không. |
| Giá đồng tuyến | `COLLINEAR_PRICE` | Hai giá biến động hoàn toàn cùng nhau, nên không thể tách tác động riêng của từng giá. Kiểm tra mô hình có từ chối ước lượng khi dữ liệu không đủ thông tin hay không. |

Với bối cảnh TLC, các ngày **01–20/01** dùng để huấn luyện, **21–25/01** để
chọn phương án (validation) và **26–31/01** để đánh giá cuối (test). Các mẫu
bối cảnh chỉ được xây từ tập huấn luyện. Cross-fitting chia thành năm nhóm
theo ngày gốc.
Bootstrap lấy lại mẫu theo ngày và huấn luyện lại toàn bộ mô hình; các bản
sao của cùng một ngày luôn thuộc cùng nhóm.

**Seed** là giá trị khởi tạo bộ sinh số ngẫu nhiên, giúp tạo và tái lập một
phép lặp mô phỏng. Lượt đánh giá đầy đủ giữ cấu hình **100 seed cho mỗi
trường hợp × 5 trường hợp**, dùng các seed **20001–20100**. Mỗi cặp trường
hợp–seed tạo một bộ dữ liệu để ba phương pháp cùng đánh giá, tương ứng một
job trong lượt chạy. Seed khác với lượt bootstrap: bootstrap lấy lại mẫu
từ bộ dữ liệu của một seed để tính khoảng tin cậy.

DML dùng **50 cây/5 nhóm cross-fitting (folds)**; mỗi phương pháp có hệ số
hợp lệ chạy **199 lần lấy mẫu bootstrap**. Seed 19001 dùng cho thử nghiệm thời gian chạy trước đó,
không nằm trong kết quả báo cáo. Giao thức được cố định và giữ nguyên sau khi
xem kết quả.

**Bias** đo sai lệch trung bình so với đáp án; **RMSE** (*Root Mean Squared
Error*, căn trung bình bình phương sai số) đo độ lớn sai số, với trọng số
lớn hơn cho sai số lớn. Hai chỉ số được tính riêng cho từng ô hệ số qua các
seed. RMSE xác suất
kịch bản được tổng hợp bằng căn trung bình bình phương của RMSE từng seed,
trên cùng tập bối cảnh test đã cố định.

Tỷ lệ bao phủ (coverage) là tỷ lệ khoảng tin cậy chứa hệ số thật. Trong
trường hợp không có tác động giá, một kết quả dương tính giả xảy ra khi
khoảng tin cậy không chứa 0 dù tác động thật bằng 0. Cả hai tỷ lệ được báo
cáo cùng khoảng tin cậy theo phân phối nhị thức (binomial) cho từng ô.
Bốn hệ số và ba phương pháp trên cùng một seed không
được xem như các quan sát độc lập.

Ngưỡng kỹ thuật được đặt trước cho trường hợp giá ngẫu nhiên là **RMSE hệ số
≤0,10 mỗi ô** và **RMSE xác suất kịch bản ≤0,02**. Nếu hơn 5% lượt bootstrap thất bại, kết quả
phải được đánh dấu. Độ chính xác của hệ số và độ tin cậy của khoảng ước lượng
được đánh giá riêng. Giao thức dùng khoảng 95% và báo cáo khoảng binomial,
nhưng chưa đặt một biên sai lệch chấp nhận được cho tỷ lệ bao phủ.

Kịch bản tăng 10% giá X dùng **log(1.1)** và giữ nguyên giá Y. Trước khi dự
báo, hệ thống kiểm tra dữ liệu có hỗ trợ cặp giá trong miền **0,90–1,10** và
các xác suất có hợp lệ tại từng bối cảnh hay không. Trường hợp thiếu hỗ trợ
hoặc không tách được tác động giá sẽ bị từ chối. Khoảng kịch bản không được
xuất nếu có lượt bootstrap cho xác suất không hợp lệ; khoảng chưa ổn định
được ghi trạng thái riêng.

### 3.3. Mô hình lựa chọn Swissmetro và đánh giá phương án giá

Swissmetro được chia **theo người**, với seed 31001, để một người không xuất
hiện ở nhiều tập. Mô hình logit đa thức (MNL) có hai hằng số cho Train/Car,
lấy Swissmetro làm mốc và dùng hệ số thời gian/chi phí chung. Mô hình đối
chiếu chỉ có các hằng số. Cả hai xét phương án nào khả dụng và chỉ huấn
luyện trên tập train. Thời gian được quy đổi bằng phút/100, chi phí bằng
CHF/100; người có thẻ GA được tính chi phí tăng thêm của Train/Swissmetro
bằng 0. Tập test không được dùng để chọn hoặc điều chỉnh mô hình.

Thực nghiệm chọn giá ở giai đoạn phát triển dùng **20 seed mỗi trường hợp**
cho giá ngẫu nhiên và nhiễu quan sát được, seeds 32001–32020. Mỗi seed có
**7.440 blocks/372.000 phiên**, dùng 50 cây/5 nhóm cross-fitting và không
chạy bootstrap theo ngày. X/Y giả định
cùng thuộc một đơn vị, với giá cơ sở mỗi dịch vụ là 1 đơn vị chuẩn hóa.
Mô hình chọn một cặp giá cố định từ chín cặp tạo bởi các mức
**0,90/1,00/1,10**. Việc chọn dựa trên dự báo ở tập validation và được lưu
trước khi đánh giá trên test.

Hai phương án đối chiếu là giữ giá 1/1 (Unchanged) và giảm 10% giá X, giữ Y
(Simple rule). Một cặp giá chỉ được xét khi có ít nhất một block huấn luyện
cho cặp đó trong mỗi nhóm vùng–cuối tuần–cao điểm. Nếu thiếu hỗ trợ, phương
án quay về giữ nguyên giá. Đây là ngưỡng dùng cho thực nghiệm phát triển,
chưa chứng minh dữ liệu GSM đủ hỗ trợ những phương án tương tự.

Chỉ số đánh giá là tổng giá trị đặt xe mô phỏng trên 1.000 phiên xem báo giá.
**Uplift** là chênh lệch so với giữ nguyên giá; **regret** là phần giá trị
thấp hơn phương án tốt nhất theo đáp án mô phỏng, trong cùng tập giá được
hỗ trợ. Bộ đánh giá độc lập với mô hình chọn giá. Nếu đánh giá test bị lỗi,
kết quả được ghi không khả dụng, thay vì chọn lại giá dựa trên test.

## 4. Current data

| Dữ liệu | Quy mô và xử lý hiện tại | Vai trò trong PoC |
|---|---|---|
| TLC HVFHV 01/2024 | Tệp gốc 19.663.930 dòng, 24 trường, 472.757.547 bytes; bảng vùng 265 dòng | Cung cấp bối cảnh vận hành; thiếu phiên không đặt và cơ chế gán giá |
| TLC trong phạm vi | 970.940 chuyến hoàn tất; vùng đón 161/162/163/164/170, nền tảng HV0003/HV0005, giữ trả ngoài cụm | Dữ liệu sau kiểm tra và bảng tổng hợp cùng ghi nhận 970.940 chuyến; chưa đo chuyển đổi hoặc độ co giãn GSM |
| Mart và chất lượng | 14.880 ô vùng × 30 phút × platform; 970.675 dòng giá dương, 960.950 dòng request-to-pickup hợp lệ | Kiểm soát chất lượng theo chỉ số; không loại số chuyến khi một chỉ số lỗi |
| Bối cảnh / demo | 240 mẫu vùng/giờ/cuối tuần chỉ từ tập train, không cần mẫu thay thế; demo bảy ngày 3.360 ô/175.861 chuyến | Dùng cho huấn luyện và dashboard, không lấy thông tin từ test |
| Dữ liệu bán tổng hợp cho đánh giá đầy đủ | 7.440 blocks/372.000 phiên mỗi seed; train 4.800 blocks/20 ngày, test 1.440 blocks/72.000 phiên | Tác động và lựa chọn được sinh với đáp án đã biết để kiểm tra phương pháp |
| Swissmetro | 10.728 dòng/1.192 người gốc; bỏ 9 CHOICE=0, giữ 10.719 nhiệm vụ/1.191 người | Khảo sát lựa chọn giả định độc lập; giữ mọi mục đích chuyến đi SP=1 |
| Phân chia Swissmetro | Train 833 người/7.497 nhiệm vụ; validation và test mỗi tập 179 người/1.611 nhiệm vụ | Kiểm tra dự báo trên người chưa có trong tập huấn luyện |
| GSM | Chưa có dữ liệu gốc hoặc bộ chuyển đổi dữ liệu phiên xem báo giá | Chưa thể đánh giá phương án giá trên GSM hoặc dự báo kết quả kinh tế thực tế |

Nguồn TLC từ [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
Thời gian nguồn không kèm múi giờ nên được xử lý theo giả định
`America/New_York`. Dữ liệu gốc và checksum được giữ nguyên, không tự loại
bản ghi trùng. Giá trị 0 được phân biệt với dữ liệu thiếu; các phân vị không
đủ dữ liệu vẫn ghi là thiếu. Swissmetro giữ mười dòng có thuộc tính trùng
nhau vì chúng là các nhiệm vụ khảo sát riêng.
[EPFL/Biogeme, mục Data](https://biogeme.epfl.ch/) nêu phạm vi sử dụng cho
nghiên cứu và giáo dục; quyền tái phân phối hoặc sử dụng thương mại chưa
được xác nhận.

Để tiếp tục với GSM, cần **tám nhóm nguồn gốc trong 12 tháng gần nhất**, gồm
vùng lân cận/đối chứng: Booking & Demand; Pricing & Promotion; Driver Supply &
Status; Driver Earnings & Incentive; Matching & Operations; Customer
Choice/Cross-service; Policy & Context; Finance & Cost. Giữ cả không đặt/hủy/
timeout/không có xe và tài xế không có chuyến. Dữ liệu cần giữ cấu trúc log
gốc, được giả danh hóa nhất quán, kèm từ điển trường, khóa nối, đơn vị, múi
giờ và lịch sử thay đổi cấu trúc. Người thực hiện sẽ tự ánh xạ, nối và kiểm
tra theo [data contract](../../../GSM_DATA_CONTRACT.md).
Khóa session–quote–request–trip và driver/vehicle–dispatch–shift/charging cần
truy vết; giá/thưởng trước quyết định tách khỏi khoản thực nhận sau đó.

## 5. Experiment

### 5.1. Độ đầy đủ của đợt đánh giá

Kết quả gồm **6.000 dòng hệ số, tương ứng 60 ô thống kê**. Có 1.200 lượt
ước lượng cho hệ số hợp lệ và **238.800/238.800 lượt bootstrap thành công**.
Trong các lượt hợp lệ, không có lần nào cho xác suất ban đầu hoặc xác suất
kịch bản không hợp lệ. Còn 300 lượt thuộc trường hợp đồng tuyến bị từ chối;
1.200 dòng hệ số của nhóm này được giữ với giá trị N/A. Chúng được tính vào
tổng số lượt đã thực hiện, nhưng không vào mẫu số của RMSE hay tỷ lệ bao phủ.

Checksum của 500 checkpoint JSON/parquet và các dòng trong bảng tổng hợp đã
được đối chiếu. Các chỉ số của 60 ô cũng được tính lại và cho kết quả khớp.
Như vậy, mỗi DGP có đủ 100 phép lặp, bao gồm cả những trường hợp mô hình
không thể ước lượng. Đây là cơ sở để xem xét sai số và độ tin cậy ở các phần
tiếp theo. Mỗi lần ước lượng cho bốn hệ số, nên 199 lượt bootstrap được tính
một lần, không nhân thêm với số hệ số.

### 5.2. Khả năng ước lượng đúng tác động giá

Mỗi dòng trong bảng được tổng hợp từ 100 seed. Bảng lấy bias tuyệt đối lớn
nhất và RMSE lớn nhất qua bốn ô của ma trận; RMSE kịch bản đánh giá sai số xác suất
khi tăng 10% giá X và giữ giá Y.

| Trường hợp mô phỏng | Phương pháp | Bias tuyệt đối lớn nhất | RMSE hệ số lớn nhất | RMSE xác suất kịch bản |
|---|---|---:|---:|---:|
| Giá ngẫu nhiên | OLS không điều chỉnh | 0,001489 | 0,012475 | 0,003637 |
| Giá ngẫu nhiên | OLS điều chỉnh | 0,001300 | 0,012603 | 0,003591 |
| Giá ngẫu nhiên | DML | 0,001695 | 0,012680 | 0,003602 |
| Nhiễu quan sát được | OLS không điều chỉnh | 0,129793 | 0,130368 | 0,016680 |
| Nhiễu quan sát được | OLS điều chỉnh | 0,001727 | 0,012319 | 0,003758 |
| Nhiễu quan sát được | DML | 0,003463 | 0,012798 | 0,003777 |

Khi giá được gán ngẫu nhiên, cả ba phương pháp đều ước lượng khá sát tác
động đã biết. RMSE lớn nhất của các hệ số nằm trong khoảng 0,0125–0,0127,
thấp hơn ngưỡng 0,10. Sai số xác suất kịch bản khoảng 0,0036, tương đương
**0,36 điểm phần trăm**, dưới ngưỡng 2 điểm phần trăm đã đặt ra.

Khi giá phụ thuộc vào bối cảnh gây nhiễu, sai số lớn nhất của OLS không điều chỉnh lên
đến 0,130368. OLS điều chỉnh và DML đưa mức này xuống 0,012319 và 0,012798.
Kết quả cho thấy việc đưa bối cảnh trước chính sách vào mô hình giúp ước
lượng đúng tác động giá trong điều kiện đã thử. OLS điều chỉnh còn có RMSE
hơi thấp hơn DML ở trường hợp này, nên chưa có cơ sở ưu tiên DML chỉ vì đây
là phương pháp phức tạp hơn.

Bản đã nộp ghi nhận lượt kiểm tra ban đầu `20261003T135730-1ae94396`, gồm
**20 seed mỗi trường hợp, 100 jobs, 0 lỗi**, chạy trong 66,59 giây. Cấu hình dùng 1.860
blocks/93.000 phiên, 20 cây và 0 lượt bootstrap. RMSE lớn nhất của
OLS không điều chỉnh/OLS điều chỉnh/DML lần lượt là: giá ngẫu nhiên
**0,028020/0,025927/0,025527**, nhiễu quan sát được
**0,101744/0,030885/0,032944**, nhiễu ẩn **0,108117/0,036286/0,040800**,
không có tác động giá **0,027939/0,025774/0,025640**; 60 lượt ước lượng
trong trường hợp giá đồng tuyến bị từ chối.
Lượt đánh giá đầy đủ khác lượt ban đầu cả về dữ liệu, số cây và bootstrap.
Vì vậy, chênh lệch RMSE giữa hai lượt không thể quy riêng cho việc tăng số
seed. Bảng lịch sử được giữ tại
[hồ sơ 04/10](../20261004/POC_Technical_Report.md).

### 5.3. Độ tin cậy của khoảng ước lượng

| Phương pháp khi giá ngẫu nhiên | Tỷ lệ bao phủ qua bốn ô | Số lần bao phủ ở Y/Y | Khoảng binomial 95% của Y/Y |
|---|---:|---:|---|
| OLS không điều chỉnh | 90–96% | 90/100 | [82,38%; 95,10%] |
| OLS điều chỉnh | 86–95% | **86/100** | **[77,63%; 92,13%]** |
| DML | 86–94% | **86/100** | **[77,63%; 92,13%]** |

Sai số của hệ số nhỏ chưa bảo đảm khoảng tin cậy đạt mức danh nghĩa. Với
hệ số Y/Y khi giá ngẫu nhiên, khoảng 95% của OLS điều chỉnh và DML chỉ chứa tác động
thật ở 86 trong 100 lần đánh giá, tức bỏ sót ở 14/100 seed. Khoảng binomial
95% cho tỷ lệ này là [77,63%; 92,13%], không chứa mức 95%. Vì vậy, phần ước
lượng điểm đã đạt ngưỡng kỹ thuật, nhưng **độ bao phủ của khoảng tin cậy vẫn
là hạn chế cần xử lý trước khi nghiệm thu thống kê đầy đủ**.

Trạng thái `interval_status=ok` chỉ xác nhận đủ lượt bootstrap và đạt các
kiểm tra kỹ thuật. Kiểm tra bổ sung bằng binomial một phía, hiệu chỉnh Holm
trên 36 ô thuộc ba trường hợp giá ngẫu nhiên, nhiễu quan sát được và không
có tác động giá, cho giá trị p hiệu chỉnh 0,014825 ở hai ô Y/Y. Đây là
phân tích sau khi có kết quả, không phải tiêu chí nghiệm thu định trước;
phép hiệu chỉnh cũng chưa xử lý việc xem tiến độ nhiều lần trước đó.

Thực nghiệm không có tác động giá kiểm tra mô hình có báo tác động khác 0 khi tác động
thật bằng 0 hay không:

| Phương pháp | Dương tính giả X/X | X/Y | Y/X | Y/Y |
|---|---:|---:|---:|---:|
| OLS điều chỉnh | 6/100 | 8/100 | 8/100 | 8/100 |
| DML | 7/100 | 7/100 | 5/100 | 8/100 |
| OLS không điều chỉnh | 8/100 | 7/100 | 7/100 | 5/100 |

Các phương pháp báo tác động khác 0 ở 5–8 trong 100 lần đánh giá, tùy hệ số.
Khoảng binomial 95% cho 5/100 là [1,64%; 11,28%], cho 8/100 là
[3,52%; 15,16%]. Các khoảng đều chứa mức 5%. Với số lần lặp hiện tại, chưa
có bằng chứng mạnh rằng tỷ lệ dương tính giả vượt mức danh nghĩa; đồng thời
cũng chưa đủ để khẳng định hai tỷ lệ tương đương. Tỷ lệ này tính riêng từng
ô, khác với tỷ lệ cả ma trận có ít nhất một kết luận sai. Chi tiết các chỉ
số và khoảng tin cậy của 60 ô nằm trong
[rà soát thống kê](statistical_review.md).

### 5.4. Nhiễu ẩn và giới hạn nhận dạng

| Phương pháp khi có nhiễu ẩn, 100 seed | Bias tuyệt đối lớn nhất | RMSE hệ số lớn nhất | Tỷ lệ bao phủ theo ô |
|---|---:|---:|---:|
| OLS không điều chỉnh | 0,130073 | 0,130618 | 0% |
| OLS điều chỉnh | 0,025143 | 0,027836 | 41–67% |
| DML | 0,025052 | 0,027878 | 43–67% |

Khi thiếu yếu tố gây nhiễu, OLS điều chỉnh và DML vẫn còn sai lệch dù đã đưa
bối cảnh quan sát được vào mô hình. Tỷ lệ bao phủ chỉ đạt 41–67% và 43–67%.
RMSE xác suất kịch bản của hai phương pháp là 0,013850/0,013877, nhưng sai
số dự báo này không đủ để bảo đảm hệ số có ý nghĩa nhân quả. Ngưỡng đã đặt
cho giá ngẫu nhiên không được dùng để kết luận trường hợp nhiễu ẩn đạt yêu cầu.

Với giá đồng tuyến, hai giá biến động hoàn toàn cùng nhau, nên dữ liệu
không cho phép tách tác động của từng giá. Cả ba phương pháp đều từ chối ở
100/100 seed: tổng 300 lượt trả trạng thái không nhận dạng được tác động
(`not_identified`) và không chạy bootstrap
(0 lượt). Hệ số, kịch bản và tỷ lệ bao phủ được ghi N/A, với mẫu số hợp lệ
bằng 0. Kết quả này cho thấy cơ chế kiểm tra nhận dạng đã hoạt động như
mong đợi, tránh xuất hệ số khi dữ liệu không đủ thông tin.

### 5.5. Kịch bản tăng giá X

Kịch bản dưới đây được giữ từ bản đã nộp, thuộc lượt chạy
`20261003T130951-df24a7e4`, trường hợp giá ngẫu nhiên, seed 42. Dữ liệu gồm 7.440 blocks/372.000
phiên; mỗi phương pháp hoàn tất 199/199 lượt bootstrap. Thời gian huấn
luyện và bootstrap là 516,21 giây. DML ước lượng ma trận
`[[-0.590036, 0.169760], [0.101347, -0.498596]]`, với RMSE xác suất kịch bản
so với đáp án bằng 0,003678. Khi tăng 10% giá X, giữ giá Y và xét 10.000
phiên giả định, kết quả như sau:

| Lựa chọn | Trước | Sau | Thay đổi, điểm phần trăm |
|---|---:|---:|---:|
| Chọn dịch vụ X | 31,2280% | 25,6044% | −5,6236 |
| Chọn dịch vụ Y | 25,9856% | 26,9516% | +0,9659 |
| Không đặt (NONE) | 42,7864% | 47,4441% | +4,6577 |

Tỷ lệ chọn Y tăng ít hơn mức giảm ở X, trong khi tỷ lệ không đặt tăng
4,6577 điểm phần trăm. Tổng số lượt đặt xe kỳ vọng vì vậy giảm
**465,77 trên 10.000 phiên**. Kết quả cho thấy chỉ theo dõi sự thay thế giữa
X và Y sẽ bỏ qua phần nhu cầu rời cả hai dịch vụ. Các con số thể hiện thay
đổi ròng của xác suất, chưa xác định được từng khách đã chuyển từ X sang Y.

Kiểm tra phạm vi giá và khoảng ước lượng ở lượt chạy này có trạng thái
`ok`; cả 199 lượt bootstrap cho xác suất hợp lệ. Khoảng tin cậy 95% riêng cho
thay đổi số lượt đặt là [−488,62; −439,38]. Tuy nhiên, một seed chưa đủ để
đánh giá độ bao phủ của khoảng tin cậy; ở lượt này, ba trong bốn khoảng hệ
số chứa tác động thật. Đây vẫn là lựa chọn mô phỏng với số phiên xem giá
cố định, chưa dự báo số chuyến hoàn thành hoặc doanh thu GSM. Kết quả giữ
nguyên từ lượt cũ, chưa chạy lại trên mã hiện tại.

### 5.6. Dự báo lựa chọn trên Swissmetro

Hai mô hình được đánh giá trên cùng cách chia dữ liệu. Tập test có 1.611
nhiệm vụ của 179 người; log loss tính bằng nats/nhiệm vụ, giá trị thấp hơn
thể hiện dự báo tốt hơn. Lượt chạy `week2-swissmetro-final-31001` cho kết quả:

| Mô hình | Log loss train | Log loss validation | Log loss test | Độ chính xác test |
|---|---:|---:|---:|---:|
| Chỉ có hằng số (Intercept-only) | 0,880078 | 0,903043 | 0,881660 | 57,4798% |
| MNL có thời gian và chi phí | 0,815995 | 0,807700 | 0,781474 | 66,9770% |

Khi thêm thời gian và chi phí, log loss test giảm 0,100186 nats/nhiệm vụ
và độ chính xác tăng 9,4972 điểm phần trăm. Cải thiện này xuất hiện trên
những người chưa có trong tập huấn luyện, cho thấy các thuộc tính phương
án bổ sung thông tin dự báo so với mô hình chỉ có hằng số và điều kiện
khả dụng. Cả hai phép tối ưu đều hội tụ; các ma trận thiết kế có hạng lần
lượt là 2 và 4. Tổng xác suất bằng 1 và không vi phạm điều kiện khả dụng.

Chưa tính khoảng tin cậy cho log loss và độ chính xác. Swissmetro cũng là
khảo sát lựa chọn giả định, nên kết quả này kiểm chứng khả năng dự báo,
chưa xác lập tác động nhân quả của giá hoặc khả năng áp dụng cho GSM.
Lượt kiểm tra lại `week2-swissmetro-closeout-31001` trên mã cuối kỳ giữ
nguyên cả sáu dòng chỉ số và các dự báo. Năm tệp kết quả được kiểm tra
checksum trước khi dùng lại; thông tin nguồn của hai lượt được lưu riêng.

### 5.7. Ảnh hưởng của sai số ước lượng đến quyết định giá

Thực nghiệm `week2-policy-final-32001-32020` gồm 40 job, với 20 seed cho mỗi
trường hợp giá ngẫu nhiên và nhiễu quan sát được. Mọi phương án được đánh
giá trên cùng dữ liệu của từng seed. Bảng trình bày giá trị đặt xe mô phỏng trung bình trên
1.000 phiên xem báo giá, tính theo giá chuẩn hóa. Uplift so với giữ nguyên
giá; regret so với phương án tốt nhất theo đáp án trong tập giá được hỗ trợ.

| Phương án giá | Giá ngẫu nhiên: giá trị | Giá ngẫu nhiên: uplift | Giá ngẫu nhiên: regret | Nhiễu quan sát được: giá trị | Nhiễu quan sát được: uplift | Nhiễu quan sát được: regret |
|---|---:|---:|---:|---:|---:|---:|
| Giữ nguyên giá | 551,352199 | 0,000000 | 23,569085 | 551,352199 | 0,000000 | 16,075210 |
| Giảm 10% giá X, giữ giá Y | 565,472776 | 14,120577 | 9,448509 | 560,531721 | 9,179522 | 6,895688 |
| OLS không điều chỉnh | 574,921284 | 23,569085 | 0,000000 | 521,061057 | −30,291142 | 46,366352 |
| OLS điều chỉnh | 574,921284 | 23,569085 | 0,000000 | 567,427409 | +16,075210 | 0,000000 |
| DML | 574,921284 | 23,569085 | 0,000000 | 567,427409 | +16,075210 | 0,000000 |
| Tốt nhất theo đáp án mô phỏng (Oracle) | 574,921284 | 23,569085 | 0,000000 | 567,427409 | +16,075210 | 0,000000 |

Trong trường hợp có nhiễu quan sát được, OLS không điều chỉnh chọn tăng cả hai giá lên
1,10 ở 19/20 seed và giữ nguyên giá ở một seed. Phương án này làm giá trị
đặt xe mô phỏng giảm trung bình 30,291142 so với giữ nguyên giá. OLS điều chỉnh
và DML chọn cùng phương án tốt nhất theo đáp án ở 20/20 seed, đạt mức
tăng 16,075210. Như vậy, sai lệch ước lượng có thể dẫn đến một quyết định
giá bất lợi, còn việc điều chỉnh bối cảnh giúp tránh lỗi này trong các
điều kiện đã thử.

Khi giá ngẫu nhiên, cả ba mô hình cùng chọn cặp giá 0,90/0,90 ở 20/20 seed.
DML và OLS điều chỉnh cho giá trị bằng nhau. Regret bằng 0 chỉ có nghĩa là đạt
phương án tốt nhất trong tập giá được hỗ trợ, chưa bảo đảm tối ưu ở mọi
mức giá hoặc bối cảnh.

Bảng sau so sánh DML với các phương án khác trên cùng seed và bối cảnh
test. Mỗi dòng có 20 cặp; khoảng 95% Student-t dành cho chênh lệch trung
bình qua seed, chưa hiệu chỉnh đa so sánh:

| Trường hợp mô phỏng | So với | Chênh lệch trung bình | Khoảng 95% |
|---|---|---:|---|
| Giá ngẫu nhiên | Giảm 10% giá X, giữ giá Y | 9,448509 | [9,437913; 9,459104] |
| Nhiễu quan sát được | Giảm 10% giá X, giữ giá Y | 6,895688 | [3,028157; 10,763219] |
| Nhiễu quan sát được | OLS không điều chỉnh | 46,366352 | [41,431590; 51,301115] |

Chênh lệch giữa DML và OLS điều chỉnh bằng 0 ở cả hai trường hợp; khi giá
ngẫu nhiên, chênh lệch giữa DML và OLS không điều chỉnh cũng bằng 0, với
khoảng [0; 0]. Tổng cộng 120 lượt ước lượng
hoàn tất và 240/240 giá trị test hợp lệ, không có lỗi huấn luyện hay đánh
giá. Quy tắc giảm 10% giá X quay về giữ nguyên giá ở 7/20 seed có nhiễu quan sát
được do thiếu hỗ trợ; các trường hợp này vẫn nằm trong mẫu số. Bộ đánh
giá chạy trong 191,50 giây, toàn bộ bước mất 195,03 giây. Hai lượt dùng
cùng giao thức cho giá trị và lựa chọn giá giống nhau; kết quả cuối được
dùng lại sau khi đối chiếu checksum.

Các khoảng chênh lệch phản ánh biến động qua seed ở giai đoạn phát triển,
không thay cho kiểm tra độ bao phủ của day-bootstrap. Thực nghiệm giữ
cố định số phiên xem giá và giả định mọi lượt đặt đều hoàn tất, được
thanh toán. Chưa xét giới hạn công suất, hủy chuyến, chi phí hay phản ứng
cung. Vì vậy, mức tăng trong bảng là giá trị đặt xe mô phỏng, chưa phải
doanh thu thực thu hoặc ROI của GSM.

### 5.8. Mức độ hoàn thành và công việc còn lại

PoC đã có một luồng xử lý từ dữ liệu đến mô hình và kịch
bản giá. Các thực nghiệm cho thấy điều chỉnh bối cảnh giúp ước lượng đúng
hơn và chọn giá tốt hơn OLS không điều chỉnh trong trường hợp có nhiễu quan sát được.
Kịch bản X/Y/NONE đã thể hiện được phần nhu cầu chuyển sang dịch vụ còn
lại và phần rời cả hai. Swissmetro bổ sung kiểm tra dự báo trên dữ liệu
lựa chọn độc lập. OLS điều chỉnh vẫn là phương pháp đối chiếu cần giữ cạnh DML.

Hai giới hạn còn rõ là nhiễu ẩn làm mất bảo đảm nhân quả và tỷ lệ bao phủ
của hệ số Y/Y khi giá ngẫu nhiên chỉ đạt 86/100. Trong trường hợp đồng tuyến, 300 lượt từ chối đã
cho thấy cơ chế kiểm tra nhận dạng hoạt động. Các kết quả của 500 checkpoint
đã được đối chiếu, nhưng bộ mô hình cầu/lựa chọn bàn giao cuối cùng và lần
chạy lại tương ứng vẫn cần hoàn thiện. Vì vậy, **Week 2 đạt một phần, chưa
nghiệm thu đầy đủ**. Hạn chế về khoảng tin cậy cần được ghi nhận và chốt
với người nghiệm thu; tập seed đánh giá cuối không được dùng để điều chỉnh
phương pháp nhằm nâng kết quả.

Theo kế hoạch Week 3–5, các bước sau gồm mô hình cung, mô phỏng vận hành,
dashboard kinh tế, thiết kế switchback và sổ đối chiếu dự báo–thực tế.
A/A hoặc pilot chỉ thực hiện khi có dữ liệu phù hợp và được GSM chấp thuận.
Hạn nộp thực tế, người kiểm tra, ngày nghiệm thu và các ngoại lệ được chấp
nhận hiện chưa được xác nhận.
