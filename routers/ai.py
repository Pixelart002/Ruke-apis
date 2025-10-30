# router.py
from typing import List, Optional
import os
import json
import requests
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel

# LlamaIndex imports (may differ by version)
from llama_index import (
    SimpleDirectoryReader,
    ServiceContext,
    LLMPredictor,
    GPTVectorStoreIndex,
    StorageContext,
    load_index_from_storage,
    Document
)
from llama_index.embeddings import SentenceTransformerEmbeddings

# If your llama_index version uses different module names, adapt these imports.
# See official docs for exact import paths. 2

# --------------------
# CONFIG
# --------------------
MISTRAL_BASE = "https://mistral-ai-three.vercel.app/?id={user_id}&question={question_param}"
# Directory to persist index (adjust if you want in-memory)
INDEX_DIR = "./index_store"

# Sentence-transformers model (local embeddings)
SENTENCE_MODEL = "all-MiniLM-L6-v2"

# --------------------
# FastAPI app
# --------------------
app = FastAPI(title="LlamaIndex + Mistral Router")

# --------------------
# Pydantic models
# --------------------
class IngestRequest(BaseModel):
    texts: List[str]            # list of text documents to ingest
    doc_ids: Optional[List[str]] = None

class QueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = 3

# --------------------
# Custom LLM wrapper for Mistral endpoint
# Implements the minimal LlamaIndex LLM interface used by LLMPredictor.
# This class sends synchronous HTTP GET to your endpoint and returns text.
# --------------------
from llama_index.llms.base import LLM
from llama_index.llms.schema import LLMMetadata, Generation, LLMResult, Message

class MistralLLM(LLM):
    """
    Minimal custom LLM wrapper that calls your Mistral endpoint.
    """
    def __init__(self, base_url: str = MISTRAL_BASE, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(name="mistral-custom-endpoint")

    def _call(self, prompt: str, **kwargs) -> str:
        """
        Synchronous call. Some LlamaIndex versions call `predict` or `_call`.
        This implementation handles the common cases; if your version
        requires `predict` instead, add a thin wrapper.
        """
        # build url: replace placeholders safely
        user_id = kwargs.get("user_id", "llama_index_user")
        # naive url-encoding of question param
        q = str(prompt).replace(" ", "+").replace("#", "").replace("&", "and")
        url = self.base_url.format(user_id=user_id, question_param=q)
        try:
            res = requests.get(url, timeout=self.timeout)
            res.raise_for_status()
            # Expecting plain text response containing the model's answer
            text = res.text
            return text
        except requests.RequestException as e:
            raise RuntimeError(f"Mistral endpoint error: {e}")

    # Some LlamaIndex versions expect generate() returning an LLMResult
    def generate(self, prompts: List[str], **kwargs) -> LLMResult:
        generations = []
        for p in prompts:
            text = self._call(p, **kwargs)
            gen = Generation(text=text)
            generations.append([gen])
        # Message schema required by some versions
        message = Message(role="assistant", content=generations[0][0].text)
        return LLMResult(generations=generations, llm_output={"model_name":"mistral-custom-endpoint"})

# --------------------
# Helper to create ServiceContext + Index objects
# --------------------
def create_service_context():
    # embeddings: local sentence-transformers
    embed = SentenceTransformerEmbeddings(model_name=SENTENCE_MODEL)
    # llama_index LLMPredictor uses an LLM object
    mistral_llm = MistralLLM()
    llm_predictor = LLMPredictor(llm=mistral_llm)
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor, embed_model=embed)
    return service_context

def ensure_index_store_dir():
    if not os.path.exists(INDEX_DIR):
        os.makedirs(INDEX_DIR, exist_ok=True)

# --------------------
# Ingest endpoint (POST /ingest)
# Accepts a JSON: { "texts": ["doc1", "doc2"], "doc_ids": ["id1","id2"] }
# --------------------
@app.post("/ingest")
def ingest_docs(req: IngestRequest):
    try:
        service_context = create_service_context()
        docs = []
        for i, t in enumerate(req.texts):
            metadata = {"source": (req.doc_ids[i] if req.doc_ids and i < len(req.doc_ids) else None)}
            docs.append(Document(text=t, metadata=metadata))
        # Build a vector index in memory, then persist
        index = GPTVectorStoreIndex.from_documents(docs, service_context=service_context)
        ensure_index_store_dir()
        index.storage_context.persist(persist_dir=INDEX_DIR)
        return {"status":"ok", "message":"ingested", "num_docs": len(docs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --------------------
# Build index from local directory of plain text files (optional helper)
# GET /build_from_dir?dir=./data
# --------------------
@app.get("/build_from_dir")
def build_from_dir(dir: str = "./data"):
    try:
        service_context = create_service_context()
        reader = SimpleDirectoryReader(input_dir=dir)
        docs = reader.load_data()
        index = GPTVectorStoreIndex.from_documents(docs, service_context=service_context)
        ensure_index_store_dir()
        index.storage_context.persist(persist_dir=INDEX_DIR)
        return {"status":"ok", "num_docs": len(docs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --------------------
# Query endpoint (POST /query)
# --------------------
@app.post("/query")
def query_index(req: QueryRequest):
    try:
        # load index from disk if exists, else error
        if not os.path.exists(INDEX_DIR):
            raise HTTPException(status_code=404, detail="Index not found. Ingest first.")
        storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
        service_context = create_service_context()
        index = load_index_from_storage(storage_context, service_context=service_context)
        q = req.query
        # Simple query: use index.as_query_engine()
        query_engine = index.as_query_engine(service_context=service_context, similarity_top_k=req.top_k)
        response = query_engine.query(q)
        # response might be an object; coerce to string
        return {"answer": str(response), "raw": repr(response)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --------------------
# Health check
# --------------------
@app.get("/health")
def health():
    return {"status":"ok"}