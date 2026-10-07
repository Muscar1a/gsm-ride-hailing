# Rà soát nghiệm thu Week 2 — 07/10/2026

**Mốc bằng chứng: 10:41:19, Asia/Bangkok (UTC+07).**

Tài liệu đối chiếu nội bộ của [báo cáo PoC](weekly_report.md) và
[bản tiến độ](progress_update.md). Đây là rà soát kỹ thuật, chưa phải xác nhận
của người nghiệm thu. **Week 2 đạt một phần; chưa đóng đầy đủ.**

| Gate | Kết luận tại mốc chốt | Bằng chứng / phần còn lại |
|---|---|---|
| Data | Đạt kỹ thuật trong phạm vi public/synthetic | TLC đối soát và train-only context; Swissmetro schema/units/person holdout/checksums. EPFL nêu dùng nghiên cứu/giáo dục; giữ giới hạn tái phân phối/thương mại |
| Effect | Đạt development; chờ reporting đầy đủ | Recovery các run đã nêu và RCT tạm; các DGP khác chưa có kết quả reporting. Không coi nhiễu ẩn là được nhận dạng |
| Scenario | Đã kiểm chứng run lịch sử; chờ chốt bundle cuối | Run `20261003T130951-df24a7e4`, support/probability/199-draw checks; không gán nguồn code cũ cho run mới |
| Reproducibility | Đạt đối chiếu hiện có; chờ bộ bàn giao cuối | Snapshot nguyên trạng; checksum 69 checkpoints, 13 batch manifests, 205 policy artifacts, 5 Swissmetro closeout artifacts và 31 artifacts của model lịch sử. Policy/Swissmetro dùng lại outputs đã xác minh |
| Statistics | Chờ; có dấu hiệu coverage thấp | Chưa đủ 100 seeds × 5 DGP; NULL_EFFECT chưa chạy. RMSE RCT tạm đạt, coverage chưa đủ căn cứ nghiệm thu |
| Additional benchmarks | Đạt phạm vi development đã định | Swissmetro và policy-value 40/40 seed jobs; evaluator test độc lập, uplift âm/ties/fallbacks được giữ; không phải GSM revenue |

Nguồn provenance: [EPFL/Biogeme, mục Data](https://biogeme.epfl.ch/) công bố
Swissmetro trong nhóm dữ liệu dùng cho nghiên cứu/giáo dục. Nguồn này bổ sung
cho source manifest; không sửa manifest cũ hoặc suy ra quyền thương mại/tái phân phối.

## Coverage và mẫu số

**69/500 jobs** thành công, **1 đang chạy** (job 70, RCT seed 20070),
**0 thất bại**, **430 chưa bắt đầu**. Chỉ RCT đã bắt đầu; reporting seeds
20001–20100, probe 19001 bị loại. 69 successful checkpoints có 828 coefficient
rows, 207 fits, mỗi fit 199/199 draws; tổng 41.193 refits. Runtime trung bình
516,41 giây/job. Mọi con số là snapshot tại mốc chốt.

Bảng chính thức của 13 batches gồm **65 RCT seeds**, 780 coefficient rows,
195 fits/38.805 refits; bốn successful seeds của batch đang chạy chưa vào pool.
Không cộng số draws lặp lại trên bốn ô hệ số thành bốn lần số refits.

Bảng dưới lấy trực tiếp pooled metrics đã kiểm tra checksum. Mỗi dòng có
**65/100 seeds yêu cầu**, 65 estimates/intervals hợp lệ, 0 fit/interval failure;
12.935 requested/successful draws **của estimator**. Bias/RMSE có đơn vị
probability/log-price; coverage là individual 95% interval coverage.

| Estimator | Outcome/price | Bias | RMSE | Coverage | Binomial 95% |
|---|---|---:|---:|---:|---|
| adjusted_ols | X/X | 0,000377 | 0,011222 | 86,15% | [75,34%; 93,47%] |
| adjusted_ols | X/Y | -0,000227 | 0,011385 | 93,85% | [84,99%; 98,30%] |
| adjusted_ols | Y/X | 0,001338 | 0,009942 | 93,85% | [84,99%; 98,30%] |
| adjusted_ols | Y/Y | 0,000591 | 0,011551 | 86,15% | [75,34%; 93,47%] |
| dml | X/X | 0,000118 | 0,011470 | 87,69% | [77,18%; 94,53%] |
| dml | X/Y | -0,000551 | 0,011807 | 93,85% | [84,99%; 98,30%] |
| dml | Y/X | 0,001531 | 0,010224 | 93,85% | [84,99%; 98,30%] |
| dml | Y/Y | 0,001139 | 0,011647 | 86,15% | [75,34%; 93,47%] |
| naive_ols | X/X | 0,000265 | 0,013108 | 87,69% | [77,18%; 94,53%] |
| naive_ols | X/Y | 0,000275 | 0,012186 | 93,85% | [84,99%; 98,30%] |
| naive_ols | Y/X | 0,001148 | 0,010824 | 96,92% | [89,32%; 99,63%] |
| naive_ols | Y/Y | 0,001014 | 0,011632 | 90,77% | [80,98%; 96,54%] |

Các khoảng binomial trên là mô tả theo ô, chưa hiệu chỉnh việc xem tiến độ
lặp lại/đa so sánh. Y/Y của adjusted OLS và DML có 56/65 coverage; khoảng
[75,34%; 93,47%] chưa chứa nominal 95%. Không đổi phương pháp/seeds để đạt
gate sau khi thấy kết quả tạm. Null false positives **N/A**, denominator 0;
không xem là tỷ lệ 0. Các DGP chưa chạy chưa có bias/RMSE/coverage reporting.

## Policy-value và tái lập

Run `week2-policy-final-32001-32020`: 40 seed jobs, 240/240 valid values, 120 fits, 0 learning
failure, 0 test rejection. Simple rule fallback ở 7 observed seeds, giữ trong
mẫu số; status `complete_with_fallbacks`. Runtime evaluator (gồm fit/select
và ghi outputs) **191,50 giây**;
stage tổng **195,03 giây**.

Hai lượt cùng protocol cho kết quả hành vi/value/action trùng nhau; khác biệt
mã giữa hai lượt là khai báo kiểu và metadata lỗi, không tuning. Bản cuối
được dùng lại sau checksum verification. Swissmetro closeout chạy lại cho
metrics và predictions trùng run `week2-swissmetro-final-31001`, rồi dùng lại
outputs thành công. Hai run cuối có cùng source hash; coverage snapshot riêng.

**131 tests passed, 40,95 giây**; Ruff check/format đạt (36 files), ty 0.0.82
đạt toàn bộ `src/gsm_poc` với `--error-on-warning`. Browser QA là bằng chứng
lịch sử; chưa kiểm tra lại browser/CI từ xa trong đợt này. Không thêm dependency.

## Nguồn đóng băng và checksum

Các đường dẫn tính từ repo root; dữ liệu lớn/run artifacts nằm trong thư mục
ignored. Các hash dưới định danh bằng chứng, không đồng nhất các phiên bản mã.

| Bằng chứng | SHA-256 |
|---|---|
| Bản đối chiếu `.cache/submission-20261007-results-034119.json` | `ad2cf2d58479dfdd5b1d6d6f09a1f957423dfc5f2a2d542bc62f21de745a21d4` |
| Coverage frozen spec | `8fda615108bc06365320bdbf41fa5ded3e19423630efd360a6767c2c61e61af1` |
| Pooled seed_metrics.parquet (65 seeds) | `e0b916e51b0f0ef8d07fce976e1d533fefa554bfacda9abf5f4eab6dfe417132` |
| Pooled evaluation_metrics.csv | `68125acf4666680591e0d2c055ebb2090f0fd7387b8e8feaf6c71c85ca2fa5ad` |
| Coverage source | `8459df189c1da3d4252f1ac2445854ac684c4ee15cecf951d80cbfd5402648a0` |
| Policy/Swissmetro closeout source | `68a7a1b7bf19ec6eb2dff47ecb90a0c429c5c34e724232c371c9b3b0535661f3` |
| Lock | `e619cacb8a04c36d2970a268d8ebbb983f0c1c31dc66a6c918331bd7691b6b1c` |
| Policy manifest `runs/week2-policy-final-32001-32020/manifest.json` | `ce9c99bbeecc8ff1fec175daae53311f022c2f6a695c64d1b9bd238f57e614cc` |
| Swissmetro manifest `runs/week2-swissmetro-closeout-31001/manifest.json` | `95c13b8941da5a9b527ee8e893f2d8327d10b23998350beffcc50a4b0e6903b7` |

Revision nền `574cf501304a777827c2e04704d96a1ab563e1b2`; các module policy/
Swissmetro có thay đổi chưa commit, nhận diện bằng source hash riêng. Audit
giữ từng checkpoint/hash, summary đúng mẫu số và kiểm tra bytes context/lock/
source/runner. CSV kèm audit giữ pooled metrics đúng mốc, kể cả khi runner cập nhật.

## Điều kiện còn lại để đóng Week 2

1. Đủ giao thức 500 jobs; pool per-seed rows với khóa/denominator/hashes hợp lệ.
2. Rà soát bias/RMSE, coverage/null/binomial intervals và draw failures >5%;
   giữ hidden-confounding/collinear stress cases và không tự coi completion là pass.
3. Chốt bộ demand/choice bàn giao và exports tương thích với manifest/config/
   scope/code; kiểm tra rerun/resume tương ứng. Model lịch sử đã xác minh là
   bằng chứng riêng, chưa gọi là bộ bàn giao mới.
4. Cập nhật hai báo cáo cùng mốc cuối, ghi người kiểm tra/ngày/kết luận hoặc
   ngoại lệ thực tế. Các trường này hiện **chưa xác nhận**; hạn nộp thực tế
   cũng chưa được cung cấp.

Tối ưu compute tiếp tục ở chat riêng. Các kết luận hiện chỉ áp dụng public/
synthetic, evidence C; mô hình cung, simulator và thử nghiệm/ROI GSM thuộc bước sau.
