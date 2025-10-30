# ai.py
"""
Llama-Index pipeline using a custom Mistral endpoint that expects `id={fullname}`.
- The Mistral endpoint used: https://mistral-ai-three.vercel.app/?id={fullname}&question={question}
- fullname (string) will be used in place of userid as requested.

Provides:
- CustomMistralLLM: a minimal LLM wrapper for llama_index that issues HTTP GET to your endpoint.
- helper functions to build, save, load and query a GPTVectorStoreIndex.
"""

import os
import time
import json
import logging
from typing import Optional, List

import requests
from urllib.parse import quote_plus

# llama_index (gpt_index) imports -- install via `pip install llama-index` if needed
from llama_index import (
    SimpleDirectoryReader,
    GPTVectorStoreIndex,
    LLMPredictor,
    PromptHelper,
    ServiceContext,
)
from llama_index.llms.base import LLM  # minimal base class to implement custom LLM

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomMistralLLM(LLM):
    """
    A minimal LLM wrapper for llama_index that sends the prompt to the custom Mistral endpoint.

    The endpoint format:
        https://mistral-ai-three.vercel.app/?id={fullname}&question={question_param}

    fullname: full name string of the user (used as `id` param) and will be URL-encoded.
    """

    def __init__(
        self,
        fullname: str,
        base_url: str = "https://mistral-ai-three.vercel.app/",
        timeout: int = 30,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ):
        """
        :param fullname: Full name to use as id param when calling endpoint
        :param base_url: Base url for the API (default as provided)
        :param timeout: request timeout seconds
        :param max_retries: number of times to retry on transient failures
        :param retry_delay: delay between retries in seconds
        """
        self.fullname = fullname
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    # llama_index expects _call to be implemented; signature sometimes: def _call(self, prompt, stop=None)
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Send the prompt to the Mistral endpoint and return the assistant text.
        """
        # Construct the URL-encoded query
        # Use fullname as id param per user instructions
        encoded_fullname = quote_plus(self.fullname)
        encoded_question = quote_plus(prompt)

        # Build URL: {base_url}/?id={fullname}&question={question}
        url = f"{self.base_url}/?id={encoded_fullname}&question={encoded_question}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "custom-mistral-llm/1.0",
        }

        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug("Calling Mistral endpoint: %s (attempt %d)", url, attempt + 1)
                res = requests.get(url, headers=headers, timeout=self.timeout)
                res.raise_for_status()

                # Try JSON first, fall back to text
                content_type = res.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    data = res.json()
                    # Many lightweight endpoints return either {'answer': '...'} or plain text as string
                    # If it's a mapping, try common keys; otherwise stringify
                    if isinstance(data, dict):
                        # common keys fallback order
                        for k in ("answer", "response", "text", "result", "data"):
                            if k in data and isinstance(data[k], (str,)):
                                return data[k]
                        # last resort: JSON-dump
                        return json.dumps(data)
                    elif isinstance(data, str):
                        return data
                    else:
                        return str(data)
                else:
                    # Content not JSON, return plain text
                    return res.text
            except requests.HTTPError as e:
                logger.warning("HTTP error calling Mistral endpoint: %s (status %s)", e, getattr(e.response, "status_code", None))
                last_exc = e
            except requests.RequestException as e:
                logger.warning("Request exception calling Mistral endpoint: %s", e)
                last_exc = e

            # retry delay
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)

        # if we exit retry loop, raise a wrapped error
        raise RuntimeError(f"Mistral endpoint failed after {self.max_retries + 1} attempts: {last_exc}")

    @property
    def metadata(self) -> dict:
        return {"name": "custom-mistral-llm", "fullname": self.fullname}


def create_llm_predictor(fullname: str, **llm_kwargs) -> LLMPredictor:
    """
    Helper to create a LLMPredictor using the custom Mistral LLM.
    Pass any additional llm_kwargs to CustomMistralLLM.
    """
    custom_llm = CustomMistralLLM(fullname=fullname, **llm_kwargs)
    return LLMPredictor(llm=custom_llm)


def build_index_from_dir(
    docs_dir: str,
    fullname: str,
    index_save_path: str = "index.json",
    max_input_size: int = 4096,
    num_outputs: int = 512,
    chunk_size_limit: int = 600,
    **llm_kwargs,
) -> GPTVectorStoreIndex:
    """
    Build a GPTVectorStoreIndex (vector index) from a directory of documents (text files).
    - docs_dir: directory that SimpleDirectoryReader can read (txt, md, etc.)
    - fullname: full user name that will be used when calling Mistral endpoint
    - index_save_path: path to save index (index persists to disk)
    - llm_kwargs: forwarded to CustomMistralLLM (timeout, max_retries, etc.)
    """

    # 1) Read documents
    logger.info("Reading documents from: %s", docs_dir)
    documents = SimpleDirectoryReader(docs_dir).load_data()

    # 2) Create prompt helper & LLMPredictor
    prompt_helper = PromptHelper(max_input_size, num_outputs, chunk_size_limit)
    llm_predictor = create_llm_predictor(fullname=fullname, **llm_kwargs)
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor, prompt_helper=prompt_helper)

    # 3) Build index
    logger.info("Building GPTVectorStoreIndex...")
    index = GPTVectorStoreIndex.from_documents(documents, service_context=service_context)

    # 4) Persist index to disk
    logger.info("Saving index to: %s", index_save_path)
    index.save_to_disk(index_save_path)
    return index


def load_index(index_path: str, fullname: str, **llm_kwargs) -> GPTVectorStoreIndex:
    """
    Load an existing index from disk and re-create service context (so queries call your Mistral endpoint).
    """
    logger.info("Loading index from: %s", index_path)
    # Recreate predictor and service context (PromptHelper values will be stored inside the index metadata if needed)
    llm_predictor = create_llm_predictor(fullname=fullname, **llm_kwargs)
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
    index = GPTVectorStoreIndex.load_from_disk(index_path, service_context=service_context)
    return index


def query_index(index: GPTVectorStoreIndex, query_str: str, top_k: int = 5):
    """
    Query the index and return the raw response text.
    Uses the index's query_engine (which will use the created CustomMistralLLM).
    """
    logger.info("Querying index: %s (top_k=%d)", query_str, top_k)
    query_engine = index.as_query_engine(similarity_top_k=top_k)
    response = query_engine.query(query_str)
    # response may be a Response object with `.response` or `.response_str` depending on version
    # Be defensive when extracting text
    try:
        # new API tends to have .response or .get_formatted_response()
        if hasattr(response, "response"):
            return str(response.response)
        if hasattr(response, "get_formatted_response"):
            return response.get_formatted_response()
        # fallback to str()
        return str(response)
    except Exception:
        return str(response)


# Example usage
if __name__ == "__main__":
    # Example variables - change to your actual values
    DOCS_DIR = "./docs"  # directory with .txt/.md documents to index
    INDEX_PATH = "my_vector_index.json"
    # The user.fullname you retrieve from your /me endpoint (use exactly the fullname string)
    # Example: "John Doe"
    USER_FULLNAME = "John Doe"  # <-- Replace this with the fullname you receive from your auth endpoint

    # Build index (only run once, or when documents change)
    if not os.path.exists(INDEX_PATH):
        logger.info("Index file not found, building index from %s", DOCS_DIR)
        index = build_index_from_dir(
            docs_dir=DOCS_DIR,
            fullname=USER_FULLNAME,
            index_save_path=INDEX_PATH,
            max_input_size=4096,
            num_outputs=512,
            chunk_size_limit=600,
            timeout=30,
            max_retries=2,
            retry_delay=1.0,
        )
    else:
        logger.info("Index file exists, loading...")
        index = load_index(INDEX_PATH, fullname=USER_FULLNAME, timeout=30)

    # Query example
    q = "Summarize the key points from the docs about deployment best practices."
    print("Query:", q)
    ans = query_index(index, q, top_k=5)
    print("Answer:", ans)