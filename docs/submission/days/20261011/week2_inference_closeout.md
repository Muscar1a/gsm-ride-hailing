# Week 2 — Kết quả xử lý khoảng tin cậy và tín hiệu

Ngày chốt: **11/10/2026, Asia/Bangkok**. Người thực hiện: Codex, theo yêu cầu của Bun.
Trạng thái: **chẩn đoán và đánh giá độc lập đã hoàn tất; Bun nghiệm thu Week 2
với ngoại lệ kỹ thuật ngày 11/10/2026**. [Quyết định và tích hợp hybrid](week2_hybrid_acceptance.md).
Chưa chứng nhận mọi CI đạt 95% hoặc nghiệm thu GSM. Semi-synthetic, evidence C; X/Y giữ nguyên.

## Kết luận trực tiếp

Đã xử lý phần kiểm chứng còn thiếu: đối chiếu công thức phương sai với chuẩn DGP,
đóng băng phương pháp/tiêu chí rồi đánh giá trên 100 seed độc lập mỗi DGP và mỗi
estimator, kiểm tra tín hiệu giả và chạy toàn bộ kiểm thử. Không phát hiện lỗi
công thức OLS block trong phạm vi kiểm tra. Cách gom theo ngày đánh giá thấp
phương sai của một số baseline, nên không chọn làm phương pháp cho lượt độc lập.

**Không kết luận đã chữa hết undercoverage:** một số đầu ra vẫn có coverage
88–89/100. Có **8 dòng cảnh báo riêng** (các đầu ra và DGP có tương quan, không
phải 8 lỗi độc lập), dù **0/168 phép kiểm tra** bác bỏ sau Holm. Không bác bỏ
không chứng minh coverage chính xác 95%; không dùng kết quả này để điều chỉnh
độ rộng CI hoặc chọn lại seeds/method. Gate calibration toàn bộ đầu ra còn mở.

## 1. Kiểm tra nguyên nhân phương sai

Tái dựng **200 dataset cũ**, không fit thêm mô hình. Với mỗi block, covariance
X/Y là `(diag(p_xy) - p_xy p_xy') / n_sessions`; biến đổi bằng linear map của OLS
để lấy joint covariance của bốn theta và hai baseline. Đây là phương sai chính
xác có điều kiện cho estimator tuyến tính trong DGP này. Phần elasticity vẫn
chỉ dùng delta method. Oracle chỉ đi vào evaluator, không vào inference.

- Sai khác lớn nhất giữa điểm tái dựng và điểm production đã lưu:
  **5.32e-14**; conditional bias tối đa:
  **5.67e-14**.
- Tỷ lệ RMS sai số chuẩn HC3 so với chuẩn conditional trên mọi gradient kiểm tra:
  **0.999627–1.003511**, chênh dưới 0,4%.
- Day CR1 có tỷ lệ thấp nhất khoảng **0,824–0,832**: thiếu khoảng 16–18% sai số
  chuẩn ở một số baseline. Đây là sensitivity, không có bảo đảm small-G cho DML.
- Kết quả làm yếu giả thuyết OLS HC3 sai công thức hoặc cần hệ số phóng đại CI.
  Biến động Monte Carlo là một khả năng; chưa thể quy mọi cảnh báo cho nguyên
  nhân đó. Chưa có đối chiếu exact variance tương tự cho DML.

## 2. Đánh giá độc lập đã đóng băng

[Frozen plan](../../../../artifacts/research/20261011/results/final_inference/frozen_plan.json) chọn trước **OLS HC3/t**
và **DML orthogonal-score/normal**, seed **45001–45100**, RCT_SYN và NULL_EFFECT.
Mỗi estimator/DGP có 100 seed; OLS và DML dùng cùng dataset của từng seed.
**400/400 point fits**, không lỗi fit/inference; **15.200 output rows** đều có CI.
Không bootstrap/jackknife, không retries hoặc tăng cohort. Hai DGP chạy song song,
lần lượt **345.88s** và
**344.43s**; không cộng thành thời gian thực.

Coverage dưới đây là số seed có CI chứa truth trên denominator 100, không phải
tỷ lệ các metric trong một lần chạy. Cohort này khác development; không suy ra
hiệu quả cải thiện method bằng việc so trực tiếp với coverage cũ.

### Theta RCT — coverage /100

| Outcome / price | OLS | DML |
| --- | --- | --- |
| X/X | 94 | 94 |
| X/Y | 93 | 89 |
| Y/X | 97 | 96 |
| Y/Y | 97 | 98 |

### Elasticity RCT — coverage /100

| Outcome / price | OLS | DML |
| --- | --- | --- |
| X/X | 95 | 93 |
| X/Y | 93 | 90 |
| Y/X | 97 | 96 |
| Y/Y | 96 | 97 |

### Scenario — min/max theo từng đầu ra

| DGP | Estimator | Coverage range |
| --- | --- | --- |
| NULL_EFFECT | adjusted_ols | 89–100/100 |
| NULL_EFFECT | dml | 88–100/100 |
| RCT_SYN | adjusted_ols | 89–100/100 |
| RCT_SYN | dml | 88–98/100 |

Không gộp các output phụ thuộc thành một coverage chung. Baseline-before được
lặp ở ba scenarios trong raw evidence, nhưng chỉ kiểm định một lần trong family.
Kịch bản từng yếu ở development (`both_plus10:Y_after_probability`) đạt OLS
**99/100**, DML **98/100** trong RCT mới; cảnh báo thấp chuyển sang X. Điều này
không chứng minh method đã sửa mọi scenario.

### Tín hiệu giả — NULL theta /100

| Outcome / price | OLS FP | DML FP |
| --- | --- | --- |
| X/X | 5 | 5 |
| X/Y | 9 | 9 |
| Y/X | 3 | 5 |
| Y/Y | 6 | 4 |

Tỷ lệ riêng từ **3–9% cho OLS**, **4–9% cho DML**. Elasticity NULL có cùng số đếm
trong cohort này, không phải bảo đảm tổng quát. Không có dòng NULL FP mà lower
bound Clopper–Pearson hai phía vượt 5%. Đây là kiểm chứng tín hiệu giả dưới NULL
DGP; chưa chứng minh khả năng phát hiện mức tác động nhỏ có ý nghĩa kinh doanh GSM.

## 3. Cảnh báo giữ nguyên và quyết định

| DGP | Estimator | Family | Output | Coverage /100 | CP upper |
| --- | --- | --- | --- | --- | --- |
| NULL_EFFECT | adjusted_ols | scenario | both_plus10:X_after_probability | 89 | 94.3793% |
| NULL_EFFECT | adjusted_ols | scenario | y_plus10:X_after_probability | 89 | 94.3793% |
| NULL_EFFECT | dml | scenario | both_plus10:X_after_probability | 88 | 93.6431% |
| NULL_EFFECT | dml | scenario | y_plus10:X_after_probability | 88 | 93.6431% |
| RCT_SYN | adjusted_ols | scenario | both_plus10:X_after_probability | 89 | 94.3793% |
| RCT_SYN | dml | scenario | both_plus10:X_after_probability | 88 | 93.6431% |
| RCT_SYN | dml | scenario | y_plus10:X_delta_percentage_points | 89 | 94.3793% |
| RCT_SYN | dml | theta | X/Y | 89 | 94.3793% |

Screen đóng băng gồm **128 kiểm tra coverage** và **40 kiểm tra NULL FP**, exact
binomial một phía, Holm chung ở alpha .05. Kết quả **0 rejection** không xóa
các cảnh báo riêng bên trên, không tạo simultaneous intervals và không chứng
nhận nominal 95%. Không chỉnh CI để ép các số đếm đạt 95/100. Các seeds này đã
được dùng cho assessment, không còn là dữ liệu final chưa xem để tuning.

Toàn bộ **12,000 scenario rows** của
assessment full-context vẫn `insufficient_support` theo ngưỡng hiện tại.
Phạm vi thu hẹp **67,5% trọng số phiên** của choice handoff trước đã qua support;
không tự chuyển kết luận đó sang tất cả seeds hoặc toàn bộ bối cảnh. Production
percentile path chưa đổi, các kết quả lịch sử vẫn giữ nguyên và không được
gắn nhãn đã calibrated bởi lượt block assessment này.

## 4. Kiểm thử và hồ sơ

**410 tests đạt**, gồm cả ba AppTest, hai Pandas FutureWarnings ở các controller
cũ đã đóng băng. Lỗi treo trước là Windows sandbox chặn `socketpair` lúc Streamlit
khởi tạo event loop; chạy với quyền kết nối nội bộ đạt, không sửa ứng dụng.
Ruff, ty trên hai runner mới, format của các file mới và diff check đạt.
Không format toàn repo theo lựa chọn của Bun.

Đối chiếu đã kiểm tra đủ Cartesian jobs/outputs, dataset pairing, DML folds
không trùng ngày, covariance PSD, delta-method SE/endpoints, coverage/FP và exact
binomial bounds. **365 files** trong năm archive trước vẫn khớp hashes; báo cáo
và các số đo trước giữ mốc lịch sử. Hồ sơ mới:

- [Oracle variance summary](../../../../artifacts/research/20261011/results/oracle_variance/summary.csv),
  [audit status](../../../../artifacts/research/20261011/results/oracle_variance/status.json),
  [oracle checksums](../../../../artifacts/research/20261011/results/oracle_variance/evidence_checksums.json).
- [Final summary](../../../../artifacts/research/20261011/results/final_inference/summary.csv),
  [raw seed metrics](../../../../artifacts/research/20261011/results/final_inference/seed_metrics.parquet),
  [168 assessment tests](../../../../artifacts/research/20261011/results/final_inference/assessment_tests.csv).
- [Final audit](../../../../artifacts/research/20261011/results/final_inference/audit.json),
  [source snapshot](../../../../artifacts/research/20261011/results/final_inference/source_snapshot.zip),
  [final checksums](../../../../artifacts/research/20261011/results/final_inference/evidence_checksums.json),
  [machine-readable report](../../../../artifacts/research/20261011/week2_inference_closeout.json).

## 5. Trạng thái bàn giao

Nhánh chẩn đoán, assessment và verification kỹ thuật đã hoàn tất. **Nghiệm thu
calibration mọi đầu ra chưa đóng**; không tiếp tục thử seeds hoặc scale CI trên
cohort final để lấy một kết quả đẹp. Bun đã chọn phương án hybrid và chấp nhận
ngoại lệ kỹ thuật; [hồ sơ tích hợp](week2_hybrid_acceptance.md) ghi phạm vi và
kiểm chứng artifact interfaces. Bootstrap baseline được giữ nguyên.

GSM vẫn chưa bàn giao data. Khi có data, cần kiểm tra mapping/assignment unit,
phụ thuộc theo ngày/khách hàng/thị trường, support, identification và mức tác
động kinh doanh trước khi dùng CI hoặc tín hiệu để đề xuất can thiệp. Chưa có
bằng chứng causal về driver supply, equilibrium hoặc ROI GSM từ nghiên cứu này.
