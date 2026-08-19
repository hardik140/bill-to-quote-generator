# Local Bill-to-Quotation Scenario Generator

Upload a photographed or scanned bill/invoice (PDF/JPG/PNG), review the
locally-OCR'd line items, confirm them, and generate three PDFs: a
Source/Baseline quote and two clearly-labelled `SIMULATED / INTERNAL
ESTIMATE` scenarios at configurable markups. Everything runs on
`127.0.0.1` — no internet connection or cloud AI API is used at any point.

See [`PRD(2).md`](PRD(2).md), [`TRD.md`](TRD.md), and [`DATA.md`](DATA.md)
for the full product/technical/data specs this implements.

## Stack

- **Backend:** FastAPI + SQLAlchemy + SQLite, Python 3.12
- **OCR/preprocessing:** pytesseract (Tesseract-OCR) + PyMuPDF + OpenCV —
  substituted for the TRD's suggested PaddleOCR because Tesseract and
  poppler were already installed on this machine and PaddleOCR is a much
  heavier, riskier install on Windows/Py3.12. Everything else in the TRD
  stack is used as specified.
- **PDF generation:** ReportLab
- **Frontend:** React + Vite + TypeScript + Tailwind CSS v4 + TanStack
  Table v8 + Axios + React Router
- **Money:** Python `Decimal` throughout — never binary floating point

## Project layout

```
backend/
  app/
    api/            FastAPI routers (documents, bills, scenarios)
    services/        preprocessing, OCR, table/field parsing, calculation,
                     scenario engine, PDF generation, storage
    models/          SQLAlchemy models (documents, bills, bill_items,
                     scenarios, scenario_items, processing_runs, generated_files)
    schemas/         Pydantic request/response models
    repositories/    thin DB access layer
    core/            settings, DB session
  storage/           uploads/ images/ generated/ temp/  (gitignored contents)
  data/              app.db (SQLite, gitignored)
  tests/             pytest suite incl. a full upload->PDF integration test
frontend/
  src/
    pages/           Dashboard, ExtractionReview, ScenarioConfig, ResultScreen
    components/      BillItemsTable (TanStack Table), Layout, ConfidenceDot
    api/             typed Axios client
    types/           TS types mirroring the backend Pydantic schemas
```

## Prerequisites

Already expected on this machine (adjust paths in
`backend/app/core/config.py` if yours differ):

- Python 3.12+
- Node.js 18+
- Tesseract-OCR binary (`APP_TESSERACT_CMD`, default
  `C:\Users\91981\Tesseract-OCR\tesseract.exe`)
- Poppler `bin/` directory (`APP_POPPLER_PATH`) — used as a fallback path
  hint; primary PDF rendering goes through PyMuPDF and doesn't need it.

## Setup

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

## Running (development)

Two terminals:

```bash
# Terminal 1 - backend (creates SQLite tables on first run)
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 - frontend (proxies /api and /files to the backend)
cd frontend
npm run dev
```

Open **http://127.0.0.1:5173**.

## Running (production-local)

Per TRD §17, build the frontend and serve it from FastAPI so there's a
single process on one port:

```bash
cd frontend && npm run build
```

Then point a `StaticFiles` mount (or a simple catch-all route) in
`backend/app/main.py` at `frontend/dist`, and run just the backend on
`http://127.0.0.1:8000`. (Not wired up by default in this checkout so that
`npm run dev`'s hot-reload stays fast during development.)

## Tests

```bash
cd backend
python -m pytest -q
```

27 tests, including:
- `test_money.py` / `test_calculation_service.py` — Decimal rounding and
  line/tax/total math
- `test_scenario_service.py` — baseline immutability, markup application,
  rounding, snapshot independence from later source-bill edits
- `test_table_parser.py` — synthetic OCR fixtures proving column-order
  independence (FR-04): the same data parses correctly whether Amount/Rate
  come before or after Qty/Unit/GST in the header row
- `test_integration_e2e.py` — full HTTP flow through a real generated PDF
  invoice: upload → extract (real Tesseract OCR) → review/edit → confirm
  → generate 3 scenarios → generate 3 PDFs → verify disclaimer text via
  PyMuPDF text extraction

`backend/scripts/generate_fixture_invoice.py` regenerates the test fixture
at `backend/tests/fixtures/printed_invoice_01.pdf`.

- **Simplified Product Name + Rate Extraction Scope.** The extraction pipeline,
  API, and UI extract only each item's Product Name and printed Rate. All vendor,
  buyer, and invoice header fields, as well as HSN, Qty, Unit, and GST columns,
  are bypassed. Items default internally to `quantity=1` and `gst_rate=0.00`,
  meaning the bill total is the direct sum of item rates while preserving full
  compatibility with the existing SQLite schema and `Decimal` calculation engine.
  Leading OCR serial numbers (e.g. "1 Camlin Marker") are automatically stripped.
- **Simplified PDF Layout.** Generated PDFs render clean `#`, `Product`, `Rate`,
  and single `Total` summaries with appropriate simulation disclaimers and
  rounding policies, without fabricated or distracting header blocks.
- **Grid-line removal before OCR.** Tesseract's layout analysis silently
  drops entire rows of a ruled/bordered table — verified empirically
  against the fixture invoice (2 of 3 item rows vanished with no error).
  `preprocessing_service._remove_grid_lines` erases ruling lines via
  morphological opening (kernel size proportional to image dimensions, so
  large bold headings aren't damaged) before deskew/CLAHE/denoise run.
- **Skew estimation via projection profile, not `minAreaRect`.**
  `cv2.minAreaRect` on the raw foreground point cloud reported ~4° of
  skew on a perfectly level, digitally-rendered page (unreliable for
  sparse mixed layouts — a title plus a few header lines plus a table).
  Replaced with a coarse-to-fine search that maximizes horizontal
  projection variance, which correctly reports 0°.
- **Cell/column clustering threshold.** OCR column-header gaps run as low
  as ~3x average character width while in-phrase word gaps run ~0.7-0.8x;
  the gap threshold sits between the two so multi-word descriptions stay
  one cell while adjacent columns (e.g. "S.No" next to "Description")
  don't get merged.
- **Tax-inclusive vs. tax-exclusive rate columns.** Per TRD §6, when a
  bill only prints a "Rate (Incl. of Tax)" column, the system does not
  guess the exclusive basis — it derives one and flags the item as
  low-confidence/ambiguous for mandatory human review rather than
  silently trusting either number.
- **Scenario snapshots are immutable.** `scenario_items` are copied from
  the confirmed bill at generation time; later edits to `bill_items`
  (blocked once confirmed, but defensively) cannot retroactively change an
  already-generated scenario or PDF.
