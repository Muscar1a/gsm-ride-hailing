# Week 2 — Nghiệm thu ngoại lệ kỹ thuật và inference kép

**Reviewer: Bun. Ngày: 11/10/2026, Asia/Bangkok.** Quyết định trực tiếp trong
phiên làm việc: **Technical exception accepted**, chọn phương án A.

Week 2 được nghiệm thu trong phạm vi controlled evidence C với các giới hạn dưới
đây. Giữ nhãn **`Technically stable`**; không đổi thành calibrated. Ngoại lệ
không đóng gate support toàn thị trường hoặc xác nhận hiệu ứng GSM.

## Bằng chứng và phạm vi chấp nhận

[Báo cáo kiểm chứng](week2_inference_closeout.md) và raw artifacts giữ nguyên:
400/400 fits, 100 seeds độc lập mỗi estimator/DGP trên 45001–45100. Cohort này
đã sử dụng để đánh giá, không dùng lại để chọn phương pháp hoặc điều chỉnh CI.

- OLS HC3 được đối chiếu với phương sai chính xác có điều kiện trong DGP tuyến
  tính; RMS SE/reference 0.999627–1.003511. DML dùng orthogonal score và kiểm
  chứng số; chưa có kiểm chứng exact finite-sample variance tương tự.
- Phát biểu nghiệm thu của Bun là coverage 88%–98%. Đọc theo output/DGP:
  theta RCT DML 89%–98%, scenario RCT DML 88%–98%; toàn bộ scenario OLS/DML,
  RCT/null có range **88%–100%**. Không gộp các ô thành một coverage chung.
- Giữ cảnh báo **88%–89%** cho một số hiệu ứng chéo và scenario. Có 8 dòng
  cảnh báo exploratory; 0/168 Holm rejections không chứng nhận coverage 95%.
- Y/Y đạt 97%–98% ở cohort mới. Mốc 86% thuộc cohort lịch sử khác; không ghi
  đây là cải thiện ghép cặp do đổi phương pháp.
- CI là individual. Analytic conditional CI giả định independent block scores;
  DML giữ nuisance cố định trong xấp xỉ score. Không suy rộng sang phụ thuộc
  thị trường/GSM hoặc xem đây là CI đồng thời.
- Support giữ ngưỡng 20 blocks: scope thu hẹp lịch sử 10/20 strata, 67,5%
  trọng số phiên đủ support; full-context vẫn `insufficient_support`.

## Triển khai phương án A

| Thành phần | Hành vi |
|---|---|
| Point fit | Lưu covariance chung của theta và mọi hệ số baseline; OLS HC3/t hoặc DML block-score/normal. Dùng observed train và residuals DML OOF, không đọc oracle. Không tính phần này cho bootstrap refits. |
| Causal `scenario()` | `inference_method="analytic"` mặc định, hoặc `"bootstrap"`. Delta method elasticity gồm baseline uncertainty và covariance chéo; hỗ trợ zone, trọng số phiên, giá baseline khác 1 và treatment xác định. |
| UI / CLI scenario | Analytic mặc định, Bootstrap tùy chọn. Analytic không deserialize `bootstrap_bundles.joblib`; giữ nhãn và cảnh báo coverage. |
| Frozen baseline | `freeze-choice` replay bootstrap tường minh. `Pipeline.scenario()` mặc định bootstrap cho caller batch cũ (`fit`, `run-all`); caller mới truyền analytic. |
| Model cũ | `prepare-inference` tạo run riêng từ freeze-choice, sao chép baseline nguyên byte và thêm `analytic_inference.json`. Xác minh hash observed/metadata với fit input hash cũ; refit tối đa một lần mỗi estimator đủ điều kiện, đối chiếu các hệ số điểm. Không tạo lại bootstrap hoặc sửa package gốc. |
| `prepare-demand` | Contract point request-rate và trạng thái rate CI unavailable giữ nguyên; covariance tùy chọn được giữ trong bundle. Bridge không nạp bootstrap để tính rates. |

Covariance thiếu có `interval_unavailable`, vẫn giữ điểm hợp lệ; covariance sai
hoặc stale bị từ chối. Không tự chuyển sang bootstrap, clipping hoặc nới support.
Naive OLS vẫn dùng bootstrap; analytic chưa được qualification cho estimator đó.

Manifest cũ chỉ ghi observed hash trong fit được kiểm bằng đúng fingerprint đó,
cộng metadata hash đã đăng ký ở generate; không bỏ kiểm metadata để cho qua.
Model cũ cần observed training data cho bước chuẩn bị duy nhất. Sau đó analytic
chỉ cần point bundle, covariance gọn và contexts. Manifest vẫn kiểm hash mọi
artifact khi mở run: integrity scan ban đầu có thể đọc bootstrap bytes để kiểm
checksum dù không deserialize draws. Lệnh dùng ở [USAGE](../../../USAGE.md#hybrid-choice-inference).
Nghiên cứu lịch sử phải chạy với snapshot source và engine đã ghi.

## Kiểm chứng tích hợp

Đối chiếu covariance và CI với frozen score kernel cho OLS/DML, toàn scope và
zone với session weights khác nhau; kiểm tra gradient elasticity khi baseline
khác 1, covariance thiếu/stale, nạp bootstrap theo selector, package cũ nguyên
byte, replay điểm và từ chối dữ liệu nguồn bị đổi; kiểm tra treatment chỉ xác
định một cột và threshold elasticity. Có regression kiểm `prepare-demand`:
schema, rates, summary, reasons và trạng thái CI giữ nguyên; chỉ các ID/version
lineage thay đổi theo package mới. UI kiểm cả mặc định analytic và chọn bootstrap.

- **423 tests đạt**, 2 Pandas FutureWarnings đã có từ controller nghiên cứu
  lịch sử; 134,59 giây. Ruff src/tests và ty cho 9 file nguồn thay đổi đạt.
  CodeGraph đã sync; kiểm local links và diff whitespace đạt.
- Run thực tế: `week2-hybrid-inference-20261011-v3`, từ baseline
  `week2-choice-handoff-20261011-v2`. Hai covariance OLS/DML được chuẩn bị trong
  **5,51 giây**, thêm khoảng **40 KB/estimator**. Hash của 20 artifacts baseline
  giữ nguyên; refitted coefficients khớp. Bootstrap point và cả ba nhóm CI replay
  khớp bản đã lưu. Analytic point replay khớp cả full và restricted scope.
- Benchmark nhỏ: **5 warm scenarios/method**, cùng model DML, 1.440 contexts,
  native threads=1, không tính I/O/refit trong timer. Median analytic
  **0,03048 giây**, bootstrap **1,12195 giây**, khoảng 37 lần trong trường hợp
  này. Nạp bootstrap riêng mất 0,415 giây; file nén thực tế 1,87 MB. Không đo
  RAM peak hoặc suy ra mức tăng tốc cho simulation toàn thị trường.
- Full-context vẫn `insufficient_support`. Scope training-supported đã công bố
  giữ 972 blocks/48.600 sessions và có support `ok`, CI technically stable.
- Kiểm hash độc lập **784 file** trong 7 archive nghiên cứu trước đây: tất cả
  giữ nguyên. Không rerun/tune benchmark 100 seeds hoặc thay raw measurements.

[Machine-readable verification](../../../../artifacts/research/20261011/week2_hybrid_verification.json) ghi source/lock
hashes, môi trường, scope, file sizes và cả 5 timings mỗi method. CLI smoke run
`week2-hybrid-scenario-20261011-v3` mặc định analytic, chỉ deserialize point model;
interval status `ok`, full-context support vẫn không đủ.

## Việc còn mở

GSM chưa có data; business confirmation, real calibration và causal GSM chưa
đánh giá. Full-context cần thêm training support và fit/validation mới. Week 3
tiếp tục trên scope hỗ trợ và evidence C đã công bố. Calibration đúng nominal
cho mọi output chưa được chứng nhận; thay đổi phương pháp tiếp theo cần protocol
và cohort mới, tách khỏi seeds đánh giá đã dùng.
