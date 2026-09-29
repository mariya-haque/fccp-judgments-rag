import os
import json
import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
METADATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "judgments_metadata.json")
COLLECTION_NAME = "fccp_judgments"
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
TOP_K = 5

client = OpenAI()
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = chroma_client.get_or_create_collection(COLLECTION_NAME)

SYSTEM_PROMPT = (
    "Aap FCCP (Federal Constitutional Court of Pakistan) judgments ka legal research "
    "assistant hain. Sirf diye gaye context (retrieved judgment excerpts aur global summary) ke basis par jawab dein. "
    "Agar context me answer na mile, saaf keh dein ke available judgments me yeh info nahi mili. "
    "Case titles aur judge names ka hawala dein jab relevant ho."
)


def load_global_metadata() -> list[dict]:
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[error] failed to load metadata: {e}")
            return []
    return []


GLOBAL_METADATA = load_global_metadata()


def build_global_summary() -> str:
    if not GLOBAL_METADATA:
        return "No global metadata available."
    
    unique_judges = sorted(list(set(item.get("judge") for item in GLOBAL_METADATA if item.get("judge"))))
    
    summary = []
    summary.append(f"TOTAL NUMBER OF PDF JUDGMENTS AVAILABLE IN DATABASE: {len(GLOBAL_METADATA)}")
    summary.append(f"ALL UNIQUE JUDGES ({len(unique_judges)}): {', '.join(unique_judges)}")
    summary.append("\nCOMPLETE LIST OF ALL AVAILABLE CASES & JUDGES:")
    for idx, item in enumerate(GLOBAL_METADATA, 1):
        summary.append(f"{idx}. Case: {item.get('title')} | Judge: {item.get('judge')} | Date: {item.get('date')}")
        
    return "\n".join(summary)


def retrieve_context(query: str, top_k: int = TOP_K):
    query_embedding = client.embeddings.create(
        model=EMBED_MODEL, input=[query]
    ).data[0].embedding

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    return list(zip(docs, metas))


def build_context_block(retrieved) -> str:
    blocks = []
    for doc, meta in retrieved:
        title = meta.get("title") or meta.get("source", "unknown")
        judge = meta.get("judge", "")
        date = meta.get("date", "")
        header = f"[Case: {title} | Judge: {judge} | Date: {date}]"
        blocks.append(f"{header}\n{doc}")
    return "\n\n---\n\n".join(blocks)


def generate_answer(query: str, chat_history: list[dict]) -> str:
    """
    chat_history: [{"role": "user"/"assistant", "content": "..."}]  
    """
    retrieved = retrieve_context(query)
    context_block = build_context_block(retrieved)
    global_summary = build_global_summary()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    messages.extend(chat_history[-10:])

    user_message = (
        f"Global Database Summary (Use this for aggregate statistics like total number of judgments, list of judges, and checking which cases exist):\n"
        f"{global_summary}\n\n"
        f"Retrieved Judgment Excerpts (Use this for detailed legal content inside specific cases):\n"
        f"{context_block}\n\n"
        f"Question: {query}"
    )
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.2,
    )
    return response.choices[0].message.content