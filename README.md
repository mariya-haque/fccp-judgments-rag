# FCCP Judgments RAG Chatbot

A retrieval-augmented chatbot for judgments of the Federal Constitutional Court of Pakistan (FCCP). A scraper downloads judgment PDFs and their metadata from fccp.gov.pk. A FastAPI backend answers questions by retrieving the most relevant judgment excerpts from a ChromaDB vector store and passing them, with a summary of every case in the dataset, to OpenAI `gpt-4o-mini`. Users sign in with a username, and each user keeps a list of saved chats in a local SQLite database.

## Features

- Scraper (`scrape_judgement.py`) that reads the first 5 pages of https://www.fccp.gov.pk/judgments, removes duplicate rows, downloads each PDF and writes `judgments_metadata.json` (title, judge, date, download URL, local PDF path).
- Retrieval: the question is embedded with `text-embedding-3-small`, and the top 5 chunks come from the Chroma collection `fccp_judgments`.
- A global summary built from the metadata file (total number of judgments, every judge, every case) is added to each prompt, so the bot can also answer aggregate questions such as "how many judgments are there?".
- Conversation memory: the last 10 messages of the chat are sent with each question.
- Username-only signup and login (no passwords), multiple chats per user, and chat titles set from the first message.
- Single-page web UI (`index.html`) served at `/`. You can ask questions in English or Roman Urdu.

## Tech stack

Python, FastAPI, Uvicorn, SQLAlchemy (SQLite), ChromaDB, OpenAI API, Requests and BeautifulSoup (scraper), plain HTML/JS frontend.

## Project structure

```
.
├── RAG/                      # The app. Run every command from here.
│   ├── main.py               # FastAPI app: auth, chats, messages, serves index.html
│   ├── rag_engine.py         # Retrieval + answer generation (ChromaDB + OpenAI)
│   ├── database.py           # SQLAlchemy models (User, Chat, Message), SQLite fccp_chatbot.db
│   ├── scrape_judgement.py   # Scrapes fccp.gov.pk and downloads judgment PDFs
│   ├── index.html            # Chat UI
│   ├── requirements.txt
│   └── .env.example
└── data/                     # Read and written by RAG/ via ../data
    ├── pdfs/                 # Downloaded judgment PDFs (written by scrape_judgement.py)
    ├── judgments_metadata.json
    └── chroma_db/            # Persistent ChromaDB store (git-ignored, build it locally)
```

### About the `data/` folder

The code does not keep its data inside `RAG/`. Both scripts build paths relative to their own location:

| File | Path used | Access |
|------|-----------|--------|
| `scrape_judgement.py` | `../data/pdfs/` | writes PDFs |
| `scrape_judgement.py` | `../data/judgments_metadata.json` | writes |
| `rag_engine.py` | `../data/judgments_metadata.json` | reads (global case summary) |
| `rag_engine.py` | `../data/chroma_db/` | reads (vector search) |

That is why this repository keeps `data/` next to `RAG/`. If you move the code elsewhere, change `CHROMA_DIR`, `METADATA_FILE` and `OUTPUT_DIR` in the two scripts.

> **Note: there is no ingestion script.** This project contains no code that splits the PDFs into chunks, embeds them and writes them to `data/chroma_db`. The chatbot expects a Chroma collection named `fccp_judgments` that already exists, where each chunk has `title`, `judge` and `date` metadata (or `source` as a fallback) and was embedded with `text-embedding-3-small`. If the collection is empty, `rag_engine.py` creates it, and queries return no excerpts. The bot then answers only from the metadata summary.

## Prerequisites

- Python 3.10+ (the code uses `list[dict]` and `str | None` type hints)
- An OpenAI API key

## Setup

```bash
cd RAG
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # then fill in the values
```

(`requirement.txt` is the older name of the dependency file. Use `requirements.txt`.)

### Environment variables

| Variable | Required | Description | Where to get it |
|----------|----------|-------------|-----------------|
| `OPENAI_API_KEY` | Yes | Used for embeddings and chat completions | https://platform.openai.com/api-keys |

## Running

1. (Optional) Download the judgments. This writes to `../data/`:

   ```bash
   python scrape_judgement.py
   ```

2. Make sure `../data/chroma_db` holds the embedded `fccp_judgments` collection (see the note above).

3. Start the API and UI:

   ```bash
   python main.py
   # or
   uvicorn main:app --reload --port 8000
   ```

4. Open http://127.0.0.1:8000. The UI calls the API at `http://localhost:8000` (the value is hard-coded in `index.html`), so keep port 8000.

The SQLite database `fccp_chatbot.db` is created in the working directory on first start.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Chat UI |
| POST | `/auth/signup` | `{ "username" }`: create a user (fails if the username exists) |
| POST | `/auth/login` | `{ "username" }`: log in an existing user |
| POST | `/users` | Create the user, or return the existing one |
| GET | `/users/{user_id}/chats` | List a user's chats |
| POST | `/chats` | `{ "user_id", "title"? }`: create a chat |
| DELETE | `/chats/{chat_id}` | Delete a chat and its messages |
| GET | `/chats/{chat_id}/messages` | Chat history |
| POST | `/chats/{chat_id}/messages` | `{ "content" }`: ask a question and get the assistant's answer |

Interactive docs: http://127.0.0.1:8000/docs
