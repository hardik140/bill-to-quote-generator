# DATA.md --- Data Model and Database Design

## 1. Data Architecture

The application uses SQLite for local persistence.

``` text
Document
   │
   └── Bill
        │
        ├── Bill Items
        │
        └── Scenarios
              │
              └── Scenario Items
```

------------------------------------------------------------------------

## 2. Core Entities

Entities:

1.  `documents`
2.  `bills`
3.  `bill_items`
4.  `scenarios`
5.  `scenario_items`
6.  `processing_runs`
7.  `generated_files`

------------------------------------------------------------------------

## 3. Entity Relationship Diagram

``` mermaid
erDiagram

    DOCUMENTS ||--o| BILLS : contains
    BILLS ||--|{ BILL_ITEMS : has
    BILLS ||--|{ SCENARIOS : generates
    SCENARIOS ||--|{ SCENARIO_ITEMS : contains
    DOCUMENTS ||--o{ PROCESSING_RUNS : processed_by
    SCENARIOS ||--o{ GENERATED_FILES : exports

    DOCUMENTS {
        uuid id PK
        string original_filename
        string stored_filename
        string mime_type
        integer file_size
        string file_hash
        datetime uploaded_at
        string status
    }

    BILLS {
        uuid id PK
        uuid document_id FK
        string vendor_name
        string vendor_address
        string vendor_gstin
        string invoice_number
        date invoice_date
        string buyer_name
        string buyer_address
        string currency
        decimal subtotal
        decimal tax_total
        decimal grand_total
        string extraction_status
        boolean confirmed
        datetime created_at
        datetime updated_at
    }

    BILL_ITEMS {
        uuid id PK
        uuid bill_id FK
        integer serial_no
        string description
        string hsn_sac
        decimal gst_rate
        decimal quantity
        string unit
        decimal source_rate
        decimal taxable_rate
        decimal line_amount
        decimal tax_amount
        decimal total_amount
        decimal confidence
        boolean user_verified
    }

    SCENARIOS {
        uuid id PK
        uuid bill_id FK
        string scenario_type
        string label
        decimal markup_percent
        string rounding_mode
        decimal subtotal
        decimal tax_total
        decimal grand_total
        string disclaimer
        datetime created_at
    }

    SCENARIO_ITEMS {
        uuid id PK
        uuid scenario_id FK
        uuid source_item_id FK
        string description
        decimal quantity
        string unit
        decimal baseline_rate
        decimal markup_percent
        decimal adjusted_rate
        decimal line_amount
        decimal tax_amount
        decimal total_amount
    }

    PROCESSING_RUNS {
        uuid id PK
        uuid document_id FK
        string processor
        string processor_version
        string status
        datetime started_at
        datetime completed_at
        string error_message
    }

    GENERATED_FILES {
        uuid id PK
        uuid scenario_id FK
        string file_type
        string filename
        string storage_path
        string file_hash
        datetime generated_at
    }
```

------------------------------------------------------------------------

## 4. Document Table

### `documents`

Stores the original uploaded file.

  Column              Type         Required Description
  ------------------- ---------- ---------- -------------------
  id                  UUID              Yes Primary key
  original_filename   TEXT              Yes Original filename
  stored_filename     TEXT              Yes Internal filename
  mime_type           TEXT              Yes MIME type
  file_size           INTEGER           Yes Size in bytes
  file_hash           TEXT              Yes SHA-256 hash
  uploaded_at         DATETIME          Yes Upload time
  status              TEXT              Yes Processing status

### Status

``` text
uploaded
processing
processed
failed
archived
```

------------------------------------------------------------------------

## 5. Bill Table

### `bills`

Stores normalized invoice/bill header information.

Important distinction:

The bill is the **source record**. It must not be overwritten when
scenarios are created.

  Column              Type
  ------------------- ----------
  id                  UUID
  document_id         UUID
  vendor_name         TEXT
  vendor_address      TEXT
  vendor_gstin        TEXT
  invoice_number      TEXT
  invoice_date        DATE
  buyer_name          TEXT
  buyer_address       TEXT
  currency            TEXT
  subtotal            DECIMAL
  tax_total           DECIMAL
  grand_total         DECIMAL
  extraction_status   TEXT
  confirmed           BOOLEAN
  created_at          DATETIME
  updated_at          DATETIME

------------------------------------------------------------------------

## 6. Bill Item Table

### `bill_items`

This is the most important table because it stores each extracted line
item.

Example:

``` json
{
  "description": "A4 Paper Rim 75 GSM",
  "quantity": 1,
  "unit": "RIM",
  "source_rate": "240.00",
  "gst_rate": "18.00"
}
```

### Financial fields

Store monetary values as fixed decimal values.

Do not store money as floating-point numbers.

Recommended database representation:

``` text
DECIMAL(14,2)
```

------------------------------------------------------------------------

## 7. Source vs Tax-Inclusive Pricing

The uploaded invoice may contain columns such as:

``` text
Rate (Incl. of Tax)
Rate
Per
Amount
```

Therefore the data model should distinguish:

``` text
source_rate
taxable_rate
line_amount
tax_amount
total_amount
```

The system should never guess which price is intended when the document
contains conflicting interpretations.

If uncertain:

``` text
user_verified = false
```

and the UI must request confirmation.

------------------------------------------------------------------------

## 8. Scenario Table

### `scenarios`

Each bill can have multiple scenarios.

MVP creates:

``` text
BASELINE
SCENARIO_B
SCENARIO_C
```

### Scenario types

``` text
BASELINE
SIMULATED
```

For B/C:

``` text
scenario_type = SIMULATED
```

### Example

``` json
{
  "scenario_type": "SIMULATED",
  "label": "Scenario B — Internal Estimate",
  "markup_percent": 10,
  "rounding_mode": "nearest_1",
  "disclaimer": "SIMULATED / INTERNAL ESTIMATE — NOT A VENDOR QUOTATION"
}
```

------------------------------------------------------------------------

## 9. Scenario Item Table

Scenario items should be copied from the confirmed baseline at
generation time.

This creates an immutable snapshot.

Example:

``` text
Baseline item:
A4 Paper
Rate: ₹240

Scenario B:
Baseline Rate: ₹240
Markup: 10%
Adjusted Rate: ₹264
```

This prevents later changes to the source bill from silently changing an
already generated scenario.

------------------------------------------------------------------------

## 10. Processing Run Table

### `processing_runs`

Stores OCR/extraction execution information.

Fields:

``` text
id
document_id
processor
processor_version
status
started_at
completed_at
error_message
```

Example:

``` json
{
  "processor": "PaddleOCR",
  "processor_version": "3.x",
  "status": "completed"
}
```

This helps debug extraction problems.

------------------------------------------------------------------------

## 11. Generated File Table

### `generated_files`

Tracks PDFs generated by the application.

Example:

``` json
{
  "file_type": "pdf",
  "filename": "scenario-b.pdf",
  "storage_path": "storage/generated/<bill-id>/scenario-b.pdf"
}
```

------------------------------------------------------------------------

## 12. Recommended Indexes

``` sql
CREATE INDEX idx_documents_uploaded_at
ON documents(uploaded_at);

CREATE INDEX idx_bills_invoice_number
ON bills(invoice_number);

CREATE INDEX idx_bill_items_bill_id
ON bill_items(bill_id);

CREATE INDEX idx_scenarios_bill_id
ON scenarios(bill_id);

CREATE INDEX idx_scenario_items_scenario_id
ON scenario_items(scenario_id);
```

------------------------------------------------------------------------

## 13. Data Lifecycle

``` text
Upload
  ↓
Original document stored
  ↓
OCR processing
  ↓
Extracted candidate data
  ↓
User edits
  ↓
Confirmed source bill
  ↓
Scenario snapshot
  ↓
PDF generation
```

The original upload must never be modified.

------------------------------------------------------------------------

## 14. Auditability

For every financial value, the application should be able to answer:

``` text
Where did this value come from?
```

Possible origins:

``` text
OCR
USER_EDIT
CALCULATED
SCENARIO_GENERATED
```

A future version can add an `field_audit_log` table:

``` text
field_audit_log
----------------
id
entity_type
entity_id
field_name
old_value
new_value
source
changed_at
```

------------------------------------------------------------------------

## 15. Example Complete Data Object

``` json
{
  "bill": {
    "invoice_number": "DSH/26-27/0896",
    "invoice_date": "2026-07-29",
    "vendor_name": "Delhi Stationery House",
    "buyer_name": "G.M.S. Sec-13 HUDA",
    "currency": "INR"
  },
  "items": [
    {
      "description": "A4 Paper Rim 75 GSM",
      "quantity": 1,
      "unit": "RIM",
      "source_rate": 240.00,
      "gst_rate": 18.00,
      "user_verified": true
    }
  ],
  "scenarios": [
    {
      "type": "BASELINE",
      "markup_percent": 0
    },
    {
      "type": "SIMULATED",
      "label": "Scenario B",
      "markup_percent": 10
    },
    {
      "type": "SIMULATED",
      "label": "Scenario C",
      "markup_percent": 20
    }
  ]
}
```

------------------------------------------------------------------------

## 16. Data Integrity Rules

1.  A scenario must reference a confirmed bill.
2.  A scenario item must reference its baseline source item.
3.  A bill cannot be confirmed if mandatory financial fields contain
    invalid values.
4.  Monetary values must use decimal arithmetic.
5.  Scenario calculations must be reproducible from stored inputs.
6.  Generated files must reference the scenario that created them.
7.  Original uploaded documents must remain immutable.
8.  User corrections must not be overwritten by a later OCR run unless
    explicitly requested.
9.  Simulated scenarios must retain their simulation disclaimer.
10. Vendor authenticity information must never be fabricated.

------------------------------------------------------------------------

## 17. Backup

For a local MVP, backup can be implemented by copying:

``` text
data/
storage/uploads/
storage/generated/
```

Recommended future feature:

``` text
Export Backup
    ↓
ZIP
    ├── database.sqlite
    ├── uploads/
    └── generated/
```

------------------------------------------------------------------------

## 18. Data Retention

Default:

-   Keep original uploads.
-   Keep confirmed bills.
-   Keep generated scenarios.
-   Allow manual deletion.

Future version:

-   Automatic cleanup rules.
-   Secure deletion.
-   Encrypted backup.
