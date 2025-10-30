# ai.py
"""
Single-file native-Python AI index + query engine using your custom Mistral endpoint.

Features:
- Reads text documents from a directory and indexes them.
- Vector search with:
    - FAISS (if installed), else
    - scikit-learn TF-IDF + cosine (if installed), else
    - a pure-Python TF (term-frequency) + numpy cosine fallback.
- Custom LLM wrapper that calls:
    https://mistral-ai-three.vercel.app/?id={fullname}&question={question}
  where `fullname` is URL-encoded and used as `id`.
- Save/load index to disk (pickle).
- Simple CLI for building, adding docs, and querying.
- All in one file (native Python).
"""

import os
import sys
import json
import time
import pickle
import math
import glob
import logging
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus

try:
    import requests
except Exception as e:
    raise RuntimeError("requests is required. Install with `pip install requests`") from e

# optional numeric libs
try:
    import numpy as np
except Exception:
    np = None

# try optional near-neighbor libs
HAS_FAISS = False
HAS_SKLEARN = False
try:
    import faiss  # type: ignore
    HAS_FAISS = True
except Exception:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
        HAS_SKLEARN = True
    except Exception:
        HAS_SKLEARN = False

# Basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple_ai")

# ------------ Configuration ------------
DATA_DIR = os.environ.get("AI_DATA_DIR", "./ai_data")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
INDEX_PATH = os.path.join(DATA_DIR, "index.pkl")
VECTORS_PATH = os.path.join(DATA_DIR, "vectors.pkl")
MISTRAL_BASE = os.environ.get("MISTRAL_BASE", "https://mistral-ai-three.vercel.app/")
# index options
TOP_K = 5
# ---------------------------------------

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)


# ------------- Utility doc loader -------------
def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def load_documents_from_dir(dirpath: str) -> List[Dict]:
    """
    Returns list of document dicts: {id, path, text}
    Supports .txt, .md, .text by default.
    """
    docs = []
    patterns = ["*.txt", "*.md", "*.text"]
    for pat in patterns:
        for p in glob.glob(os.path.join(dirpath, pat)):
            try:
                text = read_text_file(p)
                docs.append({"id": os.path.abspath(p), "path": p, "text": text})
            except Exception:
                logger.exception("Failed reading %s", p)
    # also include any other files passed
    return docs


# ------------- Vectorizer utilities -------------
class PureTFVectorizer:
    """
    Very simple term-frequency vectorizer with vocabulary grown from corpus.
    Not meant to be fancy — fallback when sklearn/faiss are not available.
    """
    def __init__(self):
        self.vocab = {}  # token -> idx
        self.idf = None

    @staticmethod
    def _tokenize(text: str):
        # naive tokenizer: split by whitespace and punctuation
        # lowercases and strips small tokens
        tokens = []
        cur = []
        for ch in text.lower():
            if ch.isalnum():
                cur.append(ch)
            else:
                if cur:
                    token = "".join(cur)
                    if len(token) >= 2:
                        tokens.append(token)
                    cur = []
        if cur:
            token = "".join(cur)
            if len(token) >= 2:
                tokens.append(token)
        return tokens

    def fit_transform(self, docs: List[str]):
        # build vocab
        for d in docs:
            for t in set(self._tokenize(d)):
                if t not in self.vocab:
                    self.vocab[t] = len(self.vocab)
        n_docs = len(docs)
        V = np.zeros((n_docs, len(self.vocab)), dtype=float) if np is not None else []
        # build doc-term matrix (TF)
        for i, d in enumerate(docs):
            tokens = self._tokenize(d)
            counts = {}
            for t in tokens:
                if t in self.vocab:
                    counts[t] = counts.get(t, 0) + 1
            if np is not None:
                for t, c in counts.items():
                    V[i, self.vocab[t]] = c
        # compute idf
        df = np.zeros((len(self.vocab),), dtype=float)
        for t, idx in self.vocab.items():
            for i in range(n_docs):
                if V[i, idx] > 0:
                    df[idx] += 1.0
        # smooth idf
        self.idf = np.log((1 + n_docs) / (1 + df)) + 1.0
        # convert to tf-idf
        if np is not None:
            V = V * self.idf[None, :]
            # normalize
            norms = np.linalg.norm(V, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            V = V / norms
        return V

    def transform(self, docs: List[str]):
        if self.idf is None:
            raise RuntimeError("Vectorizer not fitted")
        n_docs = len(docs)
        V = np.zeros((n_docs, len(self.vocab)), dtype=float) if np is not None else []
        for i, d in enumerate(docs):
            tokens = self._tokenize(d)
            counts = {}
            for t in tokens:
                if t in self.vocab:
                    counts[t] = counts.get(t, 0) + 1
            for t, c in counts.items():
                V[i, self.vocab[t]] = c
        V = V * self.idf[None, :]
        norms = np.linalg.norm(V, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        V = V / norms
        return V


class VectorIndex:
    """
    Vector index manager that uses FAISS or SKLearn TF-IDF or pure TF fallback.
    Stores:
      - docs: list of dicts (id, path, text, meta)
      - vectors: numpy array (n_docs, dim)
      - vectorizer backend
    """
    def __init__(self):
        self.docs: List[Dict] = []
        self.vectors = None
        self.backend = None  # 'faiss', 'sklearn', 'pure'
        self._faiss_index = None
        self.vectorizer = None

    def build(self, docs: List[Dict]):
        texts = [d["text"] for d in docs]
        logger.info("Building vector index for %d docs", len(docs))
        # Prefer faiss for ANN (but we still need embeddings: we use TF-IDF vectors as embeddings)
        if HAS_FAISS and np is not None:
            # use sklearn tfidf if available, else fallback to pure
            if HAS_SKLEARN:
                vec = TfidfVectorizer(stop_words="english", max_features=32768)
                X = vec.fit_transform(texts).astype("float32").toarray()
            else:
                vec = PureTFVectorizer()
                X = vec.fit_transform(texts).astype("float32")
            dim = X.shape[1]
            index = faiss.IndexFlatIP(dim)  # inner-product on normalized vectors ~ cos sim
            # normalize rows
            norms = np.linalg.norm(X, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            Xn = X / norms
            index.add(Xn)
            self._faiss_index = index
            self.backend = "faiss"
            self.vectors = Xn
            self.vectorizer = vec
            logger.info("Built FAISS index (dim=%d)", dim)
        elif HAS_SKLEARN:
            vec = TfidfVectorizer(stop_words="english", max_features=32768)
            X = vec.fit_transform(texts)
            # convert to dense normalized array if numpy available
            if np is not None:
                X_arr = X.toarray()
                norms = np.linalg.norm(X_arr, axis=1, keepdims=True)
                norms[norms == 0.0] = 1.0
                Xn = X_arr / norms
                self.vectors = Xn
            else:
                self.vectors = X
            self.vectorizer = vec
            self.backend = "sklearn"
            logger.info("Built sklearn TF-IDF index (shape=%s)", getattr(self.vectors, "shape", None))
        else:
            # pure fallback
            if np is None:
                raise RuntimeError("numpy required for fallback vector operations")
            vec = PureTFVectorizer()
            Xn = vec.fit_transform(texts)
            self.vectors = Xn
            self.vectorizer = vec
            self.backend = "pure"
            logger.info("Built pure TF fallback index (dim=%d)", Xn.shape[1])
        self.docs = docs

    def save(self, path: str):
        logger.info("Saving index to %s", path)
        payload = {
            "docs": self.docs,
            "backend": self.backend,
            "vectors_shape": None,
            "vectorizer": None,
        }
        # vectorizer: for sklearn keep vectorizer object, for pure keep vocabulary
        if self.backend == "faiss":
            # cannot pickle faiss index easily with Python pickle across versions, but we keep vectors and rebuild
            payload["vectors"] = self.vectors
            payload["vectorizer"] = self.vectorizer
        elif self.backend == "sklearn":
            payload["vectors"] = self.vectors
            payload["vectorizer"] = self.vectorizer
        else:
            payload["vectors"] = self.vectors
            payload["vectorizer"] = {"vocab": getattr(self.vectorizer, "vocab", None)}
        with open(path, "wb") as f:
            pickle.dump(payload, f)

    def load(self, path: str):
        logger.info("Loading index from %s", path)
        with open(path, "rb") as f:
            payload = pickle.load(f)
        self.docs = payload.get("docs", [])
        self.backend = payload.get("backend", "pure")
        self.vectors = payload.get("vectors", None)
        self.vectorizer = payload.get("vectorizer", None)
        # if backend == 'faiss' we do not reconstruct faiss index; we can use vectors for brute-force
        logger.info("Loaded index: %d docs, backend=%s", len(self.docs), self.backend)

    def search(self, query_text: str, top_k: int = 5) -> List[Tuple[Dict, float]]:
        """
        Returns list of (doc, score) sorted descending by similarity.
        Score is cosine similarity in [0,1] range (if normalized).
        """
        if not self.docs:
            return []
        # vectorize query
        if self.backend == "faiss" and HAS_FAISS:
            if HAS_SKLEARN:
                qv = self.vectorizer.transform([query_text]).toarray().astype("float32")
            else:
                qv = self.vectorizer.transform([query_text]).astype("float32")
            # normalize
            norm = np.linalg.norm(qv, axis=1, keepdims=True)
            norm[norm == 0.0] = 1.0
            qn = qv / norm
            D, I = self._faiss_index.search(qn, top_k)
            results = []
            for idx, score in zip(I[0], D[0]):
                results.append((self.docs[idx], float(score)))
            return results
        else:
            # brute force using vectors and cosine
            if self.backend == "sklearn":
                # vectorizer is a sklearn TfidfVectorizer object
                qv = self.vectorizer.transform([query_text])
                if np is not None:
                    qv = qv.toarray()
                else:
                    pass
            elif self.backend == "pure":
                qv = self.vectorizer.transform([query_text])
            else:
                # unknown backend fallback
                qv = None

            if np is None:
                # can't compute similarities without numpy
                raise RuntimeError("numpy is required for search in this environment")

            qv_arr = qv if isinstance(qv, np.ndarray) else np.array(qv)
            # normalize
            qnorm = np.linalg.norm(qv_arr, axis=1, keepdims=True)
            qnorm[qnorm == 0.0] = 1.0
            qn = qv_arr / qnorm
            # compute cosine similarity with stored normalized vectors
            V = self.vectors
            if V is None:
                raise RuntimeError("No vectors present to search")
            sims = np.dot(V, qn.T).squeeze()
            # if sims is 1d
            if sims.ndim > 1:
                sims = sims.flatten()
            idxs = np.argsort(-sims)[:top_k]
            results = [(self.docs[int(i)], float(sims[int(i)])) for i in idxs]
            return results


# --------------- Mistral LLM wrapper ---------------
class MistralLLM:
    """
    Minimal wrapper calling the provided mistral endpoint:
    https://mistral-ai-three.vercel.app/?id={fullname}&question={question}
    Uses GET and returns text. Retries a few times on transient failure.
    """
    def __init__(self, fullname: str, base_url: str = MISTRAL_BASE, timeout: int = 20, max_retries: int = 2, retry_delay: float = 1.0):
        self.fullname = fullname
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def call(self, prompt: str) -> str:
        encoded_fullname = quote_plus(self.fullname)
        encoded_q = quote_plus(prompt)
        url = f"{self.base_url}/?id={encoded_fullname}&question={encoded_q}"
        headers = {"User-Agent": "simple-ai-client/1.0", "Accept": "application/json, text/plain, */*"}
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                # try to parse JSON for likely keys
                ct = resp.headers.get("Content-Type", "")
                if "application/json" in ct:
                    data = resp.json()
                    if isinstance(data, dict):
                        for k in ("answer", "response", "text", "result"):
                            if k in data and isinstance(data[k], str):
                                return data[k]
                        # fallback to dumping JSON
                        return json.dumps(data)
                    elif isinstance(data, str):
                        return data
                    else:
                        return str(data)
                else:
                    return resp.text
            except requests.HTTPError as e:
                logger.warning("HTTP error on Mistral call: %s", e)
                last_exc = e
            except requests.RequestException as e:
                logger.warning("Request error on Mistral call: %s", e)
                last_exc = e
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)
        raise RuntimeError(f"Mistral call failed after retries: {last_exc}")


# --------------- High-level API ---------------
class SimpleAI:
    def __init__(self, data_dir: str = DATA_DIR, docs_dir: str = DOCS_DIR, index_path: str = INDEX_PATH):
        self.data_dir = data_dir
        self.docs_dir = docs_dir
        self.index_path = index_path
        self.index = VectorIndex()

    def build_index(self, reindex: bool = False) -> None:
        """
        Build index from files in docs_dir. If index exists and not reindex, attempt to load.
        """
        if os.path.exists(self.index_path) and not reindex:
            logger.info("Index file found at %s, loading...", self.index_path)
            self.index.load(self.index_path)
            return
        docs = load_documents_from_dir(self.docs_dir)
        if not docs:
            logger.warning("No documents found in %s. Create text files there to index.", self.docs_dir)
            self.index.docs = []
            self.index.vectors = None
            return
        self.index.build(docs)
        self.save_index()

    def save_index(self):
        self.index.save(self.index_path)

    def add_documents_from_dir(self, new_dir: str):
        """
        Copy or reference new docs and rebuild incrementally: we simply re-run build on combined docs.
        """
        # gather existing docs plus new
        new_docs = load_documents_from_dir(new_dir)
        if not new_docs:
            logger.info("No new documents found in %s", new_dir)
            return
        # copy to managed docs dir (not strictly required; we will reference)
        for d in new_docs:
            dest = os.path.join(self.docs_dir, os.path.basename(d["path"]))
            try:
                with open(d["path"], "rb") as fr, open(dest, "wb") as fw:
                    fw.write(fr.read())
            except Exception:
                logger.exception("Failed copying doc %s to %s", d["path"], dest)
        # rebuild
        self.build_index(reindex=True)

    def query(self, question: str, fullname: str, top_k: int = TOP_K, return_context: bool = False) -> Dict:
        """
        1. Find top_k relevant docs using vector search.
        2. Compose prompt: include top document excerpts + question.
        3. Call Mistral endpoint with fullname as id.
        Returns dict: {answer: str, sources: [(path, score)...], prompt: str}
        """
        if not self.index.docs:
            logger.info("Index missing or empty; building now...")
            self.build_index()
        results = self.index.search(question, top_k=top_k)
        # Compose a compact context (first 400 chars each)
        context_pieces = []
        sources = []
        for doc, score in results:
            snippet = (doc.get("text") or "")[:800].strip()
            context_pieces.append(f"--- SOURCE: {os.path.basename(doc.get('path',''))} (score={score:.4f}) ---\n{snippet}\n")
            sources.append({"path": doc.get("path"), "score": score})
        context = "\n\n".join(context_pieces) if context_pieces else ""
        prompt = (
            "You are an assistant. Use the documents provided below to answer the user's question. "
            "Cite the source filenames if relevant.\n\n"
            "DOCUMENTS:\n\n"
            f"{context}\n\nQUESTION:\n{question}\n\n"
            "Answer concisely and clearly. If you cannot find the answer in the documents, say so and provide best-effort reasoning."
        )
        # call LLM
        llm = MistralLLM(fullname=fullname)
        answer = llm.call(prompt)
        out = {"answer": answer, "sources": sources, "prompt": prompt}
        if return_context:
            out["context"] = context
        return out


# --------------- CLI helpers ---------------
def ensure_docs_dir():
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR, exist_ok=True)
        logger.info("Created docs directory: %s", DOCS_DIR)


def cli_build(args):
    ensure_docs_dir()
    ai = SimpleAI()
    reindex = "--reindex" in args
    ai.build_index(reindex=reindex)
    logger.info("Index built and saved to %s", INDEX_PATH)


def cli_add(args):
    # usage: add <path_to_dir_with_texts>
    if len(args) < 2:
        print("Usage: ai.py add <path_to_dir_with_texts>")
        return
    src = args[1]
    if not os.path.exists(src):
        print("Path not found:", src)
        return
    ai = SimpleAI()
    ai.add_documents_from_dir(src)
    logger.info("Added documents from %s and rebuilt index", src)


def cli_query(args):
    # usage: query "<fullname>" "your question here"
    if len(args) < 3:
        print('Usage: ai.py query "<fullname>" "your question" [--topk N]')
        return
    fullname = args[1]
    question = args[2]
    topk = TOP_K
    if "--topk" in args:
        try:
            i = args.index("--topk")
            topk = int(args[i + 1])
        except Exception:
            pass
    ai = SimpleAI()
    res = ai.query(question=question, fullname=fullname, top_k=topk, return_context=False)
    print("=== ANSWER ===")
    print(res["answer"])
    print("\n=== SOURCES ===")
    for s in res["sources"]:
        print(f"{s['path']} (score={s['score']:.4f})")


def cli_help():
    print("Usage: ai.py <command> [args]")
    print("Commands:")
    print("  build [--reindex]           Build index from ./ai_data/docs (creates dir if missing)")
    print("  add <dir_with_texts>        Copy texts into ./ai_data/docs and rebuild index")
    print('  query "<fullname>" "q" [--topk N]   Query the index using Mistral endpoint, fullname used as id')
    print("  help                        Show this help")


# --------------- Run as script ---------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        cli_help()
        sys.exit(0)
    cmd = sys.argv[1].lower()
    if cmd == "build":
        cli_build(sys.argv[1:])
    elif cmd == "add":
        cli_add(sys.argv[1:])
    elif cmd == "query":
        cli_query(sys.argv[1:])
    elif cmd in ("-h", "--help", "help"):
        cli_help()
    else:
        print("Unknown command:", cmd)
        cli_help()