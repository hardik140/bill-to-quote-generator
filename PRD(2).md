# PRD --- Local Bill-to-Quotation Scenario Generator

## 1. Document Information

-   **Project:** Local Bill-to-Quotation Scenario Generator
-   **Version:** 1.0
-   **Status:** Draft
-   **Deployment:** Local machine only
-   **Users:** Single authorized user
-   **Primary input:** Bill/invoice PDF, JPG, PNG
-   **Primary output:** Three clearly labelled quotation/estimate PDFs

> **Compliance note:** The application is designed for internal
> procurement, budgeting, comparison, and scenario analysis. Scenario B
> and Scenario C must be explicitly labelled as simulated/internal
> estimates and must not impersonate real vendors or create fabricated
> vendor credentials, GST registrations, signatures, seals, or other
> authenticity indicators.

------------------------------------------------------------------------

## 2. Product Overview

The application allows a user to upload a photograph or PDF of a
bill/invoice. The system extracts vendor, invoice, item, quantity,
price, GST, and total information using local OCR and table/document
processing.

After the extracted information is reviewed and confirmed by the user,
the application creates:

1.  **Source Quote / Baseline** --- prices and quantities derived from
    the uploaded document.
2.  **Scenario B** --- baseline prices adjusted using a user-defined
    markup.
3.  **Scenario C** --- baseline prices adjusted using a second
    user-defined markup.

The generated scenario documents are for internal comparison and
budgeting and must contain a visible
`SIMULATED / INTERNAL ESTIMATE — NOT A VENDOR QUOTATION` notice for
Scenario B/C.

------------------------------------------------------------------------

## 3. Problem Statement

Bills and quotations are often received as paper documents or scans.
Manually entering every item into a spreadsheet or quotation template is
slow and error-prone.

The product solves:

-   Manual transcription of invoice line items.
-   Difficulty extracting tables from photographed bills.
-   Repeated calculation of quantities, prices, GST, and totals.
-   Repeated creation of comparison/estimate documents.
-   Need for a local application where sensitive documents remain on the
    user's computer.

------------------------------------------------------------------------

## 4. Goals

### Primary Goals

-   Upload PDF/JPG/PNG documents.
-   Extract structured invoice data locally.
-   Detect and parse line-item tables.
-   Allow complete human review and correction.
-   Calculate totals deterministically.
-   Generate three scenario documents.
-   Export each scenario as PDF.
-   Keep uploaded documents and generated files local.
-   Maintain an audit trail of extracted and manually corrected values.

### Secondary Goals

-   Support poor-quality photographs.
-   Support Hindi/English mixed stationery descriptions where practical.
-   Support GST-inclusive and GST-exclusive pricing.
-   Support configurable markup percentages.
-   Support configurable rounding.
-   Allow re-opening previously processed documents.

------------------------------------------------------------------------

## 5. Non-Goals

The MVP will not:

-   Create fake real-world vendor identities.
-   Generate fake GSTIN/PAN/bank details.
-   Generate fabricated signatures or seals.
-   Represent simulated scenarios as genuine third-party quotations.
-   Automatically send quotations to third parties.
-   Require cloud AI APIs.
-   Implement multi-user authentication.
-   Implement online procurement.
-   Automatically make purchasing decisions.

------------------------------------------------------------------------

## 6. Target User

### Primary User

A single authorized user operating the application on a Windows
desktop/laptop.

### User Characteristics

-   Can upload photos/PDFs.
-   Can verify extracted data.
-   Needs minimal technical knowledge.
-   Wants quick generation of internal estimates/comparison documents.

------------------------------------------------------------------------

## 7. Core User Journey

``` text
Open Application
      ↓
Upload PDF/Image
      ↓
Document Preprocessing
      ↓
OCR + Table Extraction
      ↓
Structured Invoice Data
      ↓
Human Review/Edit
      ↓
Confirm Source Data
      ↓
Configure Scenario Markups
      ↓
Calculate Scenarios
      ↓
Preview
      ↓
Generate PDFs
      ↓
Save Locally
```

------------------------------------------------------------------------

## 8. Functional Requirements

### FR-01 --- File Upload

The system shall accept:

-   PDF
-   JPG
-   JPEG
-   PNG

MVP limits:

-   Maximum file size: configurable, default 20 MB.
-   Multiple-page PDFs supported.
-   One document processed at a time.

### FR-02 --- Document Preprocessing

The system shall support:

-   Rotation correction.
-   Deskewing.
-   Resolution normalization.
-   Contrast enhancement.
-   Noise reduction.
-   Cropping/region detection.
-   Page-by-page processing for PDFs.

### FR-03 --- OCR

The system shall extract:

-   Vendor name.
-   Vendor address.
-   GSTIN, when present.
-   Invoice number.
-   Invoice date.
-   Buyer name/address.
-   Item descriptions.
-   HSN/SAC, when present.
-   GST rate.
-   Quantity.
-   Unit.
-   Unit rate.
-   Taxable amount.
-   Tax amount.
-   Total.

OCR confidence shall be stored for extracted fields where supported.

### FR-04 --- Table Extraction

The system shall identify:

-   Serial number.
-   Description.
-   HSN/SAC.
-   GST rate.
-   Quantity.
-   Rate.
-   Unit.
-   Amount.

The parser must not assume that every bill has the same column order.

### FR-05 --- Human Review

The user shall be able to edit every extracted field.

Each item shall support:

-   Edit description.
-   Edit quantity.
-   Edit unit.
-   Edit rate.
-   Edit GST rate.
-   Add item.
-   Delete item.
-   Reorder item.

The application shall clearly indicate low-confidence fields.

### FR-06 --- Calculation Engine

All financial calculations shall be performed by deterministic
application code.

The system shall calculate:

``` text
line_subtotal = quantity × unit_price

taxable_subtotal = Σ line_subtotal

tax = taxable_subtotal × tax_rate / 100

grand_total = taxable_subtotal + tax + other_adjustments
```

The calculation engine shall use decimal arithmetic rather than binary
floating-point arithmetic for money.

### FR-07 --- Baseline Scenario

Scenario A shall preserve the confirmed source values.

Label:

`SOURCE / BASELINE — DERIVED FROM UPLOADED DOCUMENT`

### FR-08 --- Scenario B

The user shall enter a markup percentage.

Example:

``` text
Markup = 10%

Adjusted Rate = Source Rate × 1.10
```

The generated document must be labelled:

`SIMULATED / INTERNAL ESTIMATE — NOT A VENDOR QUOTATION`

### FR-09 --- Scenario C

The user shall enter a second markup percentage.

Example:

``` text
Markup = 20%

Adjusted Rate = Source Rate × 1.20
```

The same simulation notice shall be displayed prominently.

### FR-10 --- Rounding

The system shall support:

-   No rounding.
-   Nearest ₹1.
-   Nearest ₹5.
-   Nearest ₹10.

The rounding policy shall be stored with the scenario.

### FR-11 --- PDF Generation

The system shall generate:

-   Source/Baseline PDF.
-   Scenario B PDF.
-   Scenario C PDF.

PDFs shall contain:

-   Document title.
-   Scenario type.
-   Date generated.
-   Line items.
-   Quantity.
-   Rate.
-   Amount.
-   Tax summary.
-   Grand total.
-   Simulation disclaimer where applicable.

### FR-12 --- Local Storage

All data shall remain on the local machine.

Storage locations:

``` text
storage/
├── uploads/
├── processed/
└── generated/
```

### FR-13 --- History

The user shall be able to see:

-   Uploaded document name.
-   Processing date.
-   Vendor.
-   Invoice number.
-   Baseline total.
-   Number of scenarios generated.

------------------------------------------------------------------------

## 9. User Interface Requirements

### Dashboard

Components:

-   Upload area.
-   Recent documents.
-   Search/filter.
-   Open previous document.

### Extraction Review

Two-panel design:

``` text
Left: Original document preview
Right: Extracted structured data
```

### Scenario Configuration

Fields:

-   Scenario B markup.
-   Scenario C markup.
-   Tax handling.
-   Rounding.
-   PDF template.

### Result Screen

Show:

  Scenario            Total Status
  ----------------- ------- -----------
  Source/Baseline        ₹X Source
  Scenario B             ₹Y Simulated
  Scenario C             ₹Z Simulated

Actions:

-   Preview.
-   Generate PDF.
-   Open output folder.

------------------------------------------------------------------------

## 10. Non-Functional Requirements

### Performance

Target on a modern laptop:

-   UI response: \< 200 ms for normal interactions.
-   OCR: target \< 30 seconds for a typical 1--3 page bill.
-   PDF generation: target \< 5 seconds.
-   No network dependency.

### Reliability

-   Never silently change user-confirmed financial values.
-   Preserve original upload.
-   Preserve extracted version.
-   Preserve final confirmed version.
-   Recalculate totals after every relevant edit.

### Privacy

-   No document upload to external services.
-   No external telemetry in MVP.
-   Local-only storage.
-   Optional encrypted local database in a later release.

### Usability

-   Desktop-first.
-   Responsive layout.
-   Clear validation messages.
-   Keyboard-friendly tables.

------------------------------------------------------------------------

## 11. Error Handling

Examples:

### OCR Failure

Display:

`Unable to confidently extract this document. Please review or enter the fields manually.`

### Missing Quantity

Flag the row:

`Quantity required`

### Invalid Rate

Reject:

`Rate must be a valid non-negative monetary value.`

### Calculation Mismatch

Display:

`Extracted total differs from calculated total. Please verify the source document.`

------------------------------------------------------------------------

## 12. Acceptance Criteria

The MVP is complete when:

-   A user can upload a photographed bill.
-   OCR extracts the majority of visible fields.
-   The user can correct extraction errors.
-   The application calculates line totals correctly.
-   The baseline total can be verified against the source.
-   Two configurable internal scenarios can be generated.
-   Scenario B/C are clearly labelled simulated estimates.
-   PDFs are generated successfully.
-   Everything works without internet access.
-   Application data survives restart.

------------------------------------------------------------------------

## 13. Future Enhancements

-   Batch processing.
-   Excel export.
-   Multiple PDF templates.
-   Automatic table confidence visualization.
-   Local ML model for better handwritten text recognition.
-   Vendor/product master database.
-   Price history.
-   Category-specific markup rules.
-   Local encrypted database.
-   Backup/restore.
