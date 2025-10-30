# /workspace/routers/ai.py
"""
Full AI pipeline using a custom Mistral endpoint and internal vector indexing.
No llama_index dependency. Works with your FastAPI auth system.
"""

import os
import json
import numpy as np
import requests
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Query, HTTPException
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Tuple

# === FastAPI Router ===
router = APIRouter(prefix="/ai", tags=["AI"])

# === Config ===
DOCS_DIR = "./docs"
INDEX_PATH = "./vector_index.json"
MISTRAL_BASE_URL = "https://mistral-ai-three.vercel.app/"

# Load SentenceTransformer model (keep small for Heroku)
EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

# === Helper: Load user info ===
from routers import auth_utils, auth_schemas

# === Utility functions ===
def read_documents(docs_dir: str = DOCS_DIR) -> List[Tuple[str, str]]:
    """Read all text documents from directory."""
    docs = []
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
    for root, _, files in os.walk(docs_dir):
        for f in files:
            if f.lower().endswith((".txt", ".md")):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                    content = fp.read().strip()
                    if content:
                        docs.append((f, content))
    return docs


def build_index(docs: List[Tuple[str, str]], save_path: str = INDEX_PATH):
    """Generate embeddings for all docs and save as JSON."""
    print(f"📘 Building index for {len(docs)} documents...")
    data = {"embeddings": [], "meta": []}
    for name, text in docs:
        embedding = EMBED_MODEL.encode([text])[0].tolist()
        data["embeddings"].append(embedding)
        data["meta"].append({"name": name, "text": text[:4000]})
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"✅ Index saved at {save_path}")


def load_index(path: str = INDEX_PATH) -> dict:
    """Load precomputed embeddings."""
    if not os.path.exists(path):
        raise FileNotFoundError("❌ No index found. Build index first.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def retrieve_similar(query: str, index_data: dict, top_k: int = 3) -> List[str]:
    """Return top_k most similar documents by cosine similarity."""
    q_emb = EMBED_MODEL.encode([query])[0].reshape(1, -1)
    doc_embs = np.array(index_data["embeddings"])
    sims = cosine_similarity(q_emb, doc_embs)[0]
    top_ids = np.argsort(sims)[::-1][:top_k]
    return [index_data["meta"][i]["text"] for i in top_ids]


def call_mistral(fullname: str, question: str) -> str:
    """Send prompt to custom Mistral API."""
    url = f"{MISTRAL_BASE_URL}?id={quote_plus(fullname)}&question={quote_plus(question)}"
    try:
        res = requests.get(url, timeout=60)
        res.raise_for_status()
        try:
            data = res.json()
            if isinstance(data, dict):
                for key in ["answer", "response", "text", "result", "data"]:
                    if key in data:
                        return str(data[key])
            return str(data)
        except Exception:
            return res.text
    except Exception as e:
        return f"⚠️ Mistral API Error: {e}"


def query_ai_logic(query: str, fullname: str, top_k: int = 3) -> str:
    """Retrieve context from local index and query Mistral."""
    try:
        index_data = load_index(INDEX_PATH)
    except FileNotFoundError:
        docs = read_documents(DOCS_DIR)
        if not docs:
            return "❌ No documents found for indexing."
        build_index(docs)
        index_data = load_index(INDEX_PATH)

    # Retrieve top matches
    top_docs = retrieve_similar(query, index_data, top_k)
    context = "\n\n".join(top_docs)
    prompt = f"Context:\n{context}\n\nUser ({fullname}) asks:\n{query}"
    return call_mistral(fullname, prompt)


# === FastAPI endpoint ===
@router.get("/query")
async def query_ai(
    q: str = Query(..., description="User query text"),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Query endpoint.
    Fetches user's fullname from /me (auth system),
    retrieves semantic context, and queries custom Mistral AI.
    """
    try:
        fullname = current_user.get("fullname", "Anonymous User")
        print(f"👤 AI Query by: {fullname} | Q: {q}")
        response = query_ai_logic(q, fullname)
        return {"fullname": fullname, "query": q, "answer": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Query Error: {e}")


# === Optional command to manually rebuild index ===
@router.get("/rebuild_index")
async def rebuild_index(current_user: Dict = Depends(auth_utils.get_current_user)):
    """Manually rebuilds document index."""
    fullname = current_user.get("fullname", "System")
    docs = read_documents(DOCS_DIR)
    if not docs:
        return {"status": "no_docs", "message": "No text files found in docs directory."}
    build_index(docs)
    return {"status": "success", "built_by": fullname, "count": len(docs)}