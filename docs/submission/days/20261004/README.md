> Bản lưu hồ sơ ngày 04/10/2026 đã nộp theo xác nhận của người thực hiện.
> Nội dung bên dưới giữ trạng thái tại lúc soạn; các đường dẫn được cập nhật khi đổi thư mục.

Ghi chú lưu trữ: hồ sơ dưới dẫn `GSM Causal Marketplace - Data Requirements.pdf`,
nhưng tệp nguồn đó không có trong checkout này. Tài liệu yêu cầu dữ liệu hiện
có trong repo là [GSM_DATA_CONTRACT.md](../../../GSM_DATA_CONTRACT.md).

# Submission documents — 04 October 2026

Prepared in Vietnamese for the current PoC submission by the sole contributor,
**Nguyễn Thành An** (`26ai.annt@vinuni.edu.vn`).
The [full initial proposal](../../../general/GSM_Causal_Marketplace_Proposal.md) supplies the
objectives and five-week plan used to report progress. Current work covers only
part of that scope; GSM-dependent conditions remain.

The supplied [GSM Causal Marketplace - Data Requirements.pdf](<../../../GSM Causal Marketplace - Data Requirements.pdf>)
is the source for the data request: eight raw source groups, the latest 12 months
and nearby/control areas. Native schemas and existing log frequency are retained.
The researcher handles schema mapping, joins and features. The requested
Swissmetro choice baseline is pending; current measured work uses TLC and
controlled synthetic/semi-synthetic choices.

| Required item | Editable source | PDF |
|---|---|---|
| Approximately half-page progress update | [Progress_Update.md](Progress_Update.md) | [Progress_Update.pdf](Progress_Update.pdf) |
| Technical PoC report | [POC_Technical_Report.md](POC_Technical_Report.md) | [POC_Technical_Report.pdf](POC_Technical_Report.pdf) |
| Sole contributor's roles, completed work and next tasks | [Team_Allocation.md](Team_Allocation.md) | [Team_Allocation.pdf](Team_Allocation.pdf) |

## Finish before submission

1. Confirm the completed work and the proposed schedule in the allocation
   document. Nguyễn Thành An is the sole contributor and submitter.
2. Review progress against the full proposal in the progress update and
   technical report. Demand/choice validation is evidence C; supply response,
   the market simulator, switchback and GSM business outcomes remain future work.
3. Source publication was verified on 04/10/2026: the public
   [GitHub repository](https://github.com/Muscar1a/gsm-ride-hailing) has the local
   PoC commit `217e1f4` on `main`. The new submission documents are still local;
   include their final PDFs as attachments. No public demo URL is available.
   Attach the supplied Data Requirements PDF as the detailed data request.
4. After editing the three documents, regenerate the PDFs and inspect the page
   images.
5. The sole contributor submits the package by email to TS. Lê Duy Dũng
   (`dung.ld@vinuni.edu.vn`) by Sunday, **04/10/2026**. No email has been sent.

The technical report uses results recorded in [VALIDATION.md](../../../VALIDATION.md).
Simulated choices are method-validation evidence; actual GSM revenue uplift,
policy-value benchmarking and repeated-seed interval calibration remain unmeasured.

## Regenerate PDFs

Use the repository's Python 3.11 environment and an installed Chromium browser.
On the current Windows environment:

```powershell
uv sync --locked --group reports
uv run --group reports python scripts/render_submission.py --browser "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
```

The `reports` dependency group adds Markdown conversion and PDF rendering/text
inspection. Playwright is already in the development group. PDFs are written
beside their Markdown sources; printable HTML, extracted text, page PNGs and
source/PDF hashes go to ignored `.cache/submission_qa/`. Rendering blocks remote
HTTP assets and uses local fonts. The progress/report PDFs use A4 portrait;
the allocation PDF also uses A4 portrait for the solo contributor's responsibilities.

The renderer checks that each page contains text, preserves the document title,
and has no replacement glyphs. Page images still need visual review after edits.
