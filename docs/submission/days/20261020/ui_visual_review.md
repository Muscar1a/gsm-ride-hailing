# Kiểm tra trực quan UI — 20/10/2026

Backlog chính thức: [Issue #1 — UI dự báo: KPI thiếu support, CI NaN% và nhãn bằng chứng](https://github.com/Muscar1a/gsm-ride-hailing/issues/1).
Các vấn đề được ghi nhận, chưa sửa trong lượt kiểm tra này.

## Môi trường và phạm vi

- Kiểm tra trực tiếp dashboard localhost bằng trình duyệt desktop, gồm Price scenario, Methods và tải JSON/CSV qua nút trên UI.
- HEAD: `7ebae15be9c4dcb0a1b28474a74531236de72658`, cộng các thay đổi local chưa commit về docs và `contrast_ols`; không giả định chúng đã có trên `main`.
- Fixture riêng: `ui-contrast-visual-20261020`, synthetic `COLLINEAR_PRICE`, seed 88001, zone 161, 50 phiên/block, min support 1. Đây là fixture UI, không phải bộ assessment chính thức.
- Đối chiếu bổ sung cùng bundle với ngưỡng min support 5 của profile chính thức vẫn cho `status=ok`; số block training nhỏ nhất trong các nhóm point/context là 9. Ca hợp lệ không phụ thuộc việc hạ ngưỡng fixture xuống 1.
- Run cũ đối chứng: `20261020T074809-20be395f`, `RCT_SYN`, DML, seed 42.
- Không sửa mã ứng dụng trong lượt này. 52 hash nguồn/config của snapshot demand-contrast đã đóng băng vẫn khớp; xem manifest bằng chứng.

## Các ca đã xác minh

| Thao tác | Kết quả quan sát |
| --- | --- |
| `contrast_ols`, analytic, X/Y cùng +10%, 1.000 phiên | Status/support/interval đều `ok`; trước 554,438466514, sau 478,846039682, chênh lệch −75,592426832 yêu cầu kỳ vọng. |
| Chỉ X +10%, Y không đổi trên fixture đồng biến | `not_identified`; không xuất KPI dự báo. |
| X/Y cùng +20% | Bị chặn `out_of_support`; không xuất KPI, nhưng nhãn support chưa đúng. |
| Đổi 1.000 thành 2.000 phiên | Xác suất giữ nguyên; số yêu cầu kỳ vọng và chênh lệch tăng gấp đôi: 957,69 và −151,18 trên UI. |
| Bootstrap với 0 draws | Điểm dự báo hợp lệ được giữ, CI không xuất, có lý do; dòng nominal lại hiện `NaN%`. |
| Mở ma trận hệ số và Methods → effects.csv → contrast_ols | Bốn hệ số riêng không nhận dạng được hiện null/“—”, không bị thay bằng 0. |
| Tải scenario JSON và effects CSV qua UI | JSON khớp run, request và kết quả; CSV giữ bốn hệ số riêng unavailable. |
| Console và chiều rộng trang desktop | Không ghi nhận console error; document/viewport đều rộng 1.265 px, không tràn ngang toàn trang. |

CI analytic của chênh lệch tổng trong ca hợp lệ: [−82,761659597424; −68,42319406743127]. Đây là đầu ra fixture, không phải bằng chứng calibration trên dữ liệu GSM.

## Nợ cũ còn tái hiện được

Chi tiết tái hiện, hành vi mong muốn và tiêu chí hoàn tất nằm trong Issue #1.

| Ưu tiên | Vấn đề | Bằng chứng |
| --- | --- | --- |
| P1 | Run DML cũ báo `insufficient_support` nhưng vẫn trình bày KPI 5.042,32 và −430,07 như dự báo thông thường, không tách sensitivity. | [Ảnh run cũ](../../../../artifacts/research/20261020/ui_visual/06-legacy-insufficient-support.jpg) |
| P2 | CI không khả dụng vẫn hiện `nominal NaN%`, tái hiện cả run cũ và fixture mới. | [Ảnh bootstrap](../../../../artifacts/research/20261020/ui_visual/04-bootstrap-unavailable.jpg) |
| P2 | Kiểm tra ngoài miền giá đã thất bại nhưng Support hiện `unavailable` thay vì trạng thái ngoài support. | [Ảnh run cũ](../../../../artifacts/research/20261020/ui_visual/07-legacy-out-of-support.jpg) |
| P2 | Cảnh báo coverage lịch sử 88–89% không gắn model/run/phương pháp/phạm vi, xuất hiện cả khi chọn contrast mới. | [Ảnh dự báo hợp lệ](../../../../artifacts/research/20261020/ui_visual/08-final-supported.jpg) |
| P3 | README submission trỏ đến `days/20261012/GSM_Syncup_Week1-3_20261012_v1.pptx`, nhưng artifact không có trong working tree. | Kiểm tra đường dẫn local; cần khôi phục đúng nguồn hoặc ghi không có sẵn. |

Không thay cảnh báo coverage toàn cục bằng 90–100%: assessment mới chỉ quan sát khoảng đó trên 40 seed/family, chưa chứng nhận mọi CI đạt mức danh nghĩa 95%.

## Bằng chứng và giới hạn

- [Ảnh đầy đủ ca hợp lệ](../../../../artifacts/research/20261020/ui_visual/02-supported-joint-forecast.jpg), [JSON tải từ UI](../../../../artifacts/research/20261020/ui_visual/02-supported-scenario.json).
- [Ảnh Methods](../../../../artifacts/research/20261020/ui_visual/05-effects-unavailable.jpg), [CSV tải từ UI](../../../../artifacts/research/20261020/ui_visual/05-exported-effects.csv).
- [Manifest checksum và kết quả kiểm tra](../../../../artifacts/research/20261020/ui_visual/verification.json).

Docs mới được dùng để đối chiếu đặc tả; giới hạn khoa học đã nêu trong docs không tự trở thành bug. Hệ số riêng null khi contrast kết hợp được nhận dạng là hành vi đúng. Thiếu dữ liệu GSM, calibration thực tế, exposure/total-market demand, DML thiếu hạng, support manifold tổng quát và equilibrium không nằm trong phạm vi sửa lỗi UI này.

Chưa kiểm tra mobile, mọi tab vận hành hoặc hiệu năng tải file. Độ trễ của công cụ tự động hóa không được dùng làm số đo latency ứng dụng. Không chạy lại toàn bộ pytest cho lượt chỉ bổ sung báo cáo và bằng chứng này.
