# Bàn giao Week 3 — PoC với lượng tài xế online cố định

Ngày báo cáo: **12/10/2026**, múi giờ Asia/Bangkok.

**Đã hoàn tất triển khai và kiểm chứng kỹ thuật Week 3 trong phạm vi PoC Bun đã thống nhất.** Gói bàn giao đã được Bun nghiệm thu vào ngày **12/10/2026** (xem [nghiệm thu](week3_poc_acceptance.md)). Kết quả là bằng chứng synthetic cấp C, `not_calibrated`, chưa phải kết quả thực nghiệm GSM hoặc hoàn thành toàn bộ đề tài ban đầu.

## Mục tiêu và phạm vi đã hoàn thành

Chuyển dự báo nhu cầu X/Y từ bộ mô hình đã đóng băng thành diễn biến vận hành có thể kiểm tra: yêu cầu chuyến, đề nghị nhận đơn, quyết định tài xế, chuyến hoàn tất, chờ/hết hạn/hủy, thời gian rỗi và tiền trả tài xế. Simulator phục vụ kiểm chứng hệ quả của kịch bản giá với các giả định được khai báo.

- Giữ một danh sách tài xế/xe online trong toàn bộ khoảng quan sát, dùng chung cho X/Y. Tài xế đang bận hoặc chờ phản hồi đề nghị không nhận đồng thời chuyến khác.
- Tài xế quyết định từng đề nghị; từ chối vẫn online. PoC không phân ca, phân giờ hoặc mô hình hóa bật/tắt ứng dụng.
- Tài xế nhận **100% giá cước hiển thị khi chuyến hoàn tất**. Đề nghị, nhận đơn hoặc chuyến chưa hoàn tất chưa tạo khoản trả công.
- Không bổ sung ưu đãi, phản ứng giờ làm theo thu nhập, sạc xe hoặc bộ giải cân bằng cung–cầu. Đây là giới hạn phạm vi đã thống nhất.

Đặc tả hiện hành: [WEEK3_POC_SCOPE](../../../WEEK3_POC_SCOPE.md). Gói [cung lao động có kiểm soát](../../../WEEK3_SUPPLY.md) đã có trước được giữ riêng cùng bằng chứng của nó; không dùng để biến quyết định nhận đơn thành co giãn cung lao động trong PoC này.

## Hành vi và đầu ra

Rules V3 trong [week3_poc.json](../../../../configs/week3_poc.json) khai báo xác suất nhận từng đề nghị `0.8`, thời gian phản hồi 3 giây, timeout 10 giây, tối đa 20 đề nghị/yêu cầu và deadline đón khách 300 giây. Xác suất này độc lập với giá, là giả định synthetic; chưa ước lượng hành vi tài xế thực tế.

Mỗi cặp tài xế/yêu cầu chỉ có một quyết định ngẫu nhiên ổn định theo seed. Xe được giữ trong trạng thái `dispatch` khi đề nghị chưa giải quyết. Từ chối hoặc timeout giải phóng xe; hủy/hết hạn rút đề nghị và phản hồi muộn không thể tạo chuyến. Các khoản giá cước và trả công được đóng băng trước quyết định.

Đầu ra CSV/Parquet gồm `requests`, `request_events`, `vehicle_intervals`, `driver_offers`, `offer_events`, `quote_terms`, `driver_pay_terms`, `earnings_ledger`, `driver_income`. JSON lưu kết quả, đặc tả và checkpoint; manifest đăng ký checksum và môi trường. Có CLI chạy độc lập, đánh giá nhiều seed và giao diện chỉ đọc/xuất kết quả.

Các mẫu số được giữ rõ ràng:

- Tỷ lệ nhận đơn = accepted / (accepted + rejected + timed_out), tính theo phản hồi giải quyết trong cửa sổ hiện tại, kể cả đề nghị mang sang từ cửa sổ trước. Withdrawn và pending được báo riêng; không có phản hồi thì tỷ lệ unavailable.
- Online hours gồm idle, dispatch, pickup và on-trip; tài xế không có chuyến vẫn nằm trong thống kê thu nhập.
- Wait chỉ quan sát được ở yêu cầu đã đón khách. Các yêu cầu chưa được đón khi hết khoảng quan sát và các yêu cầu kết thúc trước đón được báo riêng.
- Tiền trả công là gross driver pay bằng `SYNTHETIC_UNIT`, chưa trừ chi phí; không diễn giải thành VND, thu nhập ròng, lợi nhuận hay ROI.

Checkpoint lưu đề nghị đang chờ, giữ xe, thời điểm phản hồi/timeout, số lần thử, deadline và điều khoản gốc. Chạy tiếp chỉ thanh toán chuyến hoàn tất trong cửa sổ mới. Đổi chế độ V3/legacy hoặc thêm/bỏ trả công cần run ID mới để tránh đọc nhầm đầu ra cũ; cache của cửa sổ legacy vẫn hoạt động.

## Kiểm chứng kỹ thuật

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ test suite | **609 passed**, 2 cảnh báo pandas đã có từ các script kiểm chứng Week 2; 203.87 giây |
| Ruff, format trên Python đã sửa, `ty` trên các module đã sửa | Đạt; không format toàn bộ repo |
| Đánh giá độc lập | **303/303 jobs thành công**, 0 thất bại; toàn bộ gate đóng băng đạt |
| Chạy lại cùng seed | Fixture và Poisson A/A: **22 đầu ra mỗi run giống từng byte** |
| Chạy tiếp qua checkpoint | 2 đề nghị pending qua mốc chia; request events, offer events, ledger và checkpoint cuối khớp chạy liên tục |
| Thanh toán và thời gian | Không trả công trùng, trả đúng 100% giá cước chuyến hoàn tất; cân bằng request/offer/state-time đạt |
| Cache và nguồn đầu vào | Cache được xác minh; 8 manifest nguồn được bảo vệ và kiểm tra checksum |
| UI | AppTest đọc artifact V3 thực tế, đúng metrics, 0 exception; mở trực tiếp run simulation không phụ thuộc việc tải artifact choice |
| CodeGraph | Đã sync sau thay đổi code |

Hai cảnh báo hiện có đến từ `scripts/compare_week2_variance.py:324` và `scripts/compare_week2_intervals.py:349`, về hành vi pandas khi nối bảng rỗng/all-NA. Không có test thất bại. UI được kiểm tra bằng Streamlit AppTest và bộ đọc artifact; chưa kiểm tra bố cục bằng trình duyệt trực quan.

Bằng chứng máy đọc: [week3_poc_verification.json](week3_poc_verification.json). Bảng từng lượt đánh giá: [paired seeds](week3_marketplace_seed_records.csv), [controlled mechanism](week3_marketplace_controlled_records.csv), [workloads](week3_marketplace_workload_records.csv).

## Đánh giá trên 100 seed

Run cuối: **`week3-poc-assessment-20261012-v3`**. Protocol [week3_poc_assessment.json](../../../../configs/week3_poc_assessment.json) dùng seed **73001–73100**, tách khỏi pilot **72001–72003**. 303 jobs gồm 200 quỹ đạo baseline/target ghép cặp, 100 quỹ đạo kiểm soát và 3 workload. Evaluator hoàn tất trong **100.16 giây**, dưới budget 600 giây.

Pilot 3 seed hoàn tất nhưng không đạt gate sai số trung bình của cơ chế kiểm soát: số chuyến trung bình 13.333 so với kỳ vọng 15. Pilot giữ nhãn `development_only`. Không đổi ngưỡng sau pilot hoặc dùng kết quả assessment để chỉnh ngưỡng. Các lần chạy lại cùng 100 seed phục vụ kiểm tra thay đổi giao diện/đóng gói, không được cộng thành các seed độc lập mới.

Cơ chế kiểm soát dùng một tài xế, 30 đề nghị tách rời trong 2 giờ, xác suất nhận 0.5, không chồng lấn chuyến. Đây là cấu hình có kỳ vọng tính trực tiếp, tách khỏi cơ chế forecast nhu cầu:

| Đại lượng | Kỳ vọng | Trung bình 100 seed | Gate |
|---|---:|---:|---|
| Yêu cầu / đề nghị | 30 / 30 | 30 / 30 | Đạt |
| Chuyến hoàn tất / accepted | 15 / 15 | 14.47 / 14.47 | Sai số tuyệt đối ≤ 1.2: đạt |
| Gross pay | 15 | 14.47 | Sai số tuyệt đối ≤ 1.2: đạt |
| Dispatch hours | 0.025 | 0.025 | Đạt |
| On-trip hours | 0.250 | 0.241167 | Sai số tuyệt đối ≤ 0.02: đạt |
| Idle hours | 1.725 | 1.733833 | Sai số tuyệt đối ≤ 0.02: đạt |
| Online hours | 2 | 2 | Đạt |

Kiểm tra số yêu cầu Poisson theo từng zone/service so với tích phân rate đóng băng cũng đạt. Kiểm tra A/A trong evaluator so từng metric ở từng cặp seed, không chỉ so trung bình gộp có thể triệt tiêu sai lệch.

## So sánh baseline và tăng giá X 10%

Hai input hiện hành là `week3-poc-demand-baseline-20261012-v3` và `week3-poc-demand-x-plus10-20261012-v3`. Cùng mô hình, nguồn, danh sách xe và khoảng quan sát; support gate đều đạt. Có 800 quote sessions trong 16 block, zones 161/162, khoảng quan sát 2 giờ. Expected requests từ plan: baseline **484.226731**, target **446.832670**.

Dưới đây là trung bình của 100 quỹ đạo, mỗi quỹ đạo có **2 tài xế online**:

| Metric | Baseline | X +10% | Chênh lệch target − baseline | Khoảng 95% của chênh lệch |
|---|---:|---:|---:|---|
| Yêu cầu X | 276.94 | 232.38 | −44.56 | [−45.929, −43.191] |
| Yêu cầu Y | 208.54 | 215.55 | +7.01 | [6.451, 7.569] |
| Tổng yêu cầu | 485.48 | 447.93 | −37.55 | [−39.083, −36.017] |
| Chuyến hoàn tất | 3.88 | 4.36 | +0.48 | [0.123, 0.837] |
| Mean wait ở các pickup, giây | 187.462 | 197.998 | +10.536 | [1.452, 19.620] |
| Idle vehicle-hours | 0.013839 | 0.015015 | +0.001176 | [0.000787, 0.001565] |
| Tỷ lệ nhận đề nghị | 0.804891 | 0.804770 | −0.000121 | [−0.009663, 0.009420] |
| Gross driver pay | 3.880 | 4.589 | +0.709 | [0.342, 1.076] |

Các khoảng trên là **Student-t Monte Carlo cho trung bình chênh lệch quỹ đạo ghép cặp, có điều kiện trên mô hình nhu cầu và rules cố định**. Chúng chưa truyền bất định từ bước ước lượng causal, không phải full-chain CI hoặc đồng thời cho mọi metric. Mean wait là trung bình các mean theo run trong nhóm đã pickup, không phải hiệu ứng causal trên toàn bộ khách hàng. CI block-rate và CI một quỹ đạo vẫn unavailable.

Hai tài xế bị giới hạn công suất mạnh so với khoảng 450–485 yêu cầu và deadline đón ngắn; phần lớn yêu cầu hết hạn, nhiều pickup bị ngắt trước khi đón. Không dùng thay đổi nhỏ của chuyến hoàn tất hoặc gross pay để khuyến nghị tăng giá cho GSM. X/Y vẫn là hai dịch vụ trừu tượng theo quyết định của Bun.

## Workload và giới hạn tài nguyên

Giữ demand target và seed 73001, mỗi workload tạo **452 yêu cầu** trong 2 giờ. Các lượt đo riêng có tracing bộ nhớ Python:

| Tài xế online | Wall time, giây | Peak Python allocation, MB thập phân | Work units | Kết quả |
|---|---:|---:|---:|---|
| 2 | 2.447 | 5.135 | 2,840 | Đạt |
| 20 | 5.068 | 8.797 | 4,880 | Đạt |
| 100 | 7.712 | 10.856 | 33,861 | Đạt |

Gate mỗi workload: 60 giây, 256 MiB peak Python allocation; workload cho phép tối đa 500,000 work units. `tracemalloc` không đo RSS/toàn bộ bộ nhớ native. Mức 10,000 requests là giới hạn cấu hình, **chưa được load test ở 10,000 yêu cầu**; số đo trên không chứng nhận năng lực production. Thời gian có thể đổi theo tải máy.

## Nguồn dữ liệu và khả năng tái lập

Run huấn luyện cũ `week3-choice-development-v1` không vượt kiểm tra integrity vì **6 file dữ liệu đã ghi trong manifest đang thiếu** tại `data/synthetic/ds-663bad10f5edf02dc497/`: ba file observed, hai file oracle và manifest dataset. SHA thực tế là null; chưa có bằng chứng rằng nội dung các file còn tồn tại bị thay đổi. Không tạo lại quan sát để che thiếu dữ liệu hoặc sửa manifest cũ cho thành hợp lệ.

Mô hình, context và các artifact choice đã đóng băng trong `week3-demand-baseline-v1/demand_bundle` vẫn được xác minh checksum. Chúng được đóng gói lại nguyên byte với provenance (`week3-choice-recovered-20261012-v2`, bản metadata UI hoàn chỉnh `v3`), **không refit**. Hai demand plan hiện hành được chuẩn bị mới từ bộ frozen v2 và vượt support gate. Bản v3 phục vụ khám phá choice trên UI; không đổi mô hình dùng cho assessment.

Cách này cho phép forecast có điều kiện và kiểm tra vận hành từ artifact mô hình hợp lệ; chưa tái lập được quá trình huấn luyện gốc. Gói proof ghi expected hash, tình trạng thiếu và hash các artifact sao chép. Dữ liệu nguồn, Week 2 handoff/hybrid và gói cung trước đó được giữ nguyên; thư mục `configs/data/` của Bun không bị thay đổi.

Mỗi run ghi Git revision `1b51eac493086989a18061ef6c1109c0e9cd8ae4` cùng hash source thực tế, vì workspace còn thay đổi chưa commit. Assessment có source hash `8abaaa5a2993a7e0d7c48332600f0f0309fe85945a2dbbf58655a81d51a0d182`, Python 3.11.9, lock hash, snapshot source, config, rules, compensation, protocol và nguồn demand. Raw runs/model/data nằm ngoài version control; báo cáo và ba CSV nhỏ được bàn giao trong repo.

## Cách đọc và chạy

Đọc báo cáo này trước, sau đó [proof](week3_poc_verification.json) và [USAGE](../../../USAGE.md#week-3-fixed-online-poc) nếu cần chi tiết interface. Artifact hiện có nằm trong `runs/<run_id>/`:

| Mục đích | Run đã kiểm chứng |
|---|---|
| Fixture | `week3-poc-fixture-20261012-v4` |
| Baseline / X +10% | `week3-poc-baseline-20261012-v3` / `week3-poc-x-plus10-20261012-v3` |
| Hai cửa sổ liên tiếp | `week3-poc-window-first-20261012-v3` / `week3-poc-window-second-20261012-v3` |
| Replay fixture / baseline | `week3-poc-fixture-replay-20261012-v3` / `week3-poc-baseline-replay-20261012-v3` |
| Pilot / assessment cuối | `week3-poc-pilot-20261012-v2` / `week3-poc-assessment-20261012-v3` |

Mở dashboard đã kiểm chứng từ thư mục repo:

```powershell
.venv/Scripts/python.exe -m streamlit run src/gsm_poc/ui/app.py -- --workspace . --run-id week3-poc-baseline-20261012-v3
```

Chạy một bản mới với ID mới, dùng đúng môi trường hiện có và frozen input đã xác minh:

```powershell
.venv/Scripts/python.exe -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-poc-demand-baseline-20261012-v3 --rules configs/week3_poc.json --compensation configs/week3_compensation.json --seed 42 --run-id week3-poc-review-baseline
.venv/Scripts/python.exe -m gsm_poc evaluate-marketplace --config configs/week3_demand.toml --baseline-demand-run-id week3-poc-demand-baseline-20261012-v3 --target-demand-run-id week3-poc-demand-x-plus10-20261012-v3 --rules configs/week3_poc.json --compensation configs/week3_compensation.json --protocol configs/week3_poc_assessment.json --run-id week3-poc-review-assessment
```

Giữ protocol và seed; không coi chạy lại là bằng chứng độc lập bổ sung. Trong workspace mới cần chuyển giao đầy đủ frozen artifacts có manifest hoặc chuẩn bị nguồn mới hợp lệ, không chỉ copy báo cáo/CSV.

## Giới hạn còn lại của đề tài

Week 3 PoC hiện hành đã triển khai đầy đủ theo phạm vi Bun duyệt. Chưa có dữ liệu GSM để calibration, kiểm chứng causal ngoài thực tế hoặc ước lượng phản ứng nhận đơn/online. Online roster cố định không chứng minh co giãn lao động bằng 0; xác suất nhận đơn giả định cũng không đại diện cho co giãn cung lao động. Các hạng mục lao động, cân bằng, experimental validation ngoài thực tế và ROI của problem statement gốc vẫn là mục tiêu nghiên cứu riêng, chưa được nghiệm thu bằng kết quả simulation này. Không commit hoặc push trong lượt bàn giao này.
