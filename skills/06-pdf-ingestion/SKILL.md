---
name: pdf-ingestion
description: Build, modify, or review PDF and document ingestion pipelines. Use for medical PDFs, scanned documents, OCR decisions, table extraction, metadata extraction, parser quality grading, structured JSON output, and page-level provenance.
---

# PDF Ingestion

## Rules

- Profile the PDF before extraction.
- Prefer structured/text extraction before OCR.
- Use OCR only when text extraction quality is poor.
- Extract text, tables, and figures separately when possible.
- Preserve page references and source metadata.
- Classify quality as `gold`, `silver`, `bronze`, or `quarantine`.
- Save parser logs and extraction warnings.

## Workflow

1. Detect text-based vs scanned PDF.
2. Extract document metadata.
3. Extract page text with page numbers.
4. Detect tables separately.
5. Validate extraction quality and quarantine bad files.
6. Emit structured JSON suitable for downstream RAG ingestion.
