# routers/ai.py
# -----------------------------------------
# Final version with working MistralCustomLLM for LlamaIndex
# -----------------------------------------

from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Dict
import logging
import os
from urllib.parse import quote_plus
import httpx
import asyncio

from llama_index import (
    SimpleDirectoryReader,
    GPTVectorStoreIndex,
    ServiceContext,
    LLMPredictor,
    PromptHelper,
)
from llama_index.llms.base import LLM
from llama_index.llms.types import ChatResponse, CompletionResponse, LLMMetadata

from routers import auth_utils  # adjust import if auth_utils is in a different path
from schemas import auth_schemas

router = APIRouter()
logger = logging.getLogger("routers.ai")

# -----------------------------------------
# Custom LLM wrapper for Mistral endpoint
# -----------------------------------------
class MistralCustomLLM(LLM):
    """Custom LLM that calls your Mistral endpoint using fullname instead of user_id."""

    def __init__(self, fullname: str, base_url: str = "https://mistral-ai-three.vercel.app/"):
        self.fullname = fullname
        self.base_url = base_url.rstrip("/")

    # ---------- Core sync methods ----------
    def chat(self, messages, **kwargs) -> ChatResponse:
        text = self._call(self._extract_prompt(messages))
        return ChatResponse(message=text)

    def stream_chat(self, messages, **kwargs):
        text = self._call(self._extract_prompt(messages))
        yield ChatResponse(message=text)

    def stream_complete(self, prompt: str, **kwargs):
        yield CompletionResponse(text=self._call(prompt))

    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        text = self._call(prompt)
        return CompletionResponse(text=text)

    # ---------- Async versions ----------
    async def achat(self, messages, **kwargs) -> ChatResponse:
        text = await self._acall(self._extract_prompt(messages))
        return ChatResponse(message=text)

    async def astream_chat(self, messages, **kwargs):
        text = await self._acall(self._extract_prompt(messages))
        yield ChatResponse(message=text)

    async def astream_complete(self, prompt: str, **kwargs):
        yield CompletionResponse(text=await self._acall(prompt))

    # ---------- Internal HTTP calls ----------
    def _call(self, prompt: str) -> str:
        q = quote_plus(prompt)
        id_ = quote_plus(self.fullname)
        url = f"{self.base_url}/?id={id_}&question={q}"
        try:
            r = httpx.get(url, timeout=30)
            if r.status_code == 200:
                return r.text.strip()
            return f"[HTTP {r.status_code}] {r.text}"
        except Exception as e:
            return f"[Error contacting Mistral endpoint: {e}]"

    async def _acall(self, prompt: str) -> str:
        q = quote_plus(prompt)
        id_ = quote_plus(self.fullname)
        url = f"{self.base_url}/?id={id_}&question={q}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.text.strip()
                return f"[HTTP {r.status_code}] {r.text}"
        except Exception as e:
            return f"[Error contacting Mistral endpoint: {e}]"

    # ---------- Metadata ----------
    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            model_name="Mistral-Custom",
            context_window=4096,
            num_output=512,
            is_chat_model=True,
        )

    # ---------- Utility ----------
    def _extract_prompt(self, messages) -> str:
        if isinstance(messages, str):
            return messages
        if isinstance(messages, list):
            return "\n".join([f"{m.role}: {m.content}" for m in messages if hasattr(m, "content")])
        return str(messages)


# -----------------------------------------
# Helper: Create or load vector index
# -----------------------------------------
INDEX_PATH = "workspace_index.json"
DOCS_PATH = "./docs"  # change if you store your text data elsewhere


def get_index(fullname: str) -> GPTVectorStoreIndex:
    """Load or create a LlamaIndex using the custom Mistral LLM."""
    llm = MistralCustomLLM(fullname=fullname)
    llm_predictor = LLMPredictor(llm=llm)
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)

    if os.path.exists(INDEX_PATH):
        logger.info("Loading index from disk...")
        index = GPTVectorStoreIndex.load_from_disk(INDEX_PATH, service_context=service_context)
    else:
        logger.info("Building new index from %s", DOCS_PATH)
        documents = SimpleDirectoryReader(DOCS_PATH).load_data()
        index = GPTVectorStoreIndex.from_documents(documents, service_context=service_context)
        index.save_to_disk(INDEX_PATH)
    return index


# -----------------------------------------
# Routes
# -----------------------------------------
@router.get("/ai/query")
async def query_ai(q: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    """
    Query AI with a user's question.
    Uses fullname as the unique identifier for your Mistral endpoint.
    """
    fullname = current_user["fullname"]
    logger.info(f"AI Query by: {fullname} | Q: {q}")

    try:
        index = get_index(fullname)
        response = index.as_query_engine(similarity_top_k=5).query(q)
        answer = str(response.response if hasattr(response, "response") else response)
        return {"fullname": fullname, "question": q, "answer": answer}
    except Exception as e:
        logger.exception("AI query failed")
        raise HTTPException(status_code=500, detail=f"AI query failed: {e}")


@router.get("/ai/test")
async def ai_test(current_user: Dict = Depends(auth_utils.get_current_user)):
    """Simple test endpoint to verify LLM connectivity."""
    fullname = current_user["fullname"]
    test_prompt = "Hello Anya, introduce yourself."
    logger.info(f"Testing AI connection for: {fullname}")

    llm = MistralCustomLLM(fullname=fullname)
    response = llm._call(test_prompt)
    return {"fullname": fullname, "test_prompt": test_prompt, "response": response}


@router.get("/ai/ask")
async def ai_ask(q: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    """Lightweight endpoint that directly hits the custom Mistral LLM."""
    fullname = current_user["fullname"]
    llm = MistralCustomLLM(fullname=fullname)
    answer = llm._call(q)
    return {"fullname": fullname, "question": q, "answer": answer}