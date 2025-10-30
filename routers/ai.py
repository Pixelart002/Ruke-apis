# File: routers/ai.py

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import requests
from llama_index.core import VectorStoreIndex, Document, ServiceContext, SimpleDirectoryReader
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SimpleNodeParser

# Router
router = APIRouter(prefix="/ai", tags=["AI"])

# --- Mongo connection is already globally available ---
# Assume a shared instance like `db = get_database()` is imported in startup.py or similar
# You can access it via global import or dependency if needed later for chat history, etc.

# --- Request schema ---
class AIQuery(BaseModel):
    user_id: str
    query: str


# --- Llama Index setup ---
# In production, you'd persist your index in Mongo or disk.
# Here we initialize a minimal in-memory index to demonstrate structure.

# --- Embedding + Context ---
embedding_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
service_context = ServiceContext.from_defaults(embed_model=embedding_model)
node_parser = SimpleNodeParser()

# Sample documents (could come from Mongo or any source)
documents = [
    Document(text="YUKU Protocol powers mission control for autonomous AI coordination."),
    Document(text="Mistral endpoint handles conversational AI reasoning requests."),
    Document(text="Flux Schnell API is used for ultra-fast image generation."),
]

# Build the index
nodes = node_parser.get_nodes_from_documents(documents)
index = VectorStoreIndex(nodes, service_context=service_context)


# --- Helper: Query Mistral API ---
def call_mistral(user_id: str, question: str):
    try:
        question_param = question.replace(" ", "+")
        url = f"https://mistral-ai-three.vercel.app/?id={user_id}&question={question_param}"
        res = requests.get(url, timeout=25)
        if res.status_code == 200:
            return res.text.strip()
        else:
            return f"[Error {res.status_code}] Mistral endpoint failed."
    except Exception as e:
        return f"[Exception] {str(e)}"


# --- AI Router Endpoint ---
@router.post("/chat")
def chat_with_ai(payload: AIQuery):
    """
    Hybrid AI Chat Endpoint combining:
    1. Context retrieval via LlamaIndex.
    2. Reasoning + generation via your custom Mistral endpoint.
    """

    try:
        # --- Step 1: Retrieve relevant context ---
        query_engine = index.as_query_engine(similarity_top_k=2)
        context_result = query_engine.query(payload.query)
        context_text = str(context_result.response)

        # --- Step 2: Combine with user query ---
        composed_prompt = (
            f"Context:\n{context_text}\n\n"
            f"User Query:\n{payload.query}\n\n"
            f"Answer concisely with reasoning using the given context."
        )

        # --- Step 3: Ask Mistral ---
        ai_response = call_mistral(payload.user_id, composed_prompt)

        # --- Step 4: Return structured output ---
        return {
            "user_id": payload.user_id,
            "query": payload.query,
            "context_used": context_text,
            "ai_response": ai_response
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))