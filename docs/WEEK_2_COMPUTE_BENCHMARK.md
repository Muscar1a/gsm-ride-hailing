# Thử nghiệm compute cho Week 2 — 07/10/2026

Mục tiêu: chọn cách chạy nhanh hơn cho 500 seed jobs đã đóng băng, giữ nguyên
mô hình, dữ liệu, seed và 199 bootstrap draws cho mỗi estimator được nhận dạng.
Dữ liệu đánh giá là bán tổng hợp (evidence C). Seed `19001` dành riêng cho thử
compute, không tính vào 500 job nghiệm thu.

## GPU và lựa chọn nhánh thử nghiệm

RTX 3060 Laptop 6 GB chạy được toàn bộ probe nhưng mất **1.407,42 giây**,
so với **521,62 giây** trên CPU trong cùng WSL và **580,02 giây** trên CPU
Windows. GPU chậm 2,70 lần so với CPU WSL. Adapter GPU còn thay forest nhiều
đầu ra chung bằng các forest riêng, nên không tương đương mô hình đóng băng.
Theo điều kiện đã thống nhất, tiếp tục thử CPU song song. Chi tiết và bằng
chứng: [GPU probe](GPU_PROBE_19001.md).

## Sàng lọc số worker CPU

Intel Core i7-12700H: 14 core vật lý, 20 luồng logic; RAM 39,70 GiB.
Mỗi worker là một tiến trình độc lập, dùng `.venv` Python 3.11.9 và mã trong
snapshot. Forest `n_jobs=1`; OMP/OpenBLAS/MKL đều giới hạn một luồng.

Chạy hai lượt công việc liên tiếp cho mỗi worker, cùng seed RCT `19001`, với
**10 draws/estimator**. Lưới ban đầu có 114 probe jobs. Thời gian dưới đây bao gồm khởi động
tiến trình và import; throughput của probe 10 draws không phải tốc độ nghiệm
thu 199 draws.

| Worker | Probe jobs | Tổng giây | Probe jobs/giờ | RAM trống thấp nhất (GiB) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 72,95 | 98,70 | 22,31 |
| 2 | 4 | 73,49 | 195,94 | 21,94 |
| 4 | 8 | 79,37 | 362,85 | 21,31 |
| 6 | 12 | 84,89 | 508,89 | 20,76 |
| 8 | 16 | 87,53 | 658,02 | 20,30 |
| 10 | 20 | 89,12 | 807,87 | 19,76 |
| 12 | 24 | 92,13 | 937,78 | 19,24 |
| 14 | 28 | 90,28 | 1.116,58 | 18,76 |

Trong lưới 1–14 worker, 14 worker có throughput cao nhất: 11,31 lần một
worker, cao hơn 12 worker khoảng 19,1%. Tất cả metrics khớp trong sai số tuyệt
đối `1e-12`, không thiếu bootstrap draw. Mẫu CPU toàn máy cao nhất ở cấu hình
14 worker là 96,25%; RAM còn trống ít nhất 18,76 GiB. Các ứng dụng khác và
runner coverage cũ vẫn hoạt động trong lúc đo; số tài nguyên là của toàn máy,
lấy mẫu mỗi giây. Các cấu hình được chạy tuần tự, chưa lặp lại cả grid.

Mở rộng tới 20 luồng logic bằng một lượt mới, vẫn hai công việc mỗi worker:

| Worker | Probe jobs | Tổng giây | Probe jobs/giờ | RAM trống thấp nhất (GiB) |
| ---: | ---: | ---: | ---: | ---: |
| 14 | 28 | 93,10 | 1.082,68 | 17,99 |
| 16 | 32 | 96,82 | 1.189,86 | 17,50 |
| 18 | 36 | 102,57 | 1.263,50 | 17,02 |
| 20 | 40 | 114,44 | 1.258,28 | 16,50 |

Tổng hai đợt có **250 probe jobs với 10 draws**. 18 và 20 worker gần ngang nhau
(chênh khoảng 0,4%); cần đối chiếu đủ 199 draws trước khi chọn. Lượt lặp 14
worker chậm hơn lượt trước khoảng 3,1%, cho thấy thời gian có dao động theo
điều kiện máy. Không suy từ chênh lệch nhỏ trong một lượt thành tối ưu tuyệt đối.

Kết quả máy: [1–8 worker](../.cache/cpu_scaling_20261007/sweep-10/benchmark.json),
[10–14 worker](../.cache/cpu_scaling_20261007/sweep-10-extra/benchmark.json),
[14–20 worker](../.cache/cpu_scaling_20261007/sweep-10-logical/benchmark.json).
Mỗi probe lưu cấu hình, phiên bản thư viện, checksum mã/context/metrics và thời
gian. File `resources-w*.json` lưu chuỗi mẫu CPU/RAM.

## Xác nhận đầy đủ và chạy nghiệm thu

**14 worker đã xác nhận đầy đủ:** 14 job đồng thời hoàn tất trong **680,43 giây
(11 phút 20 giây)**, tương đương **74,07 job/giờ**. Mỗi job có 199/199 draws ở
cả 3 estimator; metrics khớp CPU gốc với chênh lệch tuyệt đối lớn nhất
**2,22e-16**. RAM còn trống ít nhất 16,59 GiB, CPU toàn máy cao nhất 100%.
[Kết quả 14 worker](../.cache/cpu_scaling_20261007/confirm-199/benchmark.json).

**18 worker đã hoàn tất xác nhận:** 18 job mất **762,09 giây (12 phút 42 giây)**,
đạt **85,03 job/giờ**, cao hơn lượt 14 worker khoảng 14,8%. RAM còn trống ít nhất
**15,40 GiB**; CPU toàn máy cao nhất 100%. Tất cả job có đủ 199 draws/estimator
và khớp CPU gốc trong sai số `1e-12`; chênh lệch số lớn nhất là **2,22e-16**.

**Lượt 20 worker đã bị dừng theo yêu cầu Bun**, trước khi hoàn tất. Không có
kết luận tốc độ cho lượt 199 draws này. Status ghi `stopped_by_user`, các
checkpoint probe chưa hoàn tất ghi `interrupted`; giữ nguyên kết quả đã có.
[Kết quả nhóm đầy đủ](../.cache/cpu_scaling_20261007/confirm-199-logical/benchmark.json)
lưu riêng cấu hình 18 worker đã hoàn tất và trạng thái dừng của lượt 20 worker.

18 worker là mức nhanh nhất trong các lượt đầy đủ đã hoàn tất, chưa phải
chứng minh tối ưu tuyệt đối. 282 probe jobs hoàn tất (250 lượt 10 draws và 32
lượt 199 draws) đều được kiểm tra checksum và kết quả số; 20 probe bị gián đoạn
không được tính vào kết quả đầy đủ. [Tổng hợp đã xác minh](../.cache/cpu_scaling_20261007/summary.json).

**500/500 job nghiệm thu đã hoàn tất lúc 17:13:28 ngày 07/10, Asia/Bangkok.**
Mỗi DGP có đủ 100 seed, tổng 100 batch; không có checkpoint `failed`. Status
cuối ghi `complete`, coordinator ghi `finished` và đã kết thúc. Không probe
nào được tính vào 500 job này. Lịch cập nhật mỗi giờ đã tạm dừng khi hoàn tất.

Toàn bộ phép đo cấu hình đã dừng trước lượt nghiệm thu. Lượt pool 50 worker
khởi động lúc 12:58:17 gặp lỗi cấp phát bộ nhớ và được dừng; 80 checkpoint
cũ giữ nguyên. Theo chỉ định mới của Bun, pool **30 worker CPU** chạy tiếp từ
**13:09:44**, đạt **412/500 job** rồi kết thúc lúc **16:57:44** sau hai lỗi
ghi checkpoint Windows trong `COLLINEAR_PRICE`. Seed `20081` từng bị gián đoạn
được chạy lại, các seed đã hoàn tất được dùng lại. Tốc độ 85,03 job/giờ ở trên
là kết quả probe 18 worker, không phải phép đo của pool 30 hoặc 50 worker.

Sau sửa lỗi I/O, runner resume với pool 30 worker lúc **17:12:59**, xử lý
**88 seed còn thiếu** và kết thúc lúc **17:13:28**. Checksum JSON/parquet của
toàn bộ **412 checkpoint trước resume** giữ nguyên; source, config, context,
runner gốc và `frozen_spec.json` không bị sửa. Bằng chứng trước/sau được lưu ở
[audit phục hồi](../.cache/checkpoint_io_recovery_20261007/after_resume.json).

Lượt 18 worker dùng cùng môi trường và không có runner coverage cũ chạy cùng;
lượt 14 worker trước có một job CPU của runner cũ hoạt động. Thời gian probe
đầy đủ bao gồm khởi động/import; reference CPU Windows 580,02 giây trước đó
là thời gian bên trong script, đo ở thời điểm khác.

Bộ điều phối mới chỉ thay cách xếp lịch tiến trình. Nó giữ nguyên batch 5 seed,
run ID, config, source, context, môi trường số và checksum của runner gốc.
Checkpoint hoàn tất được dùng lại sau kiểm tra input hash và checksum; seed bị gián đoạn sẽ chạy lại
từ đầu. Lock chung ngăn hai runner đồng thời ghi cùng các batch. Timeout mỗi
batch trong đợt chạy này là 6 giờ; lỗi dừng xếp lịch mới, giữ lại checkpoint
và trạng thái lỗi. Batch size vẫn là 5 seed, số worker là tối đa; ngưỡng RAM
có thể hoãn mở thêm batch.

Ngưỡng chừa RAM theo yêu cầu Bun là **5 GiB** (khoảng 5,37 GB). Trước khi mở
batch, bộ điều phối yêu cầu thêm 1 GiB headroom; trong 10 giây đầu của mỗi
child, khoản này được giữ riêng để tránh nhiều tiến trình cùng khởi động trước
khi bộ đếm RAM phản ánh cấp phát. Khi thiếu headroom, xếp lịch mới chờ RAM hồi
phục; các batch đang chạy hoàn tất bình thường. Chờ khi không còn batch chạy
được giới hạn 10 phút. Status lưu RAM hiện tại, mức trống thấp nhất được lấy
mẫu và trạng thái chờ. Đây là kiểm soát mở batch; RAM của ứng dụng khác vẫn
có thể thay đổi trong lúc chạy.

Metadata chạy song song lưu riêng trong `week2_reporting/execution.json`;
`frozen_spec.json` không bị sửa. Status bổ sung số checkpoint hoàn tất và các
batch/seed đang chạy. Bảng tổng hợp chỉ cập nhật khi batch hoàn tất, nên có thể
chậm hơn số job đã có checkpoint. Hoàn tất compute vẫn cần rà soát coverage,
NULL_EFFECT, failures và stress cases trước khi nghiệm thu thống kê.

## Sửa lỗi ghi checkpoint Windows

Hai batch `week2-collinear_price-20001-20005` và
`week2-collinear_price-20011-20015` bị `PermissionError: [WinError 5]` khi
`os.replace` thay JSON checkpoint. Test trên Windows tái hiện được lỗi khi
file đích đang mở để đọc; retry thành công sau khi reader đóng file. Đây là
bằng chứng cho một nguyên nhân có thể gây lỗi, chưa xác định duy nhất tiến
trình giữ file trong hai sự cố thực tế.

Adapter [week2_checkpoint_io.py](../scripts/week2_checkpoint_io.py) chỉ thay
thao tác atomic write tại runtime, dùng chung cho coordinator và child.
Worker vẫn import evaluator từ snapshot và nhận nguyên các tham số CLI.
Adapter thử lại `os.replace` tối đa 8 lần với WinError 5/32/33; tổng thời gian
chờ tối đa 3,17 giây. Nó giữ nguyên file cũ tới khi thay file thành công,
không tính lại estimator trong vòng retry, và vẫn báo lỗi nếu file bị khóa
kéo dài hoặc gặp lỗi I/O khác. Checksum adapter được ghi riêng trong metadata
thực thi; không thay checksum của source thực nghiệm đã đóng băng.

## Tái lập

Chạy tại repository bằng PowerShell, output probe phải chưa tồn tại:

```powershell
.venv/Scripts/python.exe scripts/benchmark_week2_cpu.py --snapshot .cache/week2-evaluation-574cf501-20261007 --output .cache/cpu_scaling_repeat_10 --workers 1,2,4,6,8,10,12,14,16,18,20 --waves 2 --draws 10
.venv/Scripts/python.exe scripts/benchmark_week2_cpu.py --snapshot .cache/week2-evaluation-574cf501-20261007 --output .cache/cpu_scaling_repeat_199 --workers 14,18,20 --waves 1 --draws 199
```

Chỉ khởi động/resume coverage khi runner trước đã dừng; lock sẽ từ chối chạy
trùng. Lệnh resume dùng trong đợt nghiệm thu với pool 30 worker:

```powershell
.venv/Scripts/python.exe -u scripts/run_week2_parallel.py --snapshot .cache/week2-evaluation-574cf501-20261007 --build-id 214dd5a1184bd3705e66 --workers 30 --ram-reserve-gib 5 --batch-timeout-seconds 21600
```

Snapshot revision: `574cf501304a777827c2e04704d96a1ab563e1b2`.
Protocol fingerprint: `f2f405f8ca5d4a2962628f4487224ea003c1bb9c01fc6abb679910d8e9747715`.
Reporting dùng seed `20001–20100` cho mỗi DGP; probe `19001` được tách riêng.

## Kiểm tra mã

Ruff check đạt. **26 tests** của runner gốc và bộ điều phối song song
đạt: command/env tương thích, giới hạn concurrency, bỏ qua batch hoàn tất,
giữ nguyên protocol, phát hiện checksum sai, lưu lỗi, hoãn mở batch khi thiếu
RAM, phục hồi khi RAM tăng, giới hạn cấp phát khi khởi động và resume với pool
50 worker chỉ chạy batch chưa hoàn tất, tái hiện khóa file Windows, retry sau
khi reader đóng file, giới hạn retry, giữ file cũ khi vẫn lỗi, không retry lỗi
khác và giữ nguyên serialization/checksum source khi dùng adapter. Các benchmark trước đó chạy
evaluator thật để kiểm tra kết quả số; không thay bài toán bằng fixture nhỏ.
