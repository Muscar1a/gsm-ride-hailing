# Báo cáo kỹ thuật PoC GSM Causal Marketplace

**Người thực hiện: Nguyễn Thành An · Email: 26ai.annt@vinuni.edu.vn**

## 1. Bài toán và phạm vi đã thực hiện

PoC ước lượng phản ứng lựa chọn khi thay đổi giá gọi xe. Mỗi phiên xem báo giá chọn X, Y hoặc không đặt (NONE). Đầu ra là ma trận tác động giá trực tiếp/chéo và kịch bản xác suất lựa chọn.

Phiên bản này đã triển khai pipeline dữ liệu, bộ sinh hành vi có đáp án xác định, so sánh OLS/DML, bootstrap theo ngày, mô-đun kịch bản và dashboard. Các phản ứng hành vi là **mô phỏng, mức bằng chứng C**; dữ liệu TLC chỉ cung cấp bối cảnh các chuyến đã hoàn thành tại New York. Baseline lựa chọn Swissmetro trong yêu cầu dữ liệu mới chưa được triển khai.

Mục tiêu hiện tại là kiểm tra phương pháp và tính tái lập. Giá trị kinh doanh cần đo bằng doanh thu thực thu và biên đóng góp GSM; hiện chưa có dữ liệu hoặc bằng chứng doanh thu GSM.

PoC do một người thực hiện, đồng thời chịu trách nhiệm nộp báo cáo. Báo cáo đối chiếu mục tiêu dự án trong [proposal ban đầu](../../../reference/GSM_Causal_Marketplace_Proposal.md), theo yêu cầu cập nhật ngày 29/9.

| Mục tiêu trong proposal | Trạng thái PoC hiện tại |
|---|---|
| Độ nhạy giá và thay thế chéo theo vùng/giờ/dịch vụ | Đã kiểm chứng OLS/DML trên dữ liệu kiểm soát; hiện dùng ma trận chung và số phiên báo giá cố định, bằng chứng C |
| Phản ứng cung theo thu nhập kỳ vọng/thưởng | Chưa triển khai mô hình; đã nêu dữ liệu và cơ chế chi trả cần xác nhận |
| Simulator một cụm, hiệu chỉnh nền, điểm cân bằng mới và nguồn cung nhàn rỗi | Chưa xây simulator hoặc hiệu chỉnh; chưa có các đầu ra này |
| Dashboard/CSV/JSON với kết quả vận hành, kinh tế và ROI khi đủ dữ liệu | Có dashboard vận hành TLC và kịch bản lựa chọn; chưa dự báo chuyến hoàn thành, doanh thu, biên đóng góp hoặc ROI GSM |
| Thiết kế switchback, sổ đối chiếu dự báo–thực tế; A/A/pilot khi đủ điều kiện | Mới có yêu cầu sơ bộ; chưa có thiết kế chi tiết, sổ đối chiếu hoặc A/A/pilot |

Vì vậy, PoC đã hoàn thành phần nền dữ liệu, kiểm chứng cầu/thay thế chéo và demo trong phạm vi hiện tại; chưa hoàn thành toàn bộ mục tiêu năm tuần.

## 2. Dữ liệu và kiểm soát chất lượng

Nguồn công khai là TLC HVFHV tháng 01/2024 và bảng tra vùng taxi. Phạm vi chọn năm vùng đón 161, 162, 163, 164, 170; hai mã nền tảng HV0003/HV0005; giữ các chuyến có điểm trả ngoài cụm. Timestamp nguồn không kèm múi giờ được xử lý với giả định `America/New_York`.

| Hạng mục | Kết quả kiểm tra |
|---|---:|
| Tệp chuyến nguồn | 19.663.930 dòng, 24 trường; 472.757.547 byte |
| Bảng vùng | 265 dòng |
| Silver toàn tháng trong phạm vi | 970.940 chuyến hợp lệ về khóa cốt lõi |
| Mart toàn tháng | 14.880 ô vùng × 30 phút × nền tảng |
| Tổng chuyến được đối soát | 970.940 |
| Mart bảy ngày dùng cho demo | 3.360 ô; 175.861 chuyến |
| Giá dương hợp lệ / thời gian từ yêu cầu tới đón hợp lệ | 970.675 / 960.950 dòng |

Dữ liệu gốc được giữ nguyên và gắn SHA-256; không tự loại bản ghi trùng. Các cờ chất lượng độc lập giữ số chuyến hoàn thành khi chỉ một chỉ số không hợp lệ. Ô không có chuyến chỉ nhận số đếm 0 sau khi xác minh nguồn đầy đủ; phân vị thiếu dữ liệu giữ trạng thái thiếu. Tổng mart được đối soát chính xác với silver cùng phạm vi.

240 mẫu bối cảnh vùng/giờ/cuối tuần chỉ dùng ngày 01–20/01, không cần fallback. TLC thiếu phiên không đặt, phương án không chọn và cơ chế gán chính sách; không xác định chuyển đổi hay độ co giãn GSM.

Yêu cầu dữ liệu gốc (PDF nguồn không có trong checkout) bổ sung EPFL Swissmetro cho benchmark lựa chọn độc lập. Trong PoC hiện tại, Swissmetro **chưa được tải, chưa có baseline hoặc kết quả kiểm thử**; các thực nghiệm đã báo cáo chỉ dùng TLC và dữ liệu tổng hợp/bán tổng hợp. Số liệu kiểm tra Swissmetro trong PDF nguồn không phải kết quả của phiên bản này. Khi triển khai, hai benchmark public chạy riêng; không nối bản ghi hoặc chuyển hệ số giữa New York, Thụy Sĩ và GSM.

## 3. Phương pháp và nhận diện nhân quả

Đơn vị học là block chính sách với 50 phiên xem báo giá. Kết quả là tỷ lệ chọn X/Y; treatment là log tự nhiên của hệ số giá X/Y. Với bối cảnh trước chính sách W, mô hình kiểm chứng có dạng:

```text
p(W, T) = b(W) + theta × T
theta thật = [[-0.60, 0.15], [0.12, -0.50]]
```

Hàng ma trận là dịch vụ được chọn, cột là giá thay đổi. Hệ số có đơn vị xác suất trên một đơn vị log giá. Trường hợp HIDDEN_CONFOUNDING có thêm thành phần từ biến ẩn U trong xác suất lựa chọn và cơ chế gán giá. Trong trường hợp hiệu ứng bằng không, ma trận thật là 0. X/Y là dịch vụ giả định, không phải ước lượng Uber/Lyft hay GSM.

| Bộ sinh dữ liệu (DGP) | Vai trò kiểm chứng |
|---|---|
| RCT_SYN | Giá ngẫu nhiên độc lập; kiểm tra thu hồi hiệu ứng |
| OBSERVED_CONFOUNDING | Bối cảnh ảnh hưởng giá và lựa chọn; kiểm tra điều chỉnh |
| HIDDEN_CONFOUNDING | Biến ẩn U ảnh hưởng cả hai; kiểm tra giới hạn |
| NULL_EFFECT | Kiểm tra kết quả khi hiệu ứng thật bằng 0 |
| COLLINEAR_PRICE | Hai giá đồng biến hoàn toàn; phải từ chối tách hiệu ứng |

Ba phương pháp dùng cùng dữ liệu: naive OLS chỉ gồm giá; adjusted OLS thêm bối cảnh; LinearDML dùng random forest rồi hồi quy phần dư. Bối cảnh gồm vùng, giờ, thứ, cuối tuần, cao điểm, khoảng cách. Biến ẩn, đáp án thật và xác suất assignment không vào đặc trưng.

Ngày 01–20 dùng huấn luyện; 21–25 dùng validation; 26–31 dùng đánh giá cuối. Cross-fitting gồm năm fold theo ngày gốc. Bootstrap lấy lại mẫu ngày và huấn luyện lại toàn bộ mô hình; các bản sao một ngày giữ cùng nhóm. Điều kiện nhận diện cần nhiễu đã quan sát đủ, biến thiên giá và hỗ trợ phù hợp. DML không loại được nhiễu ẩn.

## 4. Kiến trúc và kịch bản

```text
TLC → Bronze bất biến → Silver/cờ chất lượng → Mart vận hành
                           ↓ bối cảnh chỉ từ tập huấn luyện
                     Bộ sinh chính sách và lựa chọn
                           ↓ dữ liệu quan sát giả lập
                     OLS / DML → Bootstrap → Kịch bản
                           ↓
                     Artifact → Dashboard / CSV / JSON

Oracle (đáp án thật) → Bộ đánh giá phương pháp, tách khỏi estimator
```

Pipeline batch dùng Python 3.11, DuckDB/Parquet, EconML và Streamlit. TOML/`uv.lock` cố định cấu hình và môi trường. Manifest lưu seed, revision, SHA dữ liệu/đầu ra, thời gian và lỗi. Dashboard đọc artifact hoàn thành có checksum hợp lệ, không huấn luyện qua giao diện.

Ba màn hình gồm dữ liệu vận hành, kiểm chứng phương pháp và kịch bản giá. Kịch bản sử dụng xác suất nền được học, tỷ số log giá, và tập bối cảnh đánh giá cố định. Tăng giá 10% dùng `log(1.1)`. Đầu ra gồm X/Y/NONE, thay đổi điểm phần trăm, số lựa chọn kỳ vọng và khoảng bất định.

Giá phải nằm trong miền hỗ trợ 0,90–1,10 và có hỗ trợ chung thích hợp. Xác suất được kiểm tra tại từng bối cảnh, không cắt hay chuẩn hóa để che lỗi. Giá không được hỗ trợ, giá đồng tuyến hoặc khoảng bất định chưa ổn định có trạng thái rõ ràng. Khoảng kịch bản bị giữ lại nếu có draw cho xác suất không hợp lệ.

## 5. Kết quả thực nghiệm: benchmark phương pháp

Run `20261003T135730-1ae94396` dùng **20 seed mới mỗi DGP**, từ 10001–10020: tổng 100 job, không job thất bại, thời gian 66,59 giây. Đây là cấu hình hoàn toàn tổng hợp: 1.860 block, 93.000 phiên, 20 cây mỗi random forest. Seed và ngưỡng được cố định trước; không chỉnh tham số theo kết quả cuối.

RMSE đo sai số so với đáp án thật qua các seed. Bảng lấy RMSE lớn nhất trong bốn hệ số; đây là độ chính xác hiệu ứng, không đo doanh thu. Cột cuối là sai số xác suất test khi tăng giá X 10%, giữ giá Y.

| DGP | Naive OLS | Adjusted OLS | DML | RMSE xác suất DML |
|---|---:|---:|---:|---:|
| RCT_SYN | 0,028020 | 0,025927 | 0,025527 | 0,007564 |
| OBSERVED_CONFOUNDING | 0,101744 | 0,030885 | 0,032944 | 0,008325 |
| HIDDEN_CONFOUNDING | 0,108117 | 0,036286 | 0,040800 | 0,015712 |
| NULL_EFFECT | 0,027939 | 0,025774 | 0,025640 | 0,007600 |
| COLLINEAR_PRICE | Không nhận diện | Không nhận diện | Không nhận diện | Không có |

Điều chỉnh giảm sai số so với naive OLS khi nhiễu quan sát được. Adjusted OLS tốt hơn DML một chút trong trường hợp này; chưa có căn cứ khẳng định DML luôn vượt baseline đơn giản. Cả 60 fit đồng tuyến trả `not_identified`. Nhiễu ẩn vẫn là trường hợp căng thẳng không có bảo đảm nhận diện.

Run này yêu cầu **0 bootstrap draw**: coverage và tỷ lệ dương tính giả chưa được đo. Ngưỡng kỹ thuật RCT của thiết kế (RMSE hệ số ≤0,10; RMSE xác suất ≤0,02) đạt trong cấu hình đã chạy. Đánh giá 100 seed mỗi DGP với khoảng tin cậy ổn định chưa thực hiện.

## 6. Kết quả bán tổng hợp và kiểm thử

Run `20261003T130951-df24a7e4` dùng bối cảnh TLC thật và lựa chọn mô phỏng RCT_SYN, seed 42: 7.440 block, 372.000 phiên; tập train 4.800 block trên 20 ngày; test 1.440 block. Cả ba estimator hoàn thành 199/199 bootstrap refit, không lỗi fit; kiểm tra độ nhạy khoảng được chấp nhận. Fit/bootstrap mất 516,21 giây trên máy kiểm thử.

Ma trận DML ước lượng là `[[-0.590036, 0.169760], [0.101347, -0.498596]]`. RMSE xác suất kịch bản trên oracle là 0,003678. Ba trong bốn khoảng hệ số chứa giá trị thật; một run riêng lẻ không xác lập coverage 95% thực nghiệm.

Kịch bản tăng giá X 10%, giữ giá Y, giả định 10.000 phiên có 199 draw xác suất hợp lệ, không draw không hợp lệ; trạng thái hỗ trợ và khoảng là `ok`:

| Lựa chọn | Trước (%) | Sau (%) | Thay đổi (điểm %) |
|---|---:|---:|---:|
| X | 31,2280 | 25,6044 | −5,6236 |
| Y | 25,9856 | 26,9516 | +0,9659 |
| NONE | 42,7864 | 47,4441 | +4,6577 |

Tổng lựa chọn đặt xe kỳ vọng giảm 465,77, khoảng bootstrap cá biệt 95% [−488,62; −439,38]. Đây là đầu ra mô phỏng với số phiên cố định, không phải thay đổi chuyến hoàn thành hoặc doanh thu GSM. Không kết hợp run này với benchmark 20 seed để tuyên bố calibration.

42 kiểm thử tự động, lint và format đã đạt trên Windows/Python 3.11.9. Tám kiểm tra browser đạt, gồm ba màn hình, từ chối giá ngoài hỗ trợ và bố cục 320/375/414/768 px. Workflow GitHub Actions có trong repo; kết quả CI từ xa chưa được xác minh trong báo cáo này.

## 7. Hạn chế và bước tiếp theo

PoC chưa có dữ liệu phiên báo giá GSM, adapter GSM, phản ứng cung, ghép chuyến, sạc xe, giao thoa không gian hoặc mô phỏng doanh thu/ROI. Chỉ có 20 ngày huấn luyện độc lập; bootstrap đạt điều kiện kỹ thuật trong một run chưa đủ để xác nhận calibration. Các hiệu ứng giả lập không chuyển trực tiếp sang thị trường GSM.

Bước tiếp theo theo phần việc tuần 3–5 trong proposal: xây phản ứng cung theo cơ chế thu nhập/thưởng; simulator một cụm có ghép chuyến, sạc, vòng lặp cân bằng và chỉ số nhàn rỗi; hoàn thiện dashboard kịch bản vận hành/kinh tế, thiết kế switchback, sổ đối chiếu và kiểm tra A/A/pilot khi đủ điều kiện. Mô hình, simulator và thiết kế có thể tiếp tục trên dữ liệu tổng hợp khi chưa có GSM; hiệu chỉnh vận hành thật và kết luận ROI cần dữ liệu GSM hợp lệ.

Song song, đánh giá coverage trên nhiều seed, xây benchmark chính sách giá dùng oracle độc lập trên tập test, thẩm định schema/cơ chế gán giá và tích hợp dữ liệu GSM sau khi thống nhất điều kiện nhận diện. Benchmark giữ cả kết quả không tăng hoặc giảm giá trị và trường hợp baseline thắng.

Bổ sung adapter và baseline lựa chọn EPFL Swissmetro theo yêu cầu dữ liệu mới, với tập phương án khả dụng và nhãn nguồn riêng. Đây là phần việc tiếp theo, chưa phải kết quả đã hoàn thành; không dùng benchmark này để kết luận độ co giãn GSM.

Với GSM, thống nhất doanh thu thực thu và chi phí biến đổi trước khi đo uplift; bổ sung biên đóng góp, chuyển đổi báo giá, hoàn thành, hủy, thời gian chờ và kết quả tài xế. Dữ liệu lịch sử cần hỗ trợ chính sách và giả định nhân quả đáng tin cậy. Tuyên bố tác động doanh thu cần so sánh chính sách đáng tin cậy, ưu tiên thử nghiệm ngẫu nhiên phù hợp, có thiết kế giao thoa/carryover và khoảng tin cậy.

## 8. Dữ liệu GSM cần cung cấp và tái lập

Danh mục thống nhất cho toàn bộ proposal theo GSM Causal Marketplace — Data Requirements (PDF nguồn không có trong checkout): **12 tháng gần nhất** của các dịch vụ/khu vực liên quan, gồm vùng lân cận và đối chứng; mở rộng lịch sử nếu cần bao phủ thay đổi chính sách. Nguồn lưu ngắn hơn cung cấp toàn bộ phần hiện có và ghi độ phủ. Giữ cả trường hợp không đặt, hủy, timeout, không có xe và tài xế không có chuyến.

| Nhóm nguồn dữ liệu gốc | Bảng/log hiện hữu và nội dung chính |
|---|---|
| 1. Booking & Demand | Request/booking/trip và log trạng thái, kể cả thất bại/đặt lại; khóa nối, thời điểm yêu cầu–điều phối–nhận–đón–trả/hủy, vùng, cự ly/thời lượng và trạng thái thanh toán |
| 2. Pricing & Promotion | Biểu giá/phiên bản và cấu phần từng quote; giá trước/sau giảm, phí/thuế; log đủ điều kiện–tiếp xúc–sử dụng voucher; gói thuê bao, phí/quyền lợi và vòng đời đăng ký |
| 3. Driver Supply & Status | Danh mục/hợp đồng, ca được giao/chào nhận, phân xe và log online/offline/available/busy/break/charging; vùng, mất log; gồm ca/tài xế không có chuyến hoặc không nhận ưu đãi |
| 4. Driver Earnings & Incentive | Quy tắc chi trả, thông báo/gán/hiển thị thưởng và eligibility trước quyết định; sổ lương/hoa hồng/thưởng/điều chỉnh thực nhận sau ca/chuyến; thông tin kỳ vọng đã hiển thị nếu có |
| 5. Matching & Operations | Từng dispatch và accept/reject/timeout, phiên bản matching, ETA/hành trình đón; trạng thái/eligibility xe, pin, bảo trì; phiên sạc/chờ sạc, kWh/chi phí và danh mục/khả dụng trạm |
| 6. Customer Choice / Cross-service | Log tìm kiếm/quote/hiển thị/làm mới và tương tác theo từng dịch vụ, gồm phiên không đặt; phân biệt quote tạo với quote thực thấy, khả dụng/vị trí/giá/ETA, lựa chọn và thời điểm kết thúc quan sát |
| 7. Policy & Context | Phiên bản chính sách, quy tắc/xác suất gán, giá trị assigned/applied, override và đối chứng; hồ sơ thử nghiệm nếu có; ranh giới vùng, thời tiết/giao thông/sự kiện và sự cố vận hành |
| 8. Finance & Cost | Sổ thu/chi/điều chỉnh, giá gộp/thực thu/giảm/hoàn tiền, thuế/phí, chi trả tài xế/thưởng, tài trợ, điện/sạc và chi phí biến đổi; quy tắc/phiên bản phân bổ chi phí và trạng thái đối soát |

GSM trích xuất, giả danh hóa nhất quán xuyên bảng/thời gian và giải thích nghiệp vụ. Người thực hiện PoC ánh xạ schema, nối khóa, kiểm tra chất lượng, dựng funnel/giờ cung, tổng hợp vùng–thời gian, tạo đặc trưng và ước lượng. **Không yêu cầu GSM nối bảng, đổi schema, tạo bảng 30 phút/bộ huấn luyện, tính độ co giãn, thu nhập kỳ vọng hoặc nhãn phản thực tế.** Nếu thông tin kỳ vọng chưa được lưu, cung cấp quy tắc/dữ liệu nguồn để phía nghiên cứu tái dựng.

Bàn giao Parquet, CSV UTF-8 hoặc bản xuất hiện có; giữ bảng riêng, tên trường gốc và tần suất log/snapshot. Kèm từ điển/bảng mã, khóa/bảng ánh xạ, đơn vị, timezone, null, lịch sử schema, lấy mẫu và retention nếu có; danh mục tệp, độ phủ và tổng đối soát hiện hữu. Không cần tên, điện thoại hoặc giấy tờ cá nhân. Từng nguồn/trường xác nhận **Có, Chưa ghi nhận hoặc Không áp dụng**, không gán 0 cho thông tin chưa biết.

Giữ chuỗi khóa session → quote_set → quote → request/booking → trip và request → dispatch → driver/vehicle → shift/charging_session; không coi nối theo thời điểm gần nhất là chắc chắn. Giá/thưởng hiển thị phải có trước quyết định; khoản thực nhận là kết quả sau quyết định. Thiếu request_id không tự nghĩa là không đặt; không đặt trong cửa sổ không chứng minh rời GSM/chuyển đối thủ. Không coi chênh tiền khách trả và driver_pay là lợi nhuận; thiếu chi phí ghi ROI chưa xác định. Chi tiết trường/khóa theo PDF đính kèm, không yêu cầu GSM tạo các bảng chuẩn hóa nội bộ của PoC.

Repository: [Muscar1a/gsm-ride-hailing](https://github.com/Muscar1a/gsm-ride-hailing), **công khai**. Đã xác minh ngày 04/10/2026: remote `main` có commit PoC `217e1f46ab784c4a771ce7c70bd12094cbdc1427`, trùng snapshot mã PoC cục bộ. Các tài liệu hồ sơ nộp đang được hoàn thiện cục bộ. Demo chạy cục bộ, chưa có URL công khai. Môi trường đo: Python 3.11.9, uv 0.10.12, lockfile trong repo. Dữ liệu/run lớn không lưu trong Git.

```powershell
uv sync --locked
uv run python -m gsm_poc run-all --config configs/demo.toml
uv run streamlit run src/gsm_poc/app.py
```

Run benchmark 20 seed dùng `evaluate --config configs/demo.toml --seed 10001 --seeds 20 --bootstrap-draws 0 --dgps RCT_SYN OBSERVED_CONFOUNDING HIDDEN_CONFOUNDING NULL_EFFECT COLLINEAR_PRICE`. Run bán tổng hợp dùng `run-all --config configs/tlc_quick.toml --bootstrap-draws 199 --skip-monte-carlo` sau `uv run python -m gsm_poc`.

Manifest hai run ghi revision lúc đo `c2d24a2` và SHA code `8af06450fdbbc7269ad493bc92743e830f5270516e1273ef26f182f1040a4e2e`; SHA code nhận diện nội dung thực nghiệm, không chứng minh nội dung đã được push. SHA tệp TLC: `9897de352aa52cea36b70348cc6721b8d4494327ce39c85f0dba83d86ecaa098`. Run toàn tháng `20261003T131251-0b5e2209` chỉ dựng dữ liệu, không chạy benchmark 100 seed.

Tài liệu đối chiếu trong repo: [proposal ban đầu](../../../reference/GSM_Causal_Marketplace_Proposal.md), `docs/submission/days/20261003/validation.md`, `docs/IDENTIFICATION.md`, `docs/ARCHITECTURE.md`, `docs/BENCHMARK.md`, `docs/GSM_DATA_CONTRACT.md`. Tham chiếu kỹ thuật: [EconML LinearDML](https://www.pywhy.org/EconML/_autosummary/econml.dml.LinearDML.html); nguồn dữ liệu: [TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
