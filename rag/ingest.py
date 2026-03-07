"""
RAG Ingestion Pipeline
Reads internal architecture/project documents, chunks them, embeds via Gemini,
and upserts into Qdrant Serverless.

Usage:
    python -m rag.ingest --docs-dir ./docs
"""
from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from agents.llm_client import get_embeddings
from config import cfg


CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
EMBEDDING_DIM = 3072  # gemini-embedding-001 output dimension


def _get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=cfg.QDRANT_URL, api_key=cfg.QDRANT_API_KEY)


def ensure_collection(client: QdrantClient) -> None:
    """Create the Qdrant collection if it doesn't already exist."""
    existing = [c.name for c in client.get_collections().collections]
    if cfg.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=cfg.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        print(f"[ingest] Created collection '{cfg.QDRANT_COLLECTION}'")
    else:
        print(f"[ingest] Collection '{cfg.QDRANT_COLLECTION}' already exists — skipping creation")


def load_documents(docs_dir: Path) -> list[dict]:
    """Load all .txt and .md files from docs_dir as raw text chunks."""
    documents = []
    for path in docs_dir.rglob("*"):
        if path.suffix in (".txt", ".md"):
            text = path.read_text(encoding="utf-8")
            documents.append({"source": str(path), "content": text})
    print(f"[ingest] Loaded {len(documents)} documents from '{docs_dir}'")
    return documents


def chunk_documents(documents: list[dict]) -> list[dict]:
    """Split documents into chunks with metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = []
    for doc in documents:
        splits = splitter.split_text(doc["content"])
        for i, split in enumerate(splits):
            chunks.append({
                "id": str(uuid.uuid4()),
                "content": split,
                "metadata": {"source": doc["source"], "chunk_index": i},
            })
    print(f"[ingest] Created {len(chunks)} chunks")
    return chunks


def ingest(docs_dir: Path) -> int:
    """Full ingestion pipeline. Returns number of chunks upserted."""
    client = _get_qdrant_client()
    ensure_collection(client)

    documents = load_documents(docs_dir)
    if not documents:
        print("[ingest] No documents found — nothing to ingest")
        return 0

    chunks = chunk_documents(documents)
    embeddings = get_embeddings()

    # Use LangChain's QdrantVectorStore for easy batch upsert
    texts = [c["content"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    ids = [c["id"] for c in chunks]

    QdrantVectorStore.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        ids=ids,
        url=cfg.QDRANT_URL,
        api_key=cfg.QDRANT_API_KEY,
        collection_name=cfg.QDRANT_COLLECTION,
    )

    print(f"[ingest] Successfully upserted {len(chunks)} chunks into Qdrant")
    return len(chunks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest SRE docs into Qdrant")
    parser.add_argument("--docs-dir", type=Path, default=Path("./docs"), help="Directory of documents to ingest")
    args = parser.parse_args()
    ingest(args.docs_dir)
