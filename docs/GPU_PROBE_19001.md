# GPU probe — seed 19001

Ngày thử: 07/10/2026. Mục tiêu là kiểm tra RTX 3060 Laptop 6 GB có chạy được phần Random Forest nuisance của DML và đo thời gian một seed. Đây là thử nghiệm phát triển với dữ liệu bán tổng hợp (evidence C), tách khỏi 500 seed jobs của nghiệm thu Week 2.

**Kết luận:** GPU chạy được đủ 199 bootstrap draws cho cả 3 estimator, nhưng pipeline thử mất 23 phút 27 giây, chậm 2,70 lần so với CPU gốc trong cùng WSL (8 phút 42 giây). Nên ưu tiên tăng số seed jobs chạy song song trên CPU cho Week 2; chưa dùng backend GPU này để thay mô hình đã đóng băng.

## Thiết kế đối chiếu

- DGP `RCT_SYN`, seed `19001` dành riêng cho probe; 7.440 blocks, 372.000 quote sessions, 4.800 train blocks thuộc 20 ngày gốc.
- Cùng TLC context, phép chia ngày, 5-fold GroupKFold theo `original_day_id`, 50 cây, depth 6, minimum leaf 20 và bootstrap resample ngày gốc. Mỗi lượt đầy đủ có 199 draws cho từng estimator: `naive_ols`, `adjusted_ols`, `dml`.
- CPU giữ nguyên mô hình của bản đóng băng: sklearn Random Forest với nhiều đầu ra chung. GPU dùng cuML Random Forest riêng cho từng đầu ra của `model_y` và `model_t`, đầu vào float32, `n_bins=128`, `n_streams=1`. OLS, lớp tuyến tính cuối của DML và thao tác resample vẫn chạy trên CPU.
- cuML 26.6 không nhận `sample_weight` trong API fit đang cài. Adapter chỉ bỏ qua trọng số khi mọi trọng số dương và bằng nhau; dữ liệu probe có trọng số 50 ở mọi train block. Trọng số khác nhau bị từ chối, không bị bỏ qua âm thầm.
- GPU forest được gọi trực tiếp với CuPy device arrays. Adapter từ chối implementation không thuộc cuML và đếm số GPU fits. Không dùng `cuml.accel` vì đầu ra nhiều chiều và sample weights có thể dẫn đến fallback CPU ([NVIDIA compatibility](https://docs.nvidia.com/cuml/latest/cuml-accel/compatibility/)).

GPU thay đổi cấu trúc nuisance learner và cách tìm split, vì vậy không phải là thay backend với kết quả tương đương từng bit. Một seed không đủ để nghiệm thu coverage hay sai số trên cả 5 DGP.

## Môi trường và nguồn cố định

| Thành phần | Giá trị |
| --- | --- |
| GPU | NVIDIA GeForce RTX 3060 Laptop, khoảng 6 GB VRAM |
| CPU | Intel Core i7-12700H |
| Windows reference | Python 3.11.9, môi trường `.venv` hiện có |
| WSL đối chiếu | Ubuntu WSL2, Python 3.11.15, cuML 26.6.0, CuPy 14.2.0 |
| Thư viện số chung | NumPy 2.4.6, pandas 2.3.3, SciPy 1.17.1, sklearn 1.6.1, EconML 0.16.0, joblib 1.6.0 |
| Snapshot | `.cache/week2-evaluation-574cf501-20261007` |
| Revision đóng băng | `574cf501304a777827c2e04704d96a1ab563e1b2` |
| Source checksum theo manifest Windows | `8459df189c1da3d4252f1ac2445854ac684c4ee15cecf951d80cbfd5402648a0` |
| TLC context checksum | `7137136cd0687ab6c60c382576fad6568d1587ccb9953e575b57c19945531ccf` |
| CUDA của môi trường thử | runtime 12.9; CUDA driver API trả về 13.2 |

Các báo cáo máy lưu cấu hình, seed, phiên bản Python/thư viện, checksum script và source/context. `resolved_requirements.txt` trong cache lưu toàn bộ phiên bản đã resolve; `scripts/gpu_probe_constraints.txt` giữ các phiên bản này để cài lại. Môi trường GPU, Python và uv được đặt trong `.cache/gpu_probe_19001`; không sửa `.venv`, `pyproject.toml`, `uv.lock` hay mã của snapshot.

Hàm source hash cũ đưa dấu phân cách đường dẫn của hệ điều hành vào fingerprint. Script probe tái tạo quy ước đường dẫn Windows để kiểm tra cùng manifest trên WSL, đồng thời lưu native hash của WSL. Mã nguồn được kiểm tra lại sau mỗi probe.

## Kết quả

| Lượt đối chiếu | Draws / estimator | Toàn lượt (giây) | Riêng DML (giây) | Bootstrap |
| --- | ---: | ---: | ---: | --- |
| CPU gốc — Windows | 199 | 580,02 | 554,87 | 199/199, cả 3 estimator |
| CPU gốc — WSL | 199 | 521,62 | 496,57 | 199/199, cả 3 estimator |
| GPU nuisance — WSL | 199 | 1.407,42 | 1.374,20 | 199/199, cả 3 estimator |

GPU chậm 2,70 lần so với CPU WSL và 2,43 lần so với CPU Windows trong các lượt đo này. Cả 3 estimator của các lượt đầy đủ đều có interval status `ok` theo điều kiện số draws; điều này không chứng minh nominal 95% coverage trên các seed khác.

| Chỉ số DML trên seed 19001 | CPU gốc — WSL | GPU nuisance — WSL |
| --- | ---: | ---: |
| Theta RMSE, 4 hệ số | 0,016639 | 0,017078 |
| Scenario probability RMSE | 0,003296 | 0,003315 |

Theta có đơn vị probability / log price; scenario RMSE có đơn vị probability. Chênh lệch theta DML lớn nhất giữa GPU và CPU WSL là 0,000849. Theta OLS của hai lượt WSL trùng nhau; theta DML GPU của lượt 2 draws và lượt 199 draws cũng trùng nhau. Đây là đối chiếu một seed RCT, không phải nghiệm thu sai số trên cả 5 DGP.

Lượt GPU đầy đủ ghi nhận **4.000 GPU forest fits**, 0 CPU adapter fits và 4.000 lần bỏ qua trọng số đồng nhất 50. VRAM toàn GPU cao nhất trong các mẫu là **2.248 MiB (2,20 GiB)**, utilization cao nhất 49%, nhiệt độ cao nhất 87°C. Không gặp lỗi thiếu VRAM hoặc bootstrap failure.

Chênh lệch lớn nhất giữa theta DML Windows và WSL là 3,33e-16; các OLS khác nhau tối đa 3,67e-15. CPU Windows được chạy trước bản sửa kiểm tra hash; đối chiếu CPU WSL và GPU dùng cùng checksum script hiện tại. Đường fit CPU giữ nguyên.

Kết quả máy: [đối chiếu tổng hợp](../.cache/gpu_probe_19001/comparison.json), [GPU đầy đủ](../.cache/gpu_probe_19001/results/gpu-199/report.json), [CPU WSL](../.cache/gpu_probe_19001/results/cpu-wsl-199/report.json), [CPU Windows](../.cache/gpu_probe_19001/results/cpu-199-v1/report.json). CSV metrics và JSON telemetry nằm cạnh mỗi report. Các checksum report/metrics đã được kiểm tra khi tổng hợp.

Lượt `matching-cpu-10` thành công trong 85,18 giây, DML 82,92 giây, với 220 scalar CPU forest fits. Đây là lượt kiểm tra cấu trúc adapter với 10 draws, không dùng thời gian của lượt này để so trực tiếp với lượt 199 draws. Với 5 folds và 2 đầu ra cho mỗi nuisance, adapter tạo 20 forests mỗi lần fit DML; mô hình CPU gốc dùng 10 forests nhiều đầu ra.

Lượt kiểm tra nhỏ `gpu-2-v1` thành công với 2/2 draws ở cả 3 estimator, 60 GPU forest fits và 0 CPU adapter fits. Thời gian đo trong script: 149,99 giây, gồm lần đầu nạp thư viện GPU; VRAM toàn GPU cao nhất trong các mẫu là 2.173 MiB, utilization cao nhất 48%. Các interval của lượt 2 draws được đánh dấu `interval_unstable`.

Có cảnh báo từ nvforest/Treelite: native library báo Treelite 4.6.1, model checkpoint dùng 4.7.2. cuML yêu cầu Treelite >=4.7, nên không hạ phiên bản để né cảnh báo. Cảnh báo được giữ lại và phải được xem là một hạn chế của môi trường thử.

Thời gian là thời gian bên trong script từ khởi tạo backend/tạo dữ liệu đến hoàn tất fit/bootstrap/metrics; không bao gồm cài môi trường và một phần import trước `main`. Mỗi lượt chỉ đo một lần; runner coverage CPU gốc vẫn hoạt động, và các lượt đối chiếu WSL chạy cùng thời điểm. Telemetry lấy mẫu khoảng 0,5 giây; VRAM và utilization là số của toàn GPU, gồm các ứng dụng khác, không phải mức riêng của tiến trình.

Trong lượt 199 draws, GPU lên 87°C; mẫu `nvidia-smi` ghi `sw_thermal_slowdown=Active`, `hw_thermal_slowdown=Not Active`. Đây là bằng chứng máy đang áp dụng giới hạn xung vì nhiệt tại thời điểm lấy mẫu, chưa định lượng được phần thời gian tăng thêm do nhiệt. Mẫu có timestamp lưu ở `.cache/gpu_probe_19001/thermal_observation.json`; nhiệt độ theo thời gian nằm trong `telemetry.json`. Kết luận tốc độ áp dụng cho pipeline và điều kiện laptop đã thử.

## Chạy lại

Từ PowerShell tại repository, cài môi trường riêng nếu chưa có:

```powershell
wsl -d Ubuntu --exec python3 /mnt/e/AI/vric/gsm-ride-hailing/scripts/setup_gpu_probe.py
```

Chạy lượt nhỏ trước, dùng thư mục output chưa tồn tại:

```powershell
wsl -d Ubuntu --exec python3 /mnt/e/AI/vric/gsm-ride-hailing/scripts/run_gpu_probe_wsl.py --output /mnt/e/AI/vric/gsm-ride-hailing/.cache/gpu_probe_19001/results/gpu-2-repeat --backend gpu --draws 2
```

Chạy đủ và đối chiếu cùng môi trường:

```powershell
wsl -d Ubuntu --exec python3 /mnt/e/AI/vric/gsm-ride-hailing/scripts/run_gpu_probe_wsl.py --output /mnt/e/AI/vric/gsm-ride-hailing/.cache/gpu_probe_19001/results/gpu-199-repeat --backend gpu --draws 199
wsl -d Ubuntu --exec python3 /mnt/e/AI/vric/gsm-ride-hailing/scripts/run_gpu_probe_wsl.py --output /mnt/e/AI/vric/gsm-ride-hailing/.cache/gpu_probe_19001/results/cpu-wsl-199-repeat --backend cpu --draws 199
```

Launcher giới hạn mỗi lượt ở 30 phút. Probe từ chối output đã có và output bên trong snapshot; kết quả luôn ghi `included_in_reporting=false`. Backend `matching_cpu` có thể chạy adapter một forest cho mỗi đầu ra với sklearn để nghiên cứu riêng ảnh hưởng của cấu trúc learner; không phải mô hình CPU gốc.

Mỗi thư mục kết quả có `report.json`, `metrics.csv` và `telemetry.json`. Lệnh `.venv/Scripts/python.exe .cache/gpu_probe_19001/summarize_probe.py` dựng lại `comparison.json` từ các lượt đã lưu và kiểm tra checksum, cấu hình, context, số draws và số GPU fits. File `gpu199_collected_console.log` lưu các console chunks đã thu thập, gồm cảnh báo Treelite; không có phần startup đầu lượt. Cache và các package CUDA không đưa vào version control.

## Kiểm tra

Adapter đã được kiểm tra về clone/shape nhiều đầu ra, tích hợp weighted LinearDML, từ chối trọng số không đều khi GPU không hỗ trợ, và từ chối fallback CPU. Regression tests kiểm tra hash theo quy ước Windows vẫn phát hiện thay đổi byte nguồn trên WSL, output đã có được giữ nguyên và snapshot không nhận output probe. 14 tests liên quan probe/coverage đã đạt; Ruff check và format đã đạt. Bộ requirements/constraints đã resolve thành công 69 packages, không thay môi trường đang chạy.

Sau thử nghiệm, source checksum của snapshot và checksum runner coverage gốc vẫn không đổi. Runner gốc tiếp tục hoạt động; status lúc 11:30:43 ngày 07/10 ghi 75/500 seed jobs đã được gộp, đang chạy batch `RCT_SYN` 20076–20080. Không kết quả probe nào được gộp vào coverage này.
