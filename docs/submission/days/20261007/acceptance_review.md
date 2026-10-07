# Rà soát nghiệm thu Week 2 — 07/10/2026

**Mốc dữ liệu cuối: 17:13:28 ngày 07/10/2026, Asia/Bangkok (UTC+07).**
Rà soát thống kê ngày 07/10; thời điểm chi tiết lưu trong audit JSON.

Tài liệu đối chiếu nội bộ của [báo cáo PoC](weekly_report.md) và
[bản tiến độ](progress_update.md). Đây là rà soát kỹ thuật, chưa phải xác nhận
của người nghiệm thu. **Week 2 đạt một phần; chưa đóng đầy đủ.**

| Gate | Kết luận tại mốc chốt | Bằng chứng / phần còn lại |
|---|---|---|
| Data | Đạt kỹ thuật trong phạm vi public/synthetic | TLC đối soát và train-only context; Swissmetro schema/units/person holdout/checksums. EPFL nêu dùng nghiên cứu/giáo dục; giữ giới hạn tái phân phối/thương mại |
| Effect | RCT point accuracy đạt; recovery observed đã có kết quả reporting | Đủ 100 seed/DGP; giữ hidden-confounding bias và 300 collinear rejections. Không coi nhiễu ẩn là được nhận dạng |
| Scenario | Đã kiểm chứng run lịch sử; chờ chốt bundle cuối | Run `20261003T130951-df24a7e4`, support/probability/199-draw checks; không gán nguồn code cũ cho run mới |
| Reproducibility | Reporting đã đối chiếu; chờ bộ demand/choice bàn giao cuối | 500 checkpoint hashes/rows khớp pool, 60 summary cells tính lại khớp; snapshot nguyên trạng. Policy/Swissmetro và model lịch sử giữ bằng chứng riêng |
| Statistics | Rà soát hoàn tất; chưa nghiệm thu calibration vô điều kiện | RCT Y/Y adjusted OLS/DML coverage 86/100, binomial 95% [77,63%; 92,13%]; NULL_EFFECT 5–8% theo ô. Draw failures 0/238.800 |
| Additional benchmarks | Đạt phạm vi development đã định | Swissmetro và policy-value 40/40 seed jobs; evaluator test độc lập, uplift âm/ties/fallbacks được giữ; không phải GSM revenue |

Nguồn provenance: [EPFL/Biogeme, mục Data](https://biogeme.epfl.ch/) công bố
Swissmetro trong nhóm dữ liệu dùng cho nghiên cứu/giáo dục. Nguồn này bổ sung
cho source manifest; không sửa manifest cũ hoặc suy ra quyền thương mại/tái phân phối.

## Thống kê cuối và mẫu số

**500/500 jobs** thành công, **0 lỗi cuối**, **0 còn lại**, **100/100 batches**;
100 seed mỗi DGP. Reporting seeds 20001–20100, loại probe 19001. Có **6.000
coefficient rows**, **1.200 fits được nhận dạng**, mỗi fit 199/199 draws; tổng
**238.800 refits**, 0 thất bại. **300 fits collinear bị từ chối** giữ trong mẫu
số và 1.200 rows N/A; không tính thành lỗi compute. Invalid baseline draws và
invalid scenarios ở fits hợp lệ đều bằng 0.

Đã xác minh 13 hashes của bản lưu, 500 checkpoint JSON/parquet và toàn bộ rows;
tính lại bias/RMSE/coverage/null/binomial intervals của 60 ô khớp bảng tổng hợp.
Không cộng draws lặp trên bốn coefficient rows thành bốn lần số refits.

| RCT estimator | Max theta RMSE | Scenario RMSE | Coverage theo ô |
|---|---:|---:|---:|
| naive_ols | 0,012475 | 0,003637 | 90–96% |
| adjusted_ols | 0,012603 | 0,003591 | 86–95% |
| dml | 0,012680 | 0,003602 | 86–94% |

Point accuracy RCT đạt ngưỡng 0,10/0,02. Y/Y adjusted OLS và DML có **86/100**
coverage, Clopper–Pearson hai phía 95% **[77,63%; 92,13%]**. Chẩn đoán hậu kiểm
binomial một phía/Holm trên 36 ô RCT/observed/null cho p hiệu chỉnh **0,014825**;
đây không phải acceptance rule đăng ký trước hoặc hiệu chỉnh theo dõi tiến độ.
Coverage của khoảng 95% còn hạn chế; không đổi phương pháp/seeds để nâng kết quả.

NULL_EFFECT false positives **5–8/100 theo ô**; các khoảng exact binomial 95%
đều chứa mức 5%, chưa chứng minh tương đương 5%. Hidden confounding giữ bias
và coverage thấp, không nhận dạng nhân quả; collinear từ chối đúng kiểm tra
giới hạn. Đầy đủ 60 ô và diễn giải tại [rà soát thống kê](statistical_review.md),
[audit JSON](results/week2/statistical_review/audit.json) và
[kết quả cuối](results/week2/README.md). Scenario RMSE tổng hợp là RMS của các
per-seed RMSE, không phải trung bình số học; các ô không được xem là độc lập.

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

Kiểm tra mã policy/Swissmetro trước lượt compute: **131 tests passed, 40,95 giây**;
Ruff check/format đạt (36 files), ty 0.0.82
đạt toàn bộ `src/gsm_poc` với `--error-on-warning`. Browser QA là bằng chứng
lịch sử; chưa kiểm tra lại browser/CI từ xa trong đợt này. Không thêm dependency.

## Nguồn đóng băng và checksum

Các đường dẫn tính từ repo root; dữ liệu lớn/run artifacts nằm trong thư mục
ignored. Các hash dưới định danh bằng chứng, không đồng nhất các phiên bản mã.

| Bằng chứng | SHA-256 |
|---|---|
| Bản đối chiếu `.cache/submission-20261007-results-034119.json` | `ad2cf2d58479dfdd5b1d6d6f09a1f957423dfc5f2a2d542bc62f21de745a21d4` |
| Coverage frozen spec | `8fda615108bc06365320bdbf41fa5ded3e19423630efd360a6767c2c61e61af1` |
| Pooled seed_metrics.parquet lịch sử (65 seeds) | `e0b916e51b0f0ef8d07fce976e1d533fefa554bfacda9abf5f4eab6dfe417132` |
| Pooled evaluation_metrics.csv lịch sử (65 seeds) | `68125acf4666680591e0d2c055ebb2090f0fd7387b8e8feaf6c71c85ca2fa5ad` |
| Final seed_metrics.parquet (500 jobs) | `37b603a12e432d075be30d2048eb4c90d52a29cfe11b439314a4bfa3100f3916` |
| Final evaluation_metrics.csv (60 cells) | `9cee52901c25189b7808266f649ff49088a5965b16b570d5399ba8b24b5801dc` |
| Coverage source | `8459df189c1da3d4252f1ac2445854ac684c4ee15cecf951d80cbfd5402648a0` |
| Policy/Swissmetro closeout source | `68a7a1b7bf19ec6eb2dff47ecb90a0c429c5c34e724232c371c9b3b0535661f3` |
| Lock | `e619cacb8a04c36d2970a268d8ebbb983f0c1c31dc66a6c918331bd7691b6b1c` |
| Policy manifest `runs/week2-policy-final-32001-32020/manifest.json` | `ce9c99bbeecc8ff1fec175daae53311f022c2f6a695c64d1b9bd238f57e614cc` |
| Swissmetro manifest `runs/week2-swissmetro-closeout-31001/manifest.json` | `95c13b8941da5a9b527ee8e893f2d8327d10b23998350beffcc50a4b0e6903b7` |

Revision frozen coverage `574cf501304a777827c2e04704d96a1ab563e1b2`; policy/
Swissmetro nhận diện bằng source hash ở thời điểm chạy. Revision và script hash
của rà soát mới ghi riêng trong audit JSON. Gói kết quả gốc được giữ nguyên,
kể cả metadata `pending review` ở thời điểm xuất; kết luận mới nằm trong hồ
sơ rà soát. Báo cáo không gán các outputs lịch sử cho HEAD hiện tại.

## Điều kiện còn lại để đóng Week 2

1. Chốt cách nghiệm thu hạn chế interval calibration: ghi nhận kết quả hoặc
   ngoại lệ được người nghiệm thu chấp nhận; chưa có xác nhận này. Nếu cải thiện
   phương pháp, dùng development/holdout mới theo protocol đóng băng trước.
2. Chốt bộ demand/choice bàn giao và exports tương thích với manifest/config/
   scope/code; kiểm tra rerun/resume tương ứng. Model lịch sử đã xác minh là
   bằng chứng riêng, chưa gọi là bộ bàn giao mới.
3. Hai báo cáo đã đồng bộ mốc kết quả cuối. Còn ghi người kiểm tra/ngày/kết luận
   hoặc ngoại lệ thực tế. Các trường này hiện **chưa xác nhận**; hạn nộp thực tế
   cũng chưa được cung cấp.

Compute và rà soát số liệu đã hoàn tất. Các kết luận hiện chỉ áp dụng public/
synthetic, evidence C; mô hình cung, simulator và thử nghiệm/ROI GSM thuộc bước sau.
