# Kiểm chứng lõi dự báo theo phép đổi giá — 20/10/2026

Phạm vi: **controlled evidence C**, quần thể phiên báo giá cố định, zone 161,
bối cảnh test ngày thường ngoài giờ cao điểm. Chưa xác nhận hiệu ứng hoặc calibration
GSM, chưa ghi nhận Bun nghiệm thu bản mở rộng, chưa chấm lại điểm sáng chế.

## Câu hỏi và thay đổi

So sánh nhu cầu kỳ vọng khi đổi giá X/Y với giữ nguyên giá hiện tại, cùng quần thể,
khu vực và thời gian. Bản mới `contrast_ols` giữ một số phép đổi giá kết hợp có
nhận dạng khi hai cột hệ số riêng chưa nhận dạng được. SVD giảm thiết kế giá sau
điều chỉnh bối cảnh; hồi quy điều chỉnh và HC3/t tính tác động/bất định trên không
gian được giữ. Hệ số riêng thiếu căn cứ và CI tương ứng vẫn null trong exports.

Đầu vào giá cơ sở/ứng viên, support theo bối cảnh và xác suất từng bối cảnh đều phải
hợp lệ. Rank-one support chỉ hỗ trợ một đường giá affine quan sát được, có điểm
kẹp phù hợp; chưa giải quyết mọi manifold giá phụ thuộc bối cảnh. Estimator mới là
lựa chọn opt-in; mặc định OLS/DML, các run và biên bản nghiệm thu trước giữ nguyên.

Mô hình đối chứng: adjusted OLS, DML hiện tại và dự báo tác động bằng 0. Benchmark
dùng cùng dữ liệu/phép hỏi và giữ cả trường hợp đối chứng không trả được kết quả.
Lợi ích được kiểm chứng là mở rộng phạm vi phép hỏi hợp lệ; không khẳng định độ
chính xác tốt hơn adjusted OLS trên những trường hợp đã được nhận dạng đầy đủ.

## Protocol và tính độc lập

- [Protocol cố định](../../../../configs/demand_contrast_protocol.json):
  `demand-contrast-v1-20261020`; các quy tắc được ghi trước triển khai/assessment.
- Development dùng seeds 88001–88005, 40 bộ dữ liệu. Assessment dùng seeds
  89001–89040, 320 bộ dữ liệu: bốn chế độ biến thiên giá × hai chế độ tác động.
- Dữ liệu quan sát gồm block/counts; chỉ generator/evaluator dùng oracle. Mỗi
  block có 1.000 phiên, split train/validation/test theo ngày; inference giả định
  block controlled độc lập, không suy rộng đơn vị phụ thuộc này sang GSM.
- [Freeze](../../../../artifacts/research/20261020/demand_contrast_v1_final/freeze.json)
  ghi revision gốc, trạng thái working tree có thay đổi chưa commit, môi trường,
  SHA-256 của 52 file nguồn/cấu hình và kết quả development.
- [Snapshot nguồn](../../../../artifacts/research/20261020/demand_contrast_v1_final/frozen_source.zip)
  giữ nguồn chính xác đã chạy. Hash được kiểm tra trước/sau assessment; không sửa
  thuật toán hoặc ngưỡng theo kết quả assessment.
- Bảng quan sát sinh mới nằm trong `.cache/demand_contrast/`, ngoài version control;
  từng dòng kết quả giữ đường dẫn/hash để kiểm tra hoặc tái tạo bằng nguồn đóng băng.

## Kết quả

[Summary](../../../../artifacts/research/20261020/demand_contrast_v1_final/assessment/summary.json)
và [toàn bộ 3.840 dòng kết quả](../../../../artifacts/research/20261020/demand_contrast_v1_final/assessment/records.csv)
ghi 320 bộ dữ liệu trong **65,33 giây**, dưới ngân sách 600 giây. Mỗi bộ có bốn
mô hình đối chiếu và ba đầu ra X/Y/tổng; các điểm dự báo chưa có căn cứ để trống.

| Gate đã chốt | Kết quả |
|---|---|
| Sai số và availability | 240/240 kịch bản đủ nhận dạng của estimator mới có kết quả và CI; RMSE từng family ≤0,001288 xác suất, bias tuyệt đối ≤0,000335; đạt ngưỡng 0,01/0,005 |
| Coverage family | Không có rejection thiếu coverage sau Holm cho 18 family ở alpha 0,05; **không chứng nhận mọi CI đạt 95%** |
| Không có biến thiên | Từ chối đúng 80/80 kịch bản thay đổi giá không nhận dạng |
| Chỉ đổi X khi dữ liệu chỉ có chuyển động chung X/Y | Từ chối đúng 80/80 phép hỏi; không tự chiếu sang tăng chung |

Trong 80 kịch bản giá đồng biến, estimator mới có dự báo tăng chung cho cả hai
chế độ tác động; adjusted OLS/DML đều không có dự báo, nên không có common-valid
RMSE để tuyên bố estimator mới chính xác hơn hai phương pháp đó ở chế độ này.
Trên thiết kế hai giá độc lập và chỉ một giá biến thiên, RMSE ghép cặp của bản mới
và adjusted OLS tương đương tới sai số số học.

Riêng giá đồng biến, tác động khác 0, mỗi dòng dưới có 40 seeds. Đơn vị RMSE/độ rộng
là số yêu cầu kỳ vọng trên 1.000 phiên, không phải sai số số chuyến thực hiện:

| Đầu ra | RMSE | Coverage CI | Độ rộng CI trung bình |
|---|---:|---:|---:|
| X | 0,8284 | 37/40 = 92,5% | 3,0685 |
| Y | 0,7150 | 40/40 = 100% | 2,9545 |
| X+Y | 0,9125 | 36/40 = 90% | 3,2868 |

Coverage toàn bộ 18 family nằm trong 90%–100%. Mỗi family chỉ có 40 lần lặp,
giữ exact binomial CI/p-value và toàn bộ mẫu số trong summary. Không có rejection
không đủ để kết luận calibration danh nghĩa. Đối chứng tác động bằng 0 không có
CI và không được đưa vào kiểm chứng coverage.

## Kiểm tra kỹ thuật

Đối soát nguồn/archive, 40 file quan sát development và 320 file assessment nằm
trong [verification.json](../../../../artifacts/research/20261020/demand_contrast_v1_final/verification.json).

- **653 tests đạt**, hai Pandas FutureWarnings có sẵn, 188,63 giây. Gồm regression
  cho phối hợp giá, thiếu nhận dạng, baseline sai không gian, support mỏng, xác suất
  sai, biến thiên yếu, serialization, parity OLS và mất nhận dạng trong refit.
- Smoke test pipeline generate/fit/method evaluation/scenario với `contrast_ols`
  đạt; scenario tăng chung có kết quả, `effects.csv` giữ hệ số riêng null.
- Ruff cho `src`, runner và tests mới đạt; `ty` cho `src/gsm_poc` đạt. Ruff toàn bộ
  tests còn hai lỗi sắp xếp import có sẵn trong `test_estimation.py` và
  `test_pipeline_dependencies.py`; đã xác nhận cùng lỗi trên nội dung HEAD trước
  thay đổi, không sửa các test cũ để làm đẹp kết quả kiểm tra.
- Không chạy thử nghiệm thật hoặc render/kiểm tra trực quan UI. API và lựa chọn
  estimator đã được nối theo giao diện hiện có; không thay thuật toán simulator.
- Kiểm tra thêm hai phía ngưỡng rank và guard condition vượt ngưỡng đã đạt bằng
  fixture số học xác định sau assessment; không đổi mã, mô hình hoặc ngưỡng.
- Các liên kết mới có đích hợp lệ. Danh mục submission còn một liên kết PPTX
  12/10 bị thiếu từ trước; giữ nguyên hồ sơ cũ và ghi riêng trong verification.

## Giới hạn và tái lập

Đây là đáp ứng tuyến tính cục bộ trên quần thể phiên báo giá cố định. Thuật toán
không tự loại bỏ gây nhiễu thiếu quan sát, không xác định người nào đổi dịch vụ,
không khôi phục tổng nhu cầu tiềm ẩn, không nâng evidence GSM hoặc điểm sáng chế.
Support hẹp vẫn bị từ chối; CI controlled chưa chứng nhận mọi đầu ra đạt 95%.
DML thiếu hạng và support nhiều đường giá theo bối cảnh chưa thuộc phiên bản này.

Lệnh tái lập nằm trong [USAGE](../../../USAGE.md#controlled-demand-contrast-extension).
Chạy lại seeds công bố chỉ kiểm tra tái lập; thay đổi mô hình/ngưỡng sau khi xem
assessment cần protocol mới và seeds cuối độc lập mới. Không ghi đè nguồn/kết quả
đã đóng băng. Mô tả contribution chính tiếp tục ở
[proposal](../../../reference/GSM_Causal_Marketplace_Proposal.md).
