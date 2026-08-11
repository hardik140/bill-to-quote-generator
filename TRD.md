# TRD --- Local Bill-to-Quotation Scenario Generator

## 1. Technical Overview

The system is a local desktop/web application composed of:

``` text
React/Vite Frontend
        ↓
FastAPI Backend
        ↓
Document Processing Pipeline
        ↓
OCR / Table Extraction
        ↓
Normalization + Validation
        ↓
SQLite
        ↓
Scenario Calculation Engine
        ↓
ReportLab PDF Generator
```

The application shall operate without an internet connection.

------------------------------------------------------------------------

## 2. Recommended Technology Stack

### Frontend

-   React
-   Vite
-   TypeScript
-   Tailwind CSS
-   TanStack Table
-   Axios

### Backend

-   Python 3.12+
-   FastAPI
-   Pydantic
-   SQLAlchemy
-   SQLite

### Document Processing

-   PyMuPDF
-   OpenCV
-   Pillow
-   PaddleOCR
-   Optional table extraction module

### PDF

-   ReportLab

### Testing

-   Pytest
-   Playwright
-   Vitest

### Packaging

For MVP:

-   Local FastAPI server.
-   Local Vite production build served through FastAPI or a local
    desktop wrapper.

Possible later packaging:

-   Tauri
-   PyInstaller

------------------------------------------------------------------------

## 3. System Architecture

``` text
┌────────────────────────────────────────────┐
│                 Browser UI                 │
│               React + Vite                 │
└──────────────────────┬─────────────────────┘
                       │ HTTP/JSON
                       ▼
┌────────────────────────────────────────────┐
│                FastAPI API                 │
├────────────────────────────────────────────┤
│ Upload API                                 │
│ Extraction API                             │
│ Bill API                                   │
│ Scenario API                               │
│ PDF API                                    │
└───────────────┬────────────────────────────┘
                │
       ┌────────┴───────────┐
       ▼                    ▼
┌───────────────┐    ┌──────────────────────┐
│ SQLite        │    │ Document Pipeline    │
│ Database      │    │                      │
│               │    │ PDF/Image            │
│ Bills         │    │ → Preprocessing      │
│ Items         │    │ → OCR                │
│ Scenarios     │    │ → Table Parsing      │
│ Documents     │    │ → Normalization      │
└───────────────┘    └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │ Calculation Engine   │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │ ReportLab PDF        │
                     │ Generator             │
                     └──────────────────────┘
```

------------------------------------------------------------------------

## 4. Backend Architecture

Recommended layers:

``` text
app/
├── main.py
├── api/
├── schemas/
├── services/
├── models/
├── repositories/
├── core/
└── utils/
```

### API Layer

Responsible only for:

-   Request validation.
-   Authentication boundary, if added later.
-   Calling services.
-   Returning responses.

### Service Layer

Contains business logic:

-   OCR service.
-   Invoice extraction service.
-   Validation service.
-   Calculation service.
-   Scenario service.
-   PDF service.

### Repository Layer

Responsible for SQLite persistence.

------------------------------------------------------------------------

## 5. Document Processing Pipeline

``` text
Input File
   ↓
File Validation
   ↓
PDF → Image conversion if required
   ↓
Image preprocessing
   ↓
OCR
   ↓
Bounding boxes + text
   ↓
Table detection
   ↓
Column assignment
   ↓
Row reconstruction
   ↓
Field normalization
   ↓
Confidence scoring
   ↓
Human review
```

------------------------------------------------------------------------

## 6. OCR Strategy

OCR should not directly produce final financial records.

Use:

``` text
OCR output
     ↓
Candidate fields
     ↓
Parser
     ↓
Normalizer
     ↓
Validator
     ↓
User confirmation
     ↓
Confirmed invoice
```

For example:

``` text
OCR:
"6 PCS 55.00 279.66"

Parser:
quantity = 6
rate = 55.00
amount = 279.66

Validator:
6 × 46.61 = 279.66

Interpretation:
46.61 may be taxable/unit rate while 55 may be GST-inclusive source rate.

Action:
Flag for user review.
```

This is important because the uploaded invoices can contain both
`Rate (Incl. of Tax)` and `Rate`, so the application must understand the
exact column semantics instead of assuming the first number is always
the final unit price.

------------------------------------------------------------------------

## 7. Financial Calculation Engine

Use Python `Decimal`.

Example conceptual implementation:

``` python
from decimal import Decimal

line_amount = quantity * unit_price
tax_amount = line_amount * tax_rate / Decimal("100")
total = line_amount + tax_amount
```

Never use floating-point arithmetic for monetary calculations.

### Source Data Principle

The system must preserve:

-   Original extracted values.
-   User-corrected values.
-   Calculation basis.

This prevents accidental overwriting of source information.

------------------------------------------------------------------------

## 8. Scenario Calculation

Scenario configuration:

``` json
{
  "scenario_b_markup_percent": 10,
  "scenario_c_markup_percent": 20,
  "rounding": "nearest_1"
}
```

Rate calculation:

``` text
scenario_rate = baseline_rate × (1 + markup / 100)
```

The system shall calculate scenario values from the confirmed baseline,
not from OCR output.

------------------------------------------------------------------------

## 9. API Design

### POST /api/documents/upload

Upload a PDF/image.

Response:

``` json
{
  "document_id": "uuid",
  "status": "uploaded"
}
```

### POST /api/documents/{id}/extract

Start local extraction.

Response:

``` json
{
  "document_id": "uuid",
  "status": "completed",
  "bill_id": "uuid"
}
```

### GET /api/bills/{id}

Returns extracted/confirmed bill.

### PUT /api/bills/{id}

Updates bill header information.

### PUT /api/bills/{id}/items/{item_id}

Updates an item.

### POST /api/bills/{id}/confirm

Confirms the source data.

### POST /api/bills/{id}/scenarios

Request:

``` json
{
  "scenario_b_markup_percent": 10,
  "scenario_c_markup_percent": 20,
  "rounding": "nearest_1"
}
```

Response:

``` json
{
  "scenario_ids": [
    "uuid-a",
    "uuid-b",
    "uuid-c"
  ]
}
```

### GET /api/scenarios/{id}

Returns scenario details.

### POST /api/scenarios/{id}/pdf

Generates the PDF.

### GET /api/documents/{id}/files

Lists locally generated files.

------------------------------------------------------------------------

## 10. Validation Rules

### Quantity

``` text
quantity >= 0
```

### Rate

``` text
rate >= 0
```

### GST

``` text
0 <= GST <= 100
```

### Markup

``` text
markup >= 0
```

Optional configurable maximum should be available.

### Currency

Default:

`INR`

------------------------------------------------------------------------

## 11. Security Architecture

Even though the application is local:

-   Validate file extensions.
-   Validate MIME type.
-   Enforce maximum file size.
-   Store uploads outside executable directories.
-   Generate random filenames.
-   Sanitize PDF output filenames.
-   Never execute uploaded content.
-   Restrict API to localhost by default.
-   Disable CORS for arbitrary origins.
-   Do not expose the FastAPI port publicly.
-   Avoid external telemetry.

------------------------------------------------------------------------

## 12. File Storage

``` text
storage/
├── uploads/
│   └── <uuid>.pdf
├── images/
│   └── <uuid>/
├── generated/
│   └── <bill-id>/
│       ├── baseline.pdf
│       ├── scenario-b.pdf
│       └── scenario-c.pdf
└── temp/
```

------------------------------------------------------------------------

## 13. Database

SQLite is sufficient for one local user.

Recommended SQLAlchemy configuration:

``` text
SQLite
  ↓
SQLAlchemy
  ↓
Repository layer
  ↓
Service layer
```

Enable foreign keys.

Use transactions for:

-   Bill confirmation.
-   Scenario creation.
-   Item updates.

------------------------------------------------------------------------

## 14. PDF Architecture

PDF generation should be template-driven.

``` text
Quote Data
    ↓
Template Renderer
    ↓
Header
    ↓
Item Table
    ↓
Tax Summary
    ↓
Disclaimer
    ↓
Footer
    ↓
PDF
```

Scenario B/C must visibly contain:

`SIMULATED / INTERNAL ESTIMATE — NOT A VENDOR QUOTATION`

Do not copy real vendor signatures, GST certificates, bank details,
seals, or other authenticity markers into simulated documents.

------------------------------------------------------------------------

## 15. Testing Strategy

### Unit Tests

Test:

-   Currency arithmetic.
-   GST calculations.
-   Markup calculations.
-   Rounding.
-   Quantity × rate.
-   Total reconciliation.
-   Validation.

### OCR Tests

Maintain sample fixtures:

``` text
tests/fixtures/
├── printed_invoice_01.jpg
├── printed_invoice_02.pdf
├── poor_photo_01.jpg
└── handwritten_quote_01.jpg
```

### Integration Tests

Test:

``` text
Upload
→ Extract
→ Edit
→ Confirm
→ Generate Scenario
→ Generate PDF
```

### UI Tests

Playwright:

-   Upload.
-   Review.
-   Edit.
-   Scenario configuration.
-   PDF generation.

------------------------------------------------------------------------

## 16. Performance Targets

For a typical laptop:

  Operation                                         Target
  ---------------------- ---------------------------------
  Upload                                           \<2 sec
  Image preprocessing                         \<5 sec/page
  OCR                      \<30 sec for typical 1--3 pages
  Database operation                              \<500 ms
  Scenario calculation                             \<1 sec
  PDF generation                                   \<5 sec

Actual OCR performance depends heavily on hardware and document quality.

------------------------------------------------------------------------

## 17. Deployment

### Development

``` bash
backend:
uvicorn app.main:app --reload

frontend:
npm run dev
```

### Production Local

``` text
React build
      ↓
FastAPI serves static frontend
      ↓
localhost
```

Recommended address:

``` text
http://127.0.0.1:8000
```

------------------------------------------------------------------------

## 18. Future Architecture

If the project later becomes multi-user:

``` text
Reverse Proxy
      ↓
Frontend
      ↓
API
      ↓
PostgreSQL
      ↓
Object Storage
      ↓
Background Workers
      ↓
OCR Queue
```

The MVP should not introduce this complexity prematurely.
