# So sánh phương pháp khoảng tin cậy — 11/10/2026

**Phạm vi:** development, dữ liệu semi-synthetic, evidence C; X/Y là hai dịch vụ
giả định. Chỉ so sánh bốn hệ số theta, đơn vị probability / log-price. GSM chưa
có dữ liệu. Nhánh này chưa chọn phương pháp production hoặc nghiệm thu coverage.

## Thiết kế đã đóng băng

[Study plan](results/interval_comparison/development_plan.json) được ghi trước
khi generate cohort mới. Seeds 42001–42020 dùng cho RCT_SYN và NULL_EFFECT với
adjusted OLS; DML có một probe RCT seed 42001. Mỗi job giữ 199 requested draws,
20 ngày train, context và cấu hình mô hình hiện tại. Không dùng lại hoặc tune
trên final seeds 20001–20100; không gộp cohort mới với các seeds chẩn đoán cũ.

| Phương pháp | Cách dựng khoảng | Vai trò |
|---|---|---|
| Percentile | Quantile 2,5% và 97,5% của cùng các draws | Baseline hiện tại |
| Basic | `[2 × point − q97,5; 2 × point − q2,5]` | Kiểm tra ảnh hưởng của centering; độ rộng bằng baseline |
| BCa | Bias correction từ midrank draws và acceleration từ jackknife theo ngày | Ứng viên development |

BCa bỏ lần lượt từng **original training day**, rồi refit toàn bộ thành phần
học được trên 19 ngày còn lại, cùng seed. DML tính lại nuisance và grouped folds.
Không dùng oracle để fit hoặc dựng khoảng. Điểm ước lượng được đối chiếu với
diagnostic gốc trước khi so sánh; các phương pháp dùng cùng point và raw draws.

Công thức tham chiếu theo [SciPy 1.17 bootstrap](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats.bootstrap.html)
và [R boot.ci](https://stat.ethz.ch/R-manual/R-devel/library/boot/html/boot.ci.html).
BCa không khả dụng khi jackknife lỗi/thiếu, variance bằng không, bias correction
vô hạn hoặc mapping không hợp lệ. Quantile hiệu chỉnh phải nằm trong
`[1/(B+1), B/(B+1)]`; guard được chốt trước so sánh, không clip hoặc fallback
để tạo một khoảng trông hợp lệ. Counts, lý do và các khoảng không khả dụng
vẫn có trong kết quả.

## Kết quả thực thi

| Nhóm chạy | Jobs hoàn tất | Bootstrap refits | Jackknife refits | Wall time fit/bootstrap / comparison |
|---|---:|---:|---:|---:|
| Adjusted OLS, RCT + NULL, 20 seeds mỗi DGP | 40/40 | 7.960/7.960 | 800/800 | 593,46 / 67,32 giây |
| DML, RCT seed 42001 | 1/1 | 199/199 | 20/20 | 573,09 / 60,51 giây |

Các nhóm chạy song song; không cộng các wall time thành elapsed tổng. Không có
lỗi fit, bootstrap hoặc jackknife. Cả 164 khoảng BCa của hai nhóm đều khả dụng;
không có trường hợp dùng fallback hoặc bị bỏ khỏi mẫu số. Một seed DML chỉ
kiểm chứng execution, không đo được coverage giữa seeds.

| RCT adjusted OLS, n=20 mỗi ô | Percentile | Basic | BCa |
|---|---:|---:|---:|
| X/X chứa truth | 18/20 | 17/20 | 19/20 |
| X/Y chứa truth | 19/20 | 19/20 | 19/20 |
| Y/X chứa truth | 20/20 | 20/20 | 20/20 |
| **Y/Y chứa truth** | **17/20** | **17/20** | **18/20** |
| Y/Y độ rộng trung bình | 0,039730 | 0,039730 | 0,040170 |
| Y/Y mean paired width ratio so với baseline | 1,0000 | 1,0000 | 1,0103 |

BCa Y/Y có **một coverage gain, không có loss**, trên cùng 20 seeds. Exact
binomial 95% interval cho coverage 17/20 là **[62,11%; 96,79%]**, cho 18/20 là
**[68,30%; 98,77%]**. Chênh lệch một seed không đủ xác nhận cải thiện calibration.
Basic có cùng độ rộng với percentile theo công thức; không tự sửa variance
underestimate. BCa chỉ là ứng viên, không được chọn làm mặc định từ bảng này.

| NULL adjusted OLS, false positives / 20 | Percentile | Basic | BCa |
|---|---:|---:|---:|
| X/X | 2/20 | 3/20 | 2/20 |
| X/Y | 1/20 | 1/20 | 1/20 |
| Y/X | 1/20 | 0/20 | 2/20 |
| **Y/Y** | **3/20** | **3/20** | **3/20** |

False positives Y/Y vẫn là 15% trong mẫu, exact binomial 95% interval
**[3,21%; 37,89%]**. Mẫu này chưa xác nhận kiểm soát false positives ở 5%.
Không gộp với diagnostic seeds 41001–41020 hoặc final seeds cũ để tăng mẫu số.

Số đo từng seed/method, các cohort pairing, bounds và lý do unavailable nằm trong
[development summary](results/interval_comparison/development/summary.csv),
[seed metrics](results/interval_comparison/development/seed_metrics.csv),
[jackknife](results/interval_comparison/development/jackknife.csv) và
[DML probe](results/interval_comparison/dml_probe/).

## Kiểm chứng và tái lập

Nhánh chạy qua `scripts.compare_week2_intervals`, đọc diagnostic đã hoàn tất và
kiểm toàn bộ registered checksums trước khi load bảng. Protocol so sánh được
đóng băng trước compute; kết quả dùng output directory mới và từ chối ghi đè.
Source context/config/environment, dataset identities và source code hash được
đối chiếu; point refit khớp trước khi chạy jackknife. Cả baseline bounds, điểm
và coverage/false-positive flags giữ nguyên chính xác so với diagnostic nguồn.

- **119 kiểm thử liên quan đạt**, gồm kiểm công thức BCa với `scipy.stats.bootstrap`,
  basic reflection, degenerate/tail cases, failures, pairing, nguồn bị sửa và
  tích hợp reconstruction/refit trên fixture.
- Ruff lint, format hai tệp script/test mới và `ty 0.0.82 --error-on-warning` đạt.
  Không format toàn repository.
- Kiểm lại hashes mọi artifact, 8.159 raw bootstrap draws, 820 jackknife refits,
  basic bounds và BCa bias/acceleration/quantiles đều đạt; bytes nguồn không đổi.

[Đối chiếu JSON](interval_method_comparison.json) ghi identities và assertions;
[checksums hồ sơ](results/interval_comparison/evidence_checksums.json) bảo vệ
study plan, protocol/status/summary, bảng metrics/jackknife và source snapshots.
Code hash của phương pháp hiện hành vẫn là
`1654258a72a6098d12fca3cb96314d67d43526c5d4ac548ff52d14234a2919f6`;
comparison controller SHA-256 là
`9a94fd2bd5bf07c677a6c4d169761060bd778e0ad401a40d1b7ca2fecbf2a9e3`.
Code/config/lock/package versions và hashes nằm trong protocol đã xuất bản.
Raw bootstrap draws và context nằm trong `.cache/week2-ci-comparison-*` theo
source manifests, không đưa vào Git; summaries/metrics không thay thế chúng
cho việc chạy lại toàn bộ. Hồ sơ 07/10 và chẩn đoán 41001–41020 giữ nguyên.

## Diễn giải và phần còn mở

Coverage và false positives phải đọc cùng expected/attempted/available counts,
exact binomial uncertainty và so sánh trên common-valid seeds. Không coi một
khoảng không khả dụng là thành công hoặc chọn phương pháp chỉ theo nhóm còn
tính được khoảng. Nhãn kỹ thuật không xác nhận calibration thực nghiệm.

BCa không bảo đảm sửa được variance underestimate; chỉ là một ứng viên kiểm
chứng. Hai mươi clusters theo calendar/context cố định không phải mẫu IID ngày
GSM. DML thay đổi folds khi bỏ ngày; một probe không đo được coverage quần thể.
Kết quả theta không chuyển thành xác nhận cho khoảng elasticity hoặc scenario.

**Nhánh thử nghiệm đã triển khai và chạy hoàn tất; chưa đủ bằng chứng chọn
BCa để xử lý calibration.** Cần tiếp tục development đối với variance/inference,
giữ phép so sánh ghép cặp và mẫu số lỗi. Phương pháp production, ngưỡng support
và các gói choice cũ giữ nguyên. Chỉ sau khi chốt phương pháp cùng tiêu chí mới
chạy final evaluation bằng seeds độc lập.
Statistics gate và nghiệm thu Week 2 vẫn mở. Lệnh chạy và cách đọc đầu ra nằm
trong [USAGE](../../../USAGE.md#development-interval-method-comparison).
