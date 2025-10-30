# routers/ai.py
import os
import json
import time
import logging
import requests
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Optional

# Updated llama_index imports for 2024+
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, PromptTemplate, Settings
from llama_index.core.llms import LLM

# Import your auth utilities (you already have this)
from auth import utils as auth_utils
from auth import schemas as auth_schemas

router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------- #
# 🔹 Custom LLM for Mistral API #
# ----------------------------- #

class MistralCustomLLM(LLM):
    """
    Custom LlamaIndex-compatible LLM wrapper for your Mistral endpoint:
    https://mistral-ai-three.vercel.app/?id={fullname}&question={question}
    """

    def __init__(self, fullname: str, base_url: str = "https://mistral-ai-three.vercel.app", timeout: int = 30):
        self.fullname = fullname
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, prompt: str, **kwargs) -> str:
        """Main synchronous call method for LlamaIndex."""
        encoded_name = quote_plus(self.fullname)
        encoded_question = quote_plus(prompt)
        url = f"{self.base_url}/?id={encoded_name}&question={encoded_question}"

        try:
            logger.info(f"[MistralLLM] Sending request for {self.fullname}")
            res = requests.get(url, timeout=self.timeout)
            res.raise_for_status()

            # Try parsing JSON
            try:
                data = res.json()
                if isinstance(data, dict):
                    for key in ("answer", "response", "text", "data"):
                        if key in data:
                            return data[key]
                    return json.dumps(data)
                elif isinstance(data, str):
                    return data
            except Exception:
                return res.text

        except Exception as e:
            logger.error(f"Error calling Mistral endpoint: {e}")
            raise HTTPException(status_code=500, detail=f"AI endpoint error: {str(e)}")

    # LlamaIndex expects this
    async def acomplete(self, prompt: str, **kwargs):
        return self.complete(prompt, **kwargs)


# ----------------------------------- #
# 🔹 Index Builder + Query Management #
# ----------------------------------- #

INDEX_PATH = "data/vector_index.json"
DOCS_DIR = "data/docs"

def get_index(fullname: str) -> VectorStoreIndex:
    """Load or build the index for this user."""
    llm = MistralCustomLLM(fullname=fullname)

    Settings.llm = llm  # globally apply our custom model
    Settings.chunk_size = 512

    if os.path.exists(INDEX_PATH):
        logger.info("Loading existing index...")
        return VectorStoreIndex.load_from_disk(INDEX_PATH)
    else:
        logger.info("No index found — creating from docs...")
        os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
        if not os.path.exists(DOCS_DIR):
            raise HTTPException(status_code=404, detail="Docs directory not found")
        documents = SimpleDirectoryReader(DOCS_DIR).load_data()
        index = VectorStoreIndex.from_documents(documents)
        index.storage_context.persist(persist_dir=os.path.dirname(INDEX_PATH))
        return index


# --------------------------- #
# 🔹 FastAPI Router Endpoint  #
# --------------------------- #

@router.get("/ai/query")
async def query_ai(
    q: str = Query(..., description="Your question to the AI"),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Query the AI index using your custom Mistral endpoint (fullname as user ID).
    """
    fullname = current_user.get("fullname", "Unknown")
    logger.info(f"AI Query by: {fullname} | Q: {q}")

    index = get_index(fullname)
    query_engine = index.as_query_engine()
    response = query_engine.query(q)

    # Extract response text robustly
    try:
        if hasattr(response, "response"):
            text = response.response
        elif hasattr(response, "get_formatted_response"):
            text = response.get_formatted_response()
        else:
            text = str(response)
    except Exception:
        text = str(response)

    return {"fullname": fullname, "query": q, "answer": text}


# ---------------------- #
# 🔹 Example Test Route  #
# ---------------------- #

@router.get("/ai/test")
async def test_ai(current_user: Dict = Depends(auth_utils.get_current_user)):
    """Simple test route to check endpoint connection."""
    fullname = current_user.get("fullname", "Unknown")
    llm = MistralCustomLLM(fullname)
    test_prompt = "Say hello and introduce yourself."
    result = llm.complete(test_prompt)
    return {"fullname": fullname, "response": result}