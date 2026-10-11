# Kiểm chứng bàn giao demand/choice — 11/10/2026

**Rà soát kỹ thuật ngày 11/10/2026, Asia/Bangkok. Bun đã nghiệm thu Week 2 với ngoại lệ kỹ thuật.**
[Hồ sơ quyết định và hybrid inference](week2_hybrid_acceptance.md); baseline lịch sử giữ nguyên.
Đây là bằng chứng bổ sung cho triển khai Week 2; báo cáo, số liệu và protocol
[07/10](../20261007/README.md) giữ nguyên. GSM chưa bàn giao dữ liệu.

## Thay đổi đã triển khai

`freeze-choice` đóng gói toàn bộ choice fit vào một run độc lập, không cần
snapshot fleet hay simulator. Gói giữ nguyên ba estimators `naive_ols`,
`adjusted_ols`, `dml`, model/bootstrap bundles, diagnostics, bootstrap records,
effects, splits, contexts, method metrics và scenario lịch sử. Manifest nguồn
được sao chép nguyên byte; cấu hình/môi trường huấn luyện tách khỏi môi trường
đóng gói. Gói có thể được dùng bởi scenario, dashboard và demand bridge.

`current_scenario_result.json` replay model/draws đã lưu với quy tắc hiện hành;
`choice_handoff.json` ghi scope, đơn vị, checksum, provenance, kết quả đối chiếu
và giới hạn. Không fit lại hoặc đọc oracle trong việc đóng gói/replay.
CLI từ chối ghi đè run không liên quan. JSON legacy theo vùng vẫn giữ đúng vùng;
consumer không được hạ ngưỡng support của cấu hình nguồn.

Effects/scenario mới ghi `interval_validation_scope=technical_checks_only` và
`interval_calibration_status=not_evaluated_for_this_run`. UI hiển thị interval
`ok` là **Technically stable**, tách khỏi support. Phương pháp percentile/day
bootstrap, công thức, bounds và schema joblib không đổi. Tệp lịch sử giữ nguyên.

## Bằng chứng của lượt đóng gói/replay

Các kiểm tra dưới đây thuộc lượt bàn giao ban đầu. Chẩn đoán tiếp theo cùng ngày
đã kiểm phạm vi thu hẹp và fresh development fit/bootstrap, được ghi riêng trong
[hồ sơ support và interval](support_interval_diagnostic.md).

| Mục | Kết quả đã kiểm chứng |
|---|---|
| Source model run | `20261003T130951-df24a7e4`; completed manifest và 31 artifact khớp checksum |
| Dataset | `ds-5f26297a9194afda2d39`, `semi_synthetic`, `RCT_SYN`, seed 42, evidence C |
| Bộ bàn giao | `week2-choice-handoff-20261011-v2`; 17 tệp nguồn được giữ nguyên, tổng 20 artifact đăng ký |
| Replay từ bộ bàn giao | `week2-choice-replay-20261011-v2`; toàn bộ JSON khớp current replay của gói sau khi bỏ riêng `run_id` |
| So với lịch sử | 12 nhóm trường point/interval/denominator/bootstrap khớp chính xác; trạng thái support thay đổi đúng theo kiểm tra hiện hành |
| Reuse | Lặp cả hai lệnh xác nhận `reuse verified artifacts`; mọi checksum của hai run vẫn khớp |
| Kiểm thử | 299 tests ngoài UI đạt trong 73,83 giây; 3 AppTest đạt trong 5,01 giây, tổng 302 tests |
| Kiểm tra mã/tài liệu | Ruff lint toàn bộ `src tests` và format các tệp thay đổi đạt; `ty 0.0.82 --error-on-warning` đạt; 217 link cục bộ và code fences trong 25 tệp Markdown hợp lệ |

Các tests mới kiểm tra source lỗi/incomplete trước khi load model, retry/repair
artifact đích, bảo toàn run nguồn và run không liên quan, tất cả estimators,
standalone replay khi không đọc được source run/dataset, legacy all/zone scope,
frozen support thresholds và package → demand bridge. UI kiểm tra DGP/seed,
scope, config nguồn, nominal interval và giá ngoài phạm vi.

AppTest bị chặn local loopback trong sandbox Windows; ba tests được chạy ngoài
sandbox sau khi auto-review chấp thuận. Các tests còn lại dùng thư mục tạm mới
trong workspace để tránh lỗi atomic replace ở TEMP sandbox. `ty` dùng Python
3.11 và cache/tool directory trong workspace; tải công cụ và kiểm tra ngoài
sandbox được auto-review chấp thuận vì sandbox không thấy các thư viện trong venv.
Không đổi thuật toán hoặc làm yếu kiểm tra để vượt các hạn chế môi trường này.

Format toàn repository còn hai lỗi xuống dòng **đã tồn tại ở HEAD**, tại
`src/gsm_poc/core/artifacts.py` và `src/gsm_poc/simulation/rules.py`; hai tệp không
được sửa trong lượt này. Không chạy browser thực, fresh fit/bootstrap, 500-job
reporting hay benchmark Swissmetro/policy mới. Saved-model replay kiểm chứng
inference từ bundle, không xác nhận tái huấn luyện toàn bộ bằng revision hiện tại.

## Identity và khả năng tái lập

| Identity | SHA-256 |
|---|---|
| Manifest nguồn, giữ nguyên | `d7fe2e29ca3d29a20e1131abfe158be83861a615ad5e169c6426e7d231cf8f70` |
| Manifest bộ bàn giao sau reuse | `35849460841ed2a542c3f9ae111508c40204aee0fc5f9f522ac2889c4aeff34f` |
| Manifest replay sau reuse | `0f002d72dce6938159a74db3762016b8f2daeef95e07634ba25fb7ade50b6bc9` |
| Code hiện hành dùng để đóng gói/replay | `1654258a72a6098d12fca3cb96314d67d43526c5d4ac548ff52d14234a2919f6` |
| Lock hiện hành | `ffdce4328395cbbb00ae98726e88c5386e4ef9fad4cbd69e291f6c1fb97ad154` |

[Bản đối chiếu JSON](choice_handoff_verification.json) lưu môi trường nguồn và
đóng gói, 20 artifact checksums, scope, lý do support và kết quả assertions.
Source training revision là `c2d24a277424e4523668eed8dd35e7135ae2e1a2`, code hash
`8af06450fdbbc7269ad493bc92743e830f5270516e1273ef26f182f1040a4e2e`.
Packaging HEAD là `89b3bbdca5de5c5053397f56b2c1ad6fa89cfa09` cộng thay đổi chưa
commit; code hash trên nhận diện đúng nội dung đã chạy. Python 3.11.9 và các
phiên bản package nằm trong JSON. Không gọi revision mới là revision huấn luyện.

Lệnh freeze/replay/reuse và cách đọc artifacts nằm ở
[USAGE](../../../USAGE.md#week-2-choice-handoff). Run artifacts nằm trong
`runs/<id>/`, được giữ ngoài version control. Replay cần repository/môi trường
tương thích và bộ bàn giao đã kiểm checksum; không cần TLC raw, oracle hoặc
source run/dataset gốc. Thay đổi code/environment phải dùng run ID mới.

## Kết luận gate hiện tại

| Gate | Kết luận và phạm vi |
|---|---|
| Data | Nền public/synthetic đã kiểm trong phạm vi Week 1; source/package checksums đạt. Mapping và coverage GSM vẫn chưa kiểm chứng. |
| Effect | Controlled point matrix được giữ và replay khớp; có independent block-method assessment 400/400 fits trên 100 seeds mỗi estimator/DGP. Chưa có causal GSM. |
| Scenario | **Đạt support cho phạm vi thu hẹp được công bố:** 10/20 nhóm training, giữ 67,5% trọng số phiên test. **Mở cho all-context:** support vẫn thiếu ở các nhóm bị loại. Không chuyển trạng thái của phạm vi thu hẹp sang toàn bộ thị trường. |
| Reproducibility | **Đạt cho đóng gói, saved-model replay và reuse**; 20 package artifacts kiểm được độc lập với dữ liệu gốc. Có thêm fresh development fit/bootstrap với protocol, raw draws và checksums; chưa chạy lại full 500-job final evaluation. |
| Statistics | **Technical exception accepted**, Bun, 11/10/2026. Independent cohort có Y/Y 97–98%, giữ cảnh báo cross-effect/scenario 88–89%. `Technically stable` không chứng nhận mọi CI đạt nominal 95%. Mốc 86/100 thuộc cohort lịch sử khác. |
| Additional benchmarks | Kết quả Swissmetro và 40/40 policy-value jobs là bằng chứng development lịch sử; không chạy lại hoặc nâng thành GSM business validation. |

Scenario hiện tại giữ scope năm zones, 1.440 test blocks, 72.000 quote sessions;
request giả định 10.000 sessions và tăng giá X 10%, Y không đổi. Baseline corner
`(1,1)` có 10 nhóm dưới ngưỡng 20; target `(1.1,1)` có 7 nhóm, thấp nhất 7 blocks.
Các số vẫn được lưu để đối chiếu, với `status=insufficient_support`; đây chưa phải
forecast được hỗ trợ cho toàn scope. Khoảng cách request/capacity và idle fleet
không được suy ra từ choice replay này.

Reviewer **Bun**, ngày nghiệm thu Week 2 **11/10/2026**, chấp nhận ngoại lệ
Statistics theo [hồ sơ hybrid](week2_hybrid_acceptance.md). Deadline chưa được cung cấp.
Phạm vi có support dưới ngưỡng đã đóng băng được xác định trong
[chẩn đoán mới](support_interval_diagnostic.md); toàn bộ bối cảnh vẫn cần thêm
training coverage và fit/kiểm chứng mới nếu muốn sử dụng. Calibration mọi output
và GSM còn mở. Nếu đổi phương pháp tiếp, phát triển
và đánh giá mới theo [protocol](../../../BENCHMARK.md), không tune trên final seeds
đã dùng. [Roadmap](../../../ROADMAP.md#1-close-week-2) giữ các điều kiện còn mở.
