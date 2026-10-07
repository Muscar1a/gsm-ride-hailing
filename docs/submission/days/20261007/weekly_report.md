# Báo cáo PoC GSM Causal Marketplace — Week 2

## 1. Thông tin báo cáo

**Người thực hiện: Nguyễn Thành An · 26ai.annt@vinuni.edu.vn**

**Chốt tiến độ chạy:** 07/10/2026 **10:41:19, Asia/Bangkok (UTC+07)**. Week 2 đạt một phần, chưa nghiệm thu đầy đủ.

Bản này tổng hợp kết quả PoC đã nộp và phần bổ sung hiện tại. Kết quả đo ngày
03/10 giữ nguyên nguồn run; không được coi là đã chạy lại trên mã mới.
[Báo cáo tiến độ](progress_update.md) là tài liệu ngắn đi kèm.

## 2. Tóm tắt PoC đã thực hiện

PoC ước lượng tác động giá trực tiếp/chéo lên lựa chọn **X, Y hoặc không đặt
(NONE)** trong phiên xem báo giá. Đã có pipeline TLC, năm bộ sinh hành vi có
đáp án thật, naive/adjusted OLS và DML, bootstrap theo ngày, kịch bản giá,
xuất CSV/JSON và dashboard ba màn hình. Luồng xử lý là **TLC → Bronze →
Silver/cờ chất lượng → Mart/context train-only → lựa chọn mô phỏng →
OLS/DML → bootstrap/kịch bản → artifact/dashboard**; oracle chỉ vào bộ đánh giá.

Bổ sung so với bản đã nộp: củng cố kiểm tra dữ liệu/nhận dạng/tái lập, triển khai
baseline Swissmetro có holdout theo người, policy-value với evaluator test độc
lập và coverage đầy đủ theo batch/checkpoint. Swissmetro và policy benchmark
development hoàn tất; coverage còn đang chạy. Kết quả hành vi
thuộc **evidence C**: TLC là bối cảnh chuyến hoàn thành, lựa chọn và tác động giá
là mô phỏng; Swissmetro là khảo sát lựa chọn giả định. Chưa có dữ liệu hành vi
GSM hoặc kết luận về elasticity, tác động nhân quả, doanh thu/biên đóng góp/ROI GSM.

## 3. Phạm vi hoàn thành và tiến độ so với proposal

| Phần việc | Đã có trong hồ sơ 04/10 | Bổ sung đến kỳ này / phần còn thiếu |
|---|---|---|
| Dữ liệu và cầu/thay thế chéo | TLC đối soát; OLS/DML, bootstrap, benchmark 20 seed/DGP | Củng cố kiểm chứng; coverage 100 seed/DGP đang chạy. Vẫn dùng ma trận chung và quần thể quote cố định |
| Baseline lựa chọn độc lập | Swissmetro chưa triển khai | Đã chạy MNL so với intercept-only; bổ sung căn cứ EPFL cho sử dụng nghiên cứu/giáo dục, giới hạn phạm vi sử dụng ở mục 5.3 |
| Kịch bản và demo | Kiểm tra hỗ trợ/xác suất; CSV/JSON; dashboard dữ liệu, phương pháp, giá | Củng cố trạng thái lỗi, kiểm tra artifact và phạm vi kịch bản; chưa có dự báo vận hành/kinh tế GSM |
| Phản ứng cung; simulator một cụm | Chưa triển khai | Chưa có cung, matching/sạc, cân bằng hoặc nguồn cung nhàn rỗi |
| Policy-value và thử nghiệm GSM | Chưa có benchmark policy độc lập, switchback chi tiết, sổ đối chiếu/A/A/pilot | Đã chạy policy benchmark development 20 seeds/DGP cho RCT/observed bằng oracle test độc lập; switchback, sổ đối chiếu và A/A/pilot chưa thực hiện |

## 4. Dữ liệu, phương pháp và khả năng tái lập

### TLC và kiểm soát chất lượng

Nguồn HVFHV tháng 01/2024; năm vùng đón **161, 162, 163, 164, 170**, hai platform
**HV0003/HV0005**; giữ điểm trả ngoài cụm. Timestamp không có timezone được
xử lý theo giả định `America/New_York`.

| Dữ liệu đã kiểm chứng | Quy mô |
|---|---:|
| Tệp chuyến nguồn / bảng vùng | 19.663.930 dòng, 24 trường, 472.757.547 bytes / 265 dòng |
| Silver hợp lệ về khóa / tổng chuyến mart đối soát | 970.940 / 970.940 chuyến |
| Mart toàn tháng / demo bảy ngày | 14.880 ô / 3.360 ô, 175.861 chuyến |
| Giá dương hợp lệ / request-to-pickup hợp lệ | 970.675 / 960.950 dòng |
| Context train-only | 240 mẫu vùng/giờ/cuối tuần, không cần fallback |

Giữ nguồn bất biến và SHA-256; không deduplicate. Cờ chất lượng độc lập,
số 0 và thiếu dữ liệu được phân biệt; lỗi một chỉ số không loại số chuyến hoàn
thành. TLC thiếu quote/nonbookers, phương án không chọn và cơ chế gán chính sách.

### Ước lượng, kịch bản và Swissmetro

Một `choice_block` có **50 phiên**; outcome là tỷ lệ chọn X/Y, treatment là
log tự nhiên của hệ số giá. Ma trận thật trong các DGP có hiệu ứng là
`[[-0.60, 0.15], [0.12, -0.50]]` (hàng outcome, cột giá); NULL_EFFECT có ma trận 0.
Năm DGP kiểm tra giá ngẫu nhiên, nhiễu quan sát được, nhiễu ẩn, hiệu ứng 0 và giá
đồng tuyến. Naive OLS chỉ dùng giá; adjusted OLS thêm bối cảnh; LinearDML dùng
random forest/cross-fitting phần dư. Biến ẩn, truth và assignment oracle không
vào learner. DML không khắc phục nhiễu ẩn.

Train **01–20/01**, validation **21–25/01**, test **26–31/01**; context chỉ fit
train. Năm folds theo ngày gốc; bootstrap theo ngày và refit toàn bộ mô hình.
Kịch bản +10% giá X dùng `log(1.1)`, giữ giá Y và quần thể quote cố định.
Kiểm tra hỗ trợ chung trong miền **0,90–1,10** và xác suất ở từng context;
giá không hỗ trợ/không nhận dạng không trả forecast; khoảng kịch bản không
được xuất nếu có draw xác suất không hợp lệ. Khoảng chưa ổn định được gắn trạng
thái rõ ràng. Dashboard chỉ đọc artifact đã hoàn tất, checksum hợp lệ,
không fit/bootstrap trong giao diện.

Swissmetro chạy riêng: nguồn EPFL **10.728 dòng/1.192 người**, bỏ **9 dòng
`CHOICE=0`**, giữ **10.719 dòng/1.191 người** và mọi mục đích chuyến đi (`SP=1`).
Mười dòng thuộc nhóm trùng thuộc tính được giữ như nhiệm vụ khảo sát riêng.
Seed **31001** chia theo người: train **833/7.497** người/dòng, validation và test
**179/1.611** mỗi tập, không trùng người. MNL có hai constants Train/Car,
Swissmetro làm mốc, hệ số time/cost chung; baseline chỉ có constants, cả hai
xét availability và fit train. Time là phút/100, cost CHF/100; GA holders có
chi phí tăng thêm Train/Swissmetro bằng 0. Không chọn/tune mô hình trên test.

## 5. Kết quả kiểm chứng

### 5.1. Benchmark 20 seed/DGP — kết quả đã nộp

Run `20261003T135730-1ae94396`, seeds **10001–10020**, năm DGP: **100 jobs**, không
job lỗi, **66,59 giây**. Profile tổng hợp development: **1.860 blocks/93.000
sessions**, 20 trees/forest, **0 bootstrap draws**. Bảng là RMSE lớn nhất trong
bốn ô hệ số qua 20 seeds (đơn vị probability/log-price); cột cuối là RMSE xác
suất kịch bản DML trên test (+10% giá X, giữ Y).

| DGP | Naive OLS | Adjusted OLS | DML | RMSE xác suất DML |
|---|---:|---:|---:|---:|
| RCT_SYN | 0,028020 | 0,025927 | 0,025527 | 0,007564 |
| OBSERVED_CONFOUNDING | 0,101744 | 0,030885 | 0,032944 | 0,008325 |
| HIDDEN_CONFOUNDING | 0,108117 | 0,036286 | 0,040800 | 0,015712 |
| NULL_EFFECT | 0,027939 | 0,025774 | 0,025640 | 0,007600 |
| COLLINEAR_PRICE | Không nhận dạng | Không nhận dạng | Không nhận dạng | N/A |

Ngưỡng kỹ thuật RCT **RMSE hệ số ≤ 0,10; RMSE xác suất ≤ 0,02** đạt trong
profile này. Điều chỉnh giảm lỗi khi nhiễu quan sát được; adjusted OLS hơi tốt
hơn DML ở trường hợp đó. Cả **60 fits đồng tuyến** trả `not_identified`.
Coverage và null false positives chưa được đo trong run này vì không có bootstrap.

### 5.2. TLC-context bootstrap và kịch bản — kết quả đã nộp

Run `20261003T130951-df24a7e4`, RCT seed **42**: **7.440 blocks/372.000 sessions**;
train **4.800 blocks/20 ngày**, test **1.440 blocks**. Ba estimators hoàn tất
**199/199 refits mỗi estimator**, không fit lỗi; fit/bootstrap **516,21 giây**.
DML ước lượng `[[-0.590036, 0.169760], [0.101347, -0.498596]]`; RMSE xác suất
oracle **0,003678**. Ba trong bốn khoảng hệ số chứa truth; một run không xác lập
coverage thực nghiệm.

Kịch bản +10% giá X, giữ Y, **10.000 phiên giả định**; support/interval `ok`,
**199 draws xác suất hợp lệ**, không draw không hợp lệ:

| Lựa chọn | Trước (%) | Sau (%) | Thay đổi (điểm %) |
|---|---:|---:|---:|
| X | 31,2280 | 25,6044 | −5,6236 |
| Y | 25,9856 | 26,9516 | +0,9659 |
| NONE | 42,7864 | 47,4441 | +4,6577 |

Lựa chọn đặt xe kỳ vọng giảm **465,77**, khoảng bootstrap cá biệt 95%
**[−488,62; −439,38]**. Đây là lựa chọn mô phỏng, chưa phải số chuyến hoàn thành
hay doanh thu. Không gộp run này với run 20 seed để tuyên bố calibration.

### 5.3. Swissmetro — kết quả bổ sung

Run `week2-swissmetro-final-31001`; log loss là nats/task (thấp hơn tốt hơn),
accuracy là tỷ lệ 0–1. Hai mô hình dùng cùng mẫu số: train **7.497 dòng**;
validation/test **1.611 dòng mỗi tập**.

| Mô hình | Train log loss | Validation log loss | Test log loss | Test accuracy |
|---|---:|---:|---:|---:|
| Intercept-only | 0,880078 | 0,903043 | 0,881660 | 0,574798 |
| MNL time/cost | 0,815995 | 0,807700 | 0,781474 | 0,669770 |

Test log loss giảm **0,100186 nats/task**. Cả hai optimizer hội tụ, rank đủ
**2 và 4**; xác suất tổng bằng 1, không vi phạm availability. Năm artifact được
xác minh checksum; lệnh chạy lại dùng lại đầu ra đã xác minh. Khoảng tin cậy cho
log loss/accuracy **N/A — chưa tính**.

**Rà soát nguồn ngày 07/10/2026:**
[EPFL/Biogeme, mục Data](https://biogeme.epfl.ch/) nêu các bộ dữ liệu, gồm
Swissmetro, có thể dùng cho nghiên cứu và giáo dục. Cùng nguồn tải, dictionary,
SHA-256 và split đã lưu, đây là căn cứ nghiệm thu provenance cho phạm vi PoC
học thuật. Giấy phép riêng và quyền tái phân phối/sử dụng thương mại chưa được
xác nhận; không suy ra từ giấy phép phần mềm. Bổ sung này không sửa source
manifest/artifacts đã đóng băng. Swissmetro đạt
kiểm tra kỹ thuật và đủ căn cứ sử dụng trong phạm vi trên; không chuyển hệ số
sang TLC/GSM.

Chạy lại trên mã nguồn cuối của kỳ này dưới ID `week2-swissmetro-closeout-31001`:
cả sáu dòng metrics và toàn bộ predictions trùng bản trên; năm artifact được
kiểm tra checksum, rồi lệnh dùng lại outputs đạt. Source hash của run mới trùng
policy benchmark cuối; run `week2-swissmetro-final-31001` giữ nguyên lịch sử.

### 5.4. Coverage đầy đủ và kiểm tra mã nguồn — tiến độ bổ sung

Reporting protocol: **100 seeds/DGP × 5 DGP = 500 jobs**, seeds **20001–20100**,
199 day-bootstrap draws/estimator được nhận dạng, cùng ba estimators; DML 50
trees/5 folds. Probe **19001** chỉ đo runtime (**510,53 giây**), loại khỏi báo cáo.
Snapshot đóng băng revision `574cf501304a777827c2e04704d96a1ab563e1b2`,
context build `214dd5a1184bd3705e66`. Batch tối đa năm seeds, timeout ba giờ,
khóa một runner; checkpoint được kiểm tra checksum khi resume.

Tại thời điểm chốt: **69/500 jobs thành công** (RCT seeds **20001–20069**),
**1 đang chạy** (20070), **0 thất bại**, **430 chưa bắt đầu**. Có **207 estimator
fits**, mỗi fit **199 draws yêu cầu/199 thành công**; **828 dòng coefficient
metrics** có status/interval `ok`. Các DGP khác chưa bắt đầu. Đã hoàn tất
**13/100 batches**; bảng tổng hợp hiện gồm **65 seed RCT**, còn bốn seed đã xong
trong batch đang chạy được giữ ở checkpoint và chưa vào bảng tổng hợp.

**Đã có kết quả thực nghiệm tạm** từ 65 seed RCT, mẫu số **65/100 seeds yêu cầu
cho từng estimator/ô hệ số**. RMSE dưới đây lấy giá trị lớn nhất trong bốn ô hệ
số; coverage min–max là khoảng giữa bốn tỷ lệ theo ô, không phải khoảng tin cậy.

| Estimator | Max theta RMSE | Scenario probability RMSE | Coverage theo ô (%; min–max) |
|---|---:|---:|---:|
| Naive OLS | 0,013108 | 0,003661 | 87,69–96,92 |
| Adjusted OLS | 0,011551 | 0,003613 | 86,15–93,85 |
| DML | 0,011807 | 0,003620 | 86,15–93,85 |

Point RMSE hiện thấp hơn mục tiêu RCT 0,10/0,02. Coverage cần rà soát: ô Y/Y
của adjusted OLS và DML hiện **56/65 = 86,15%**, khoảng tin cậy binomial 95%
**[75,34%; 93,47%]**, không chứa nominal 95%. Đây là dấu hiệu coverage thấp trong
kết quả tạm; chưa kết luận nghiệm thu thống kê của giao thức đầy đủ. Null false
positives **N/A — NULL_EFFECT chưa chạy**, không được diễn giải là tỷ lệ 0.

Nguồn: `week2_reporting/evaluation_metrics.csv` đã xác minh checksum;
checkpoint từng seed và bản đối chiếu `.cache/submission-20261007-results-034119.json`.
**Chưa chốt coverage/null/RMSE trên toàn bộ profile reporting hoặc nghiệm thu
thống kê.** Khi đủ giao thức, giữ binomial intervals, mẫu số yêu cầu/hợp lệ/lỗi
và gắn cờ draw failures >5%; hoàn tất chạy không tự chứng minh calibration.

Runtime trung bình **69 jobs đã xong: 516,41 giây/job (8,61 phút/job)**; đây là
phép đo của runner tuần tự tại mốc chốt, không phải cam kết thời gian cho DGP
khác hoặc chạy song song. Tối ưu compute tiếp tục ở chat riêng.

Đợt kiểm tra mã gần nhất ghi nhận **131 tests passed trong 40,95 giây**; Ruff check/format đạt
(36 files); ty **0.0.82** đạt trên toàn bộ `src/gsm_poc` với `--error-on-warning`.
Bản 04/10 ghi **42 tests** và **8 browser
checks** đạt, gồm ba tab, từ chối giá ngoài hỗ trợ và các độ rộng
320/375/414/768 px. Các kết quả browser này là lịch sử; chưa xác minh CI từ xa
cho bản bổ sung. Lỗi khởi động runner do thư mục `coverage` che optional import
đã sửa thành `week2_reporting`, có regression test; log cũ được giữ, không có
seed hoàn tất trong lần khởi động lỗi đó.

### 5.5. Policy-value độc lập — benchmark development

Run `week2-policy-final-32001-32020`; seeds **32001–32020**, hai DGP
**RCT_SYN/OBSERVED_CONFOUNDING**, **40 seed jobs**, **240 dòng policy results**.
Mỗi seed dùng **7.440 blocks/372.000 quote sessions**, bối cảnh synthetic,
50 trees/5 original-day folds; **không day-bootstrap**. Giao thức được cố định
trước đánh giá; độc lập với reporting coverage đang chạy.

X/Y là hai dịch vụ giả định cùng sở hữu; giá cơ sở **1 đơn vị chuẩn hóa mỗi
dịch vụ**. Policy là một cặp giá cố định trên mọi context, trong chín cặp
**0,90/1,00/1,10**. Unchanged giữ giá 1/1; simple rule giảm 10% giá X, giữ Y.
Hỗ trợ cần ít nhất **một training block** cho mỗi joint action và nhóm
zone/weekend/peak; ngưỡng development chưa xác lập overlap vận hành.

Fit chỉ trên train; chọn policy bằng **giá trị dự báo trên validation** và lưu
quyết định trước khi đọc oracle test. Evaluator nối truth theo dataset/block,
áp dụng ma trận DGP, không dùng learner để tự chấm. Oracle reference là giá trị
lớn nhất trong cùng lớp policy/lưới được hỗ trợ; unchanged luôn là nonintervention/
fallback. Lỗi khi kiểm tra test giữ giá trị không khả dụng, không chọn lại policy.

Bảng là **mean simulated gross booking value / 1.000 quote sessions**, đơn vị
giá chuẩn hóa; mẫu số **20 seeds/DGP/policy**. Uplift so với unchanged;
regret bằng giá trị oracle reference trừ giá trị policy.

| Policy | RCT value | RCT uplift | RCT regret | Observed value | Observed uplift | Observed regret |
|---|---:|---:|---:|---:|---:|---:|
| Unchanged | 551,352199 | 0,000000 | 23,569085 | 551,352199 | 0,000000 | 16,075210 |
| Simple rule | 565,472776 | 14,120577 | 9,448509 | 560,531721 | 9,179522 | 6,895688 |
| Naive OLS | 574,921284 | 23,569085 | 0,000000 | 521,061057 | −30,291142 | 46,366352 |
| Adjusted OLS | 574,921284 | 23,569085 | 0,000000 | 567,427409 | 16,075210 | 0,000000 |
| DML | 574,921284 | 23,569085 | 0,000000 | 567,427409 | 16,075210 | 0,000000 |
| Oracle reference | 574,921284 | 23,569085 | 0,000000 | 567,427409 | 16,075210 | 0,000000 |

RCT: ba learner cùng chọn 0,90/0,90 ở **20/20 seeds**. Observed: naive OLS
chọn 1,10/1,10 ở **19/20**, unchanged ở một seed; adjusted OLS và DML chọn
cùng oracle reference ở **20/20**. Hai phương pháp điều chỉnh hòa nhau;
không có bảo đảm DML hơn OLS. Lưới được hỗ trợ khác nhau giữa các observed
seeds; regret 0 chỉ áp dụng trong lưới đó.

**120 fits** hoàn tất, không learning failure; **240/240 giá trị test hợp lệ**,
không test rejection. Simple rule dùng unchanged fallback ở **7/20 observed
seeds** vì thiếu hỗ trợ; các learner không fallback. Fallback vẫn trong mẫu số,
không tính thành fit failure.

Chênh lệch DML trên cùng seed/test contexts, **20 cặp mỗi dòng**; khoảng 95%
Student-t không hiệu chỉnh đa so sánh, cho mean qua các seed độc lập:

| DGP | So với | Mean difference | Khoảng 95% |
|---|---|---:|---|
| RCT | Simple rule | 9,448509 | [9,437913; 9,459104] |
| RCT | Naive / adjusted OLS | 0,000000 | [0,000000; 0,000000] |
| Observed | Simple rule | 6,895688 | [3,028157; 10,763219] |
| Observed | Naive OLS | 46,366352 | [41,431590; 51,301115] |
| Observed | Adjusted OLS | 0,000000 | [0,000000; 0,000000] |

Các khoảng đo biến động development qua seeds, không thay thế day-bootstrap
calibration hoặc uncertainty của một policy triển khai. Quần thể quote cố định,
mọi booking hoàn tất và thanh toán; không capacity, hủy, chi phí hoặc phản ứng
cung. Đây là **giá trị booking mô phỏng, evidence C**, chưa phải doanh thu/ROI GSM.
Nguồn: `policy/{frozen_spec,seed_results,summary,paired_differences,report}` và
run manifest; runtime/checksum cuối ghi ở [bảng rà soát nghiệm thu](acceptance_review.md).

## 6. Phần còn thiếu, kế hoạch và dữ liệu GSM

| Điều kiện nghiệm thu Week 2 | Trạng thái và việc còn lại |
|---|---|
| Data | TLC đã đối soát; Swissmetro đã kiểm tra schema/units/splits, bổ sung căn cứ nghiên cứu/giáo dục ở mục 5.3; giữ giới hạn nguồn |
| Effect | Có recovery trên các run đã nêu; chờ kết luận từng DGP trên profile reporting đầy đủ |
| Scenario | Đã kiểm chứng trên run ở mục 5.2; cần chốt exports tương thích với bundle/config/scope cuối |
| Reproducibility | Đã có snapshot/hash/checksum và xác minh dùng lại Swissmetro; cần kiểm tra bộ bàn giao cuối cùng và rerun/resume tương ứng |
| Statistics | Chờ hoàn tất/rà soát 500 jobs; coverage thấp trong kết quả tạm cần xử lý, NULL_EFFECT chưa có kết quả |
| Additional benchmarks | Swissmetro hoàn tất trong phạm vi đã nêu; policy-value development đã chạy đủ 40 seed jobs, có evaluator test độc lập và kiểm tra tái lập (mục 5.5) |

**Chưa nghiệm thu đầy đủ Week 2.** Khi chốt, ghi người kiểm tra, ngày kiểm tra
và kết luận/ngoại lệ thực tế; không đồng nhất nghiệm thu kỹ thuật với thầy đã
phê duyệt. Đồng bộ báo cáo này và progress update tại cùng mốc số liệu cuối.

| Mốc dự kiến trong proposal | Đầu ra tiếp theo / điều kiện |
|---|---|
| Week 2: 05–11/10 | Policy-value development đã chạy; hoàn tất/rà soát coverage, kiểm tra bundle cuối, chốt bảng nghiệm thu và đồng bộ hai báo cáo. Provenance Swissmetro giữ căn cứ nghiên cứu/giáo dục ở mục 5.3 |
| Week 3: 12–18/10 | Phản ứng cung theo thu nhập/thưởng; simulator matching/hủy/sạc, cân bằng/nhàn rỗi; phát triển trên dữ liệu mô phỏng nếu chưa có GSM |
| Week 4: 19–25/10 | Dashboard vận hành/kinh tế, thiết kế switchback/carryover/cỡ mẫu và sổ đối chiếu dự báo–thực tế |
| Week 5: 26/10–01/11 | Tích hợp, kiểm thử và bàn giao; A/A/pilot khi đủ dữ liệu và được GSM chấp thuận |

Chưa có adapter/quote-session GSM, cung, simulator hoặc hiệu chỉnh vận hành thật;
không suy ra ROI từ chênh lệch tiền khách trả và driver pay. Policy benchmark
phải giữ cả zero/negative uplift và trường hợp baseline thắng. Lịch là kế hoạch,
không phải bằng chứng hoàn thành; full week-2 acceptance còn thiếu các gate
thống kê và bộ bàn giao cuối. [Bảng rà soát nghiệm thu](acceptance_review.md)
ghi bằng chứng và trạng thái từng gate, chưa phải phê duyệt của người kiểm tra.

Yêu cầu GSM **tám nhóm nguồn gốc trong 12 tháng gần nhất**, gồm vùng lân cận/
đối chứng: **Booking & Demand; Pricing & Promotion; Driver Supply & Status;
Driver Earnings & Incentive; Matching & Operations; Customer Choice/Cross-service;
Policy & Context; Finance & Cost**. Giữ cả không đặt/hủy/timeout/không có xe và
tài xế không có chuyến. GSM xuất, giả danh hóa nhất quán và giải thích nghiệp vụ;
Nguyễn Thành An tự ánh xạ schema, nối khóa, kiểm tra và dựng đặc trưng.

Giữ schema/tần suất log gốc; Parquet, CSV UTF-8 hoặc export hiện hữu; kèm dictionary,
keys, units/timezone/null, schema history và coverage/retention. Không cần dữ
liệu định danh cá nhân trực tiếp hoặc yêu cầu GSM dựng bảng 30 phút/bộ huấn luyện.
Khóa session–quote–request–trip và dispatch–driver/vehicle–shift/charging phải
truy vết được; giá/thưởng trước quyết định tách khỏi khoản thực nhận sau đó.
Nguồn thiếu ghi Có/Chưa ghi nhận/Không áp dụng, không thay bằng 0. Chi tiết theo
[data contract](../../../GSM_DATA_CONTRACT.md); kết luận nhân quả/kinh tế và
A/A/pilot phụ thuộc nhận dạng, chi phí và phê duyệt thử nghiệm phù hợp.

## Phụ lục. Nguồn kiểm chứng và tái lập

- Hồ sơ đã nộp: [báo cáo kỹ thuật 04/10](../20261004/POC_Technical_Report.md),
  [tiến độ 04/10](../20261004/Progress_Update.md), [phân công cá nhân](../20261004/Team_Allocation.md).
- Thiết kế và số liệu: [proposal](../../../general/GSM_Causal_Marketplace_Proposal.md),
  [validation lịch sử](../../../VALIDATION.md), [benchmark](../../../BENCHMARK.md),
  [run/resume week 2](../../../WEEK_2_BENCHMARKS.md).
- Các đường dẫn dưới tính từ repo root: `runs/week2-swissmetro-final-31001/manifest.json`
  và `swissmetro/{source_manifest,splits,report,metrics,predictions}`;
  `.cache/week2-evaluation-574cf501-20261007/week2_reporting/` và `runs/` trong snapshot;
  bản đối chiếu kỳ này `.cache/submission-20261007-results-034119.json`;
  `runs/week2-policy-final-32001-32020/policy/` và
  `runs/week2-swissmetro-closeout-31001/swissmetro/`.
- Windows/Python **3.11.9**, uv **0.10.12**, `uv.lock`; NumPy **2.4.6**, pandas **2.3.3**,
  SciPy **1.17.1**. Manifests lưu effective config, package versions, code/data/lock/output
  hashes, seeds, runtime và lỗi. Source hash coverage:
  `8459df189c1da3d4252f1ac2445854ac684c4ee15cecf951d80cbfd5402648a0`;
  source hash Swissmetro (có mã chưa commit):
  `84312e859833bfdc254a95cc2589152b266c492e9ca42da856e418771fedca88`.
  Source hash của policy và Swissmetro chạy lại kỳ này:
  `68a7a1b7bf19ec6eb2dff47ecb90a0c429c5c34e724232c371c9b3b0535661f3`.
  Run cũ lưu revision `c2d24a2` và code hash riêng, không gán cho HEAD hiện tại.
- Repository: [Muscar1a/gsm-ride-hailing](https://github.com/Muscar1a/gsm-ride-hailing).
  Demo chạy cục bộ; chưa có URL demo công khai. Dữ liệu/run lớn không đưa vào Git.

```powershell
uv sync --locked
uv run python -m gsm_poc run-all --config configs/demo.toml
uv run streamlit run src/gsm_poc/app.py
.venv/Scripts/python.exe -m gsm_poc.swissmetro --seed 31001 --run-id week2-swissmetro-closeout-31001
.venv/Scripts/python.exe -m gsm_poc.policy_benchmark --config configs/policy_development.toml --run-id week2-policy-final-32001-32020
```

Lệnh demo không thay thế reporting protocol; resume coverage theo runbook với
snapshot/config/seeds nguyên trạng. Sửa tài liệu không tính là chạy lại các
benchmark, tests hoặc browser checks đã ghi ở trên.
