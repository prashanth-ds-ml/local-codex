---
name: rag-pipeline
description: Build, modify, or review retrieval-augmented generation systems. Use for ingestion, chunking, embeddings, vector search, BM25 or hybrid search, reranking, citations, answer synthesis, retrieval evaluation, and RAG logging.
---

# RAG Pipeline

## Rules

- Separate ingestion, indexing, retrieval, generation, and evaluation.
- Preserve source metadata at every stage.
- Every chunk should include `document_id`, source, page or location, section when available, and chunk index.
- Do not generate final answers without retrieved context.
- Include citations wherever answers depend on retrieved sources.
- Log query, retrieved chunks, scores, prompt, model, and answer.

## Required Tests

- Chunk schema validation
- Retrieval returns expected source for known query
- Empty retrieval is handled safely
- Answer includes citations when context is used
- Retrieval or answer quality regression case when changing search logic
