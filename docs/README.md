# Tài liệu GSM Causal Marketplace PoC

Đọc tài liệu theo thứ tự: tiến độ hiện tại → roadmap → contract → thiết kế hoặc
hướng dẫn kỹ thuật cần cho công việc. Cập nhật danh mục ngày **12/10/2026**;
kết quả reporting tuần 2 chốt lúc **17:13:28 ngày 07/10/2026, Asia/Bangkok**.

Mục tiêu là ước lượng và kiểm chứng nhân quả **độ nhạy giá khách hàng, cung lao động
tài xế và thay thế giữa dịch vụ**, rồi dự báo, đánh giá chính sách và đối chiếu
bằng thí nghiệm. [Proposal](reference/GSM_Causal_Marketplace_Proposal.md) quản lý
mục tiêu/phạm vi; [core engine design](reference/CORE_ENGINE_DESIGN.md#11-engine-delivery-standard)
quản lý thuật toán và tiêu chuẩn hỗ trợ. Các đặc tả và trạng thái hiện hành được
dẫn bên dưới; kết quả thiếu dữ liệu hoặc nhận diện giữ `not_evaluated`.

**Phạm vi PoC hiện tại được Bun chốt ngày 12/10/2026:** giả sử một nhóm tài xế
online cố định trong khoảng quan sát; tài xế được nhận hoặc từ chối từng đơn,
và nhận 100% giá cước hiển thị khi hoàn thành chuyến. Không triển khai ưu đãi,
chia ca, quyết định bật/tắt app theo chính sách hoặc cân bằng thu nhập–giờ làm
trong PoC này. Xem [WEEK3_POC_SCOPE.md](WEEK3_POC_SCOPE.md). Giả định cung online
cố định không xác định độ co giãn cung lao động trong mục tiêu nghiên cứu rộng hơn.

## Tiến độ hiện tại

**Đặc tả Week 1 được Bun duyệt ngày 11/10/2026.** Phạm vi duyệt gồm
câu hỏi/estimand trong [IDENTIFICATION.md](IDENTIFICATION.md), đặc tả trạng thái
nguồn và mapping trong [ARCHITECTURE.md](ARCHITECTURE.md#research-table-schemas),
khung xác nhận tiêu chí kinh doanh và kế hoạch đánh giá trong [BENCHMARK.md](BENCHMARK.md).
Điều kiện đóng tuần nằm trong
[roadmap tuần 1](ROADMAP.md#week-1-specification-and-closure).

Rà soát ngày 11/10 xác nhận nền public/synthetic có thể tái sử dụng: run
`20261003T131251-0b5e2209` có tám artifact ingest/build tồn tại và khớp checksum,
silver/mart cùng đối soát **970.940 chuyến**, và split của choice run
`20261003T130951-df24a7e4` có 4.800/1.200/1.440 block train/validation/test,
không trùng ngày. **49 kiểm thử liên quan** về dữ liệu, độ phủ, generator,
estimation và artifact/CLI đạt trong lần rà soát; thư mục tạm được đặt trong
workspace. Số liệu lịch sử nằm trong [validation 03/10](submission/days/20261003/validation.md).
Các kiểm tra này xác nhận phạm vi TLC và controlled choice, chưa xác nhận
mapping/coverage GSM hoặc độ bao phủ khoảng tin cậy của mọi đáp ứng.

Theo xác nhận của Bun ngày 11/10, GSM đang xử lý và chưa bàn giao dữ liệu.
Mapping/độ phủ thực chưa được kiểm chứng; tiêu chí kinh doanh, mức cải thiện
đáng thử, biên độ chính sách và ngưỡng chờ/hủy/thu nhập/ngân sách còn chờ GSM
xác nhận. **Week 1: đặc tả đã duyệt; phần GSM chờ dữ liệu và xác nhận nghiệp vụ**.

**Week 2 được Bun nghiệm thu ngày 11/10/2026 với ngoại lệ kỹ thuật**;
phạm vi controlled evidence C và support được công bố trong
[hồ sơ nghiệm thu hybrid](submission/days/20261011/week2_hybrid_acceptance.md).
Reporting hoàn thành 500/500 seed jobs; Swissmetro và policy-value development
đã có kết quả lịch sử. `freeze-choice` giữ nguyên cả ba mô hình, effects,
bootstrap và hồ sơ nguồn, xuất riêng kết quả replay dưới quy tắc hiện tại và
phân biệt môi trường huấn luyện với đóng gói. Khoảng tin cậy được ghi rõ là
kiểm tra kỹ thuật; chưa xác nhận coverage thực nghiệm cho run đó.

[Kiểm chứng bàn giao 11/10](submission/days/20261011/choice_handoff_verification.md)
ghi kết quả replay/reuse và gate hiện tại. Các giá trị lịch sử tái tạo đúng,
nhưng kịch bản toàn bộ bối cảnh thiếu support ở một số nhóm theo kiểm tra hiện
hành. [Chẩn đoán support và khoảng tin cậy 11/10](submission/days/20261011/support_interval_diagnostic.md)
đã chọn phạm vi bằng dữ liệu huấn luyện: 10/20 nhóm, giữ 972/1.440 block và
48.600/72.000 phiên (67,5%); replay trong phạm vi này đạt support với ngưỡng
20 block giữ nguyên. Toàn bộ bối cảnh vẫn thiếu support.
[Nhánh so sánh interval](submission/days/20261011/interval_method_comparison.md)
đánh giá percentile/basic/BCa trên development riêng;
[sensitivity variance theo ngày](submission/days/20261011/interval_variance_comparison.md)
tái sử dụng jackknife đã lưu, không thêm fit hoặc seeds độc lập.
[Pilot DML mới](submission/days/20261011/dml_variance_pilot.md) dùng seeds mới và
adjusted OLS làm baseline ghép cặp cho day-jackknife t, không chạy lại các
phương pháp bootstrap cũ trên cohort này.
[Chẩn đoán score](submission/days/20261011/score_inference_diagnostic.md) mở rộng
cohort, đối chiếu covariance theo block/ngày, kiểm chứng elasticity/scenario
và độ nhạy folds. Các nghiên cứu này giữ nguyên mốc development.
[Báo cáo xử lý khoảng tin cậy](submission/days/20261011/week2_inference_closeout.md)
đã đối chiếu phương sai conditional OLS, hoàn tất assessment độc lập 400/400 fits
trên seeds 45001–45100 và chạy toàn bộ 410 tests. OLS HC3 khớp phương sai chuẩn;
day CR1 thiếu sai số chuẩn ở một số baseline. Assessment còn tám dòng cảnh báo
coverage riêng; không có rejection sau Holm không chứng nhận mọi CI đạt 95%.
Phương án A đã được chọn: analytic mặc định cho causal scenario/UI, bootstrap
giữ baseline đóng băng; [hướng dẫn dùng](USAGE.md#hybrid-choice-inference).
Calibration mọi đầu ra, full-context support và nghiệm thu GSM vẫn còn mở.
[Rà soát thống kê 07/10](submission/days/20261007/statistical_review.md)
giữ nguyên bằng chứng coverage; công việc còn lại nằm trong [ROADMAP.md](ROADMAP.md).
Kết quả hành vi/vận hành mô phỏng là evidence C; các kết luận GSM giữ trạng thái
theo dữ liệu và nhận diện tương ứng.

Week 3 bước 1 đã triển khai: `prepare-demand` đóng gói choice run đã kiểm tra
checksum, xuất request rates theo zone/block/service và snapshot fleet dùng chung.
Xem [lệnh chạy development](USAGE.md#week-3-demand-handoff). PoC sử dụng roster
online cố định và quyết định nhận/từ chối riêng từng offer; block-rate intervals
và calibration GSM vẫn chưa có.

Week 3 bước 2 đã triển khai: `simulate-marketplace` dùng fleet/thời gian hiện diện cố định,
request Poisson hoặc fixture CSV, xuất trajectories, trips hoàn thành, wait,
idle hours và end snapshot. Xem [hướng dẫn simulation](USAGE.md#week-3-fixed-supply-simulation).
Matching/OD/thời gian là giả định synthetic C; SOC giữ cố định. Phần state/carryover
và cancellation của bước 3 đã triển khai: chạy nối từ checkpoint busy/queued,
expiry theo pickup deadline và hủy trước pickup. Cơ chế trả công tối thiểu đã có
qua `--compensation`: tài xế nhận 100% giá cước hiển thị cho chuyến hoàn thành,
theo giả định Bun duyệt khi chưa có chính sách GSM. Giá cước/điều kiện trả công
được đóng băng riêng với sổ thu nhập; checkpoint giữ cùng contract và tránh trả
hai lần khi chạy nối. Xem [hướng dẫn trả công](USAGE.md#week-3-minimal-compensation).
[Bàn giao trả công 12/10](submission/days/20261012/week3_compensation_progress.md)
ghi 524 tests đạt, replay 18 đầu ra giống từng byte và chạy nối không thanh toán
trùng; đây là kiểm chứng tiền công theo giả định synthetic, chưa là hiệu ứng GSM.
Week 3 PoC hiện đã triển khai rules V3 trong `configs/week3_poc.json`: roster online
cố định, offer giữ xe ở trạng thái dispatch, nhận/từ chối/timeout/withdrawal với
seed ổn định và số lần thử hữu hạn. Mỗi cặp tài xế–request chỉ rút quyết định một
lần; từ chối không làm tài xế offline. Xác suất nhận 0,8 và thời gian phản hồi
3 giây là giả định synthetic độc lập với giá. Checkpoint giữ pending offers,
deadline gốc và terms trả công; CSV/Parquet có `driver_offers` và `offer_events`.
[Hướng dẫn PoC](USAGE.md#week-3-fixed-online-poc) thay thế immediate acceptance
trong đường chạy hiện hành; V1/V2 vẫn là các control lịch sử.

`evaluate-marketplace` đã triển khai so sánh baseline/price với paired seeds,
controlled truth và workload 2/20/100 tài xế theo
[protocol độc lập](BENCHMARK.md#week-3-fixed-online-operational-assessment).
Khoảng t cho trung bình Monte Carlo giữ demand fit và rules cố định; chưa phải
CI nhân quả hoặc full-chain. UI có màn hình **Simulation results**, selector riêng
và xuất CSV/JSON từ artifact hoàn thành đã kiểm checksum, không chạy simulator.
**Week 3 đã triển khai và kiểm chứng trong phạm vi PoC Bun chốt ngày 12/10/2026,
sẵn sàng để Bun đánh giá; chưa ghi nhận Bun nghiệm thu.**
[Báo cáo chốt kỹ thuật](submission/days/20261012/week3_poc_closeout.md) và
[bằng chứng đối soát](submission/days/20261012/week3_poc_verification.json) ghi
609 tests đạt (hai Pandas FutureWarnings lịch sử), assessment độc lập seeds
73001–73100 hoàn tất **303/303 jobs**, tất cả gate đạt trong 100,16 giây. Fixture
và Poisson replay khớp 22 đầu ra từng byte; chạy nối khi hai offers còn pending
khớp request/offer trace, ledger và checkpoint cuối. Các workload 2/20/100 tài xế
đã đo với khoảng 450 requests, không phải mức trần 10.000 requests; peak Python
allocation không phải process RSS. Lịch làm theo chính sách, ưu đãi,
online/offline động và equilibrium nằm ngoài PoC này.

Nguồn chạy hiện hành là `week3-poc-demand-baseline-20261012-v3` và
`week3-poc-demand-x-plus10-20261012-v3`. Run gốc
`week3-choice-development-v1` thiếu sáu file training-data đã đăng ký, nên kiểm
integrity run cũ không đạt. Đã giữ nguyên thư mục đó và đóng gói lại model/context
đã đóng băng, kiểm hash và giữ nguyên từng byte từ demand package hợp lệ, rồi chạy
lại gate `prepare-demand`; không refit hoặc phục hồi dữ liệu training. Không coi
training run cũ là đã replay nguyên vẹn. Hồ sơ chốt ghi rõ nguồn phục hồi và các
package đã đối chiếu SHA.

Nhánh khoa học cung lao động Week 3 đã triển khai độc lập với simulator:
`generate-supply`, `fit-supply`, `scenario-supply`, `evaluate-supply`. Giữ toàn bộ
nhóm đủ điều kiện, ước lượng hiệu ứng incentive lên participation/tổng giờ/giờ
phục vụ và CI theo tài xế; conditional hours chỉ mô tả. Oracle tách khỏi fitting,
support và benchmark RCT/null có protocol riêng. Xem
[contract và protocol cung](WEEK3_SUPPLY.md) cùng [hướng dẫn chạy](USAGE.md#week-3-controlled-labor-supply).
[Bàn giao cung 11/10](submission/days/20261011/week3_supply_progress.md) ghi
200/200 seed jobs RCT/null độc lập, coverage 95%-98%, báo động giả 2%-4% và
472 tests đạt; đây là kiểm chứng controlled riêng, chưa chứng nhận coverage tuyệt đối.
Nhánh này được giữ làm bằng chứng khoa học controlled, ngoài đường triển khai
PoC hiện tại; không dùng hiệu ứng incentive để thay đổi roster online.
Availability là giả định synthetic C, chưa là hệ số GSM. Nhận đơn khác với
tham gia/giờ lao động; PoC hiện đã kiểm chứng kỹ thuật và chờ Bun đánh giá,
chưa hoàn tất ba đáp ứng nhân quả của đề tài hoặc calibration GSM.

## Tài liệu đang dùng

| Tài liệu | Đọc khi cần |
|---|---|
| [USAGE.md](USAGE.md) | Cài đặt, CLI, profiles, exports, đọc status và repository checks |
| [ROADMAP.md](ROADMAP.md) | Đặc tả/điều kiện đóng tuần 1, yêu cầu theo tuần, chốt tuần 2 và định hướng tuần 3–5 |
| [GSM_DATA_CONTRACT.md](GSM_DATA_CONTRACT.md) | Request dữ liệu gửi GSM: nguồn, phạm vi, định dạng, khóa và đơn vị |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline, schema và trạng thái mapping/coverage, quy ước artifacts, ranh giới oracle và dashboard |
| [IDENTIFICATION.md](IDENTIFICATION.md) | Ba câu hỏi nhân quả, estimand/nhận diện, DGP demand/choice và giới hạn bằng chứng |
| [WEEK3_POC_SCOPE.md](WEEK3_POC_SCOPE.md) | Phạm vi PoC hiện hành: roster online cố định, nhận/từ chối đơn, trả công 100% giá cước, protocol và giới hạn nghiên cứu |
| [WEEK3_SUPPLY.md](WEEK3_SUPPLY.md) | Contract, phép đo và protocol controlled cung lao động; nhánh khoa học riêng ngoài phạm vi PoC hiện tại |
| [BENCHMARK.md](BENCHMARK.md) | Kế hoạch đánh giá theo estimand, quyết định kinh doanh còn chờ xác nhận và protocol/ngưỡng hiện có |

## Thiết kế và hồ sơ

| Nguồn | Mục đích |
|---|---|
| [Proposal](reference/GSM_Causal_Marketplace_Proposal.md) | Mục tiêu, phạm vi và lộ trình năm tuần |
| [Core engine design](reference/CORE_ENGINE_DESIGN.md) | Thiết kế thuật toán, supply, simulator và equilibrium; chưa phải trạng thái triển khai |
| [Submission](submission/README.md) | Báo cáo/PDF theo ngày; [chốt kỹ thuật Week 3 ngày 12/10](submission/days/20261012/week3_poc_closeout.md), nghiệm thu Week 2 và hồ sơ lịch sử được giữ nguyên |
| [Validation lịch sử](submission/days/20261003/validation.md) | Bằng chứng TLC/model/browser ngày 03/10 |

## Quy ước cập nhật

- Cập nhật tiến độ ở đây bằng tóm tắt và link đến bằng chứng có ngày chốt;
  kết luận nghiệm thu chi tiết nằm trong hồ sơ tương ứng.
- Giữ roadmap cho việc còn lại và yêu cầu đầu vào/đầu ra theo tuần; architecture
  và benchmark mô tả cấu trúc hoặc protocol, không lưu nhật ký tiến độ lặp lại.
- Schema/artifacts nằm trong architecture; phương pháp/evidence trong identification;
  metrics, ngưỡng và diễn giải kinh tế trong benchmark. Tài liệu tham chiếu trỏ
  về nguồn quản lý chính khi cần dùng các đặc tả này.
- Giữ `GSM_DATA_CONTRACT.md` ổn định cho request dữ liệu gửi GSM; chỉ sửa khi
  yêu cầu nguồn, trường dữ liệu, phạm vi hoặc quy cách bàn giao thay đổi.
  Yêu cầu đầu vào/đầu ra theo từng bước chỉ trao đổi trong chat, không ghi vào
  tài liệu hoặc file khác. Lệnh chạy nằm trong `USAGE.md`.
- Xóa kế hoạch/nhật ký đã hết vai trò sau khi gộp đặc tả hoặc lệnh còn cần
  vào tài liệu chính. Các link trỏ trực tiếp tới tài liệu đang dùng.
- Hồ sơ có bằng chứng nằm trong submission. Giữ nguyên kết quả số, source,
  checkpoint archive, audit và PDF lịch sử. Khi cập nhật README/metadata,
  ghi ngày/phạm vi cùng hash gốc trong manifest và tính lại checksum hiện hành.
- README gốc giữ mô tả dự án và cấu trúc code; hướng dẫn chạy và repository
  checks nằm trong [USAGE.md](USAGE.md).
