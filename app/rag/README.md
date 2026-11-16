# rag/

The knowledge base: getting documents in, and finding them again.

- `ingest.py` - file to chunks to stored. Reads pdf, txt, md and docx. Each chunk starts with its title and section. Used by the upload API and by the command line.
- `store.py` - the only file that talks to Pinecone. It also makes the embeddings. Functions: `search`, `add_chunks`, `reset`, `count`, `warm_up`. The app calls `warm_up` in the background when it starts, so the first question does not wait about 20 seconds for PyTorch and the model to load.

Chat only reads from here. Only ingest writes. A file uploaded again replaces its old chunks.

## Set up Pinecone (free)

1. Sign up at https://app.pinecone.io (the free Starter plan).
2. Open **API keys**, create a key and copy it.
3. Put it in `.env` as `PINECONE_API_KEY=...`. Use `.env`, not `.env.example`: the app reads only `.env`.
4. Run `python -m app.rag.ingest`. The first run creates the index and downloads the embedding model (about 130 MB).
5. Check it: `python -m app.rag.store "How do I connect to the VPN from home?"`

More commands: `python -m app.rag.ingest some/folder` loads another folder instead of `kb_dir`. `python -m app.rag.ingest --reset` empties the namespace first, after asking you to type `yes`.

## From file to Pinecone

```
file -> ingest.py: load_file -> chunk -> ingest_file -> store.add_chunks -> Pinecone
```

- `ingest.py` never talks to Pinecone. Its `ingest_file` ends by calling `store.add_chunks(chunks)`. That one call is the handoff.
- `add_chunks` makes the vector for each chunk, then stores one record per chunk: `id` (`file-name::0001`), the 384 numbers, and metadata (`source`, `title`, `section`, and the chunk's text under `text`).
- The chunks live only in Pinecone (your index and namespace). Nothing is saved on your computer.
- Chat reads only Pinecone. It never opens `data/kb/`.

## Where the documents come from

- The folder is `kb_dir` in `app/config.py` (default: `data/kb/` inside the project).
- To use another folder once, pass it: `python -m app.rag.ingest some/folder`. To change it for good, set `KB_DIR` in `.env`.
- Subfolders are read too, so `batch-1/` to `batch-5/` can stay as they are. Only the file name matters: it is the `source` and part of every id. Two files with the same name are refused.
- Staff uploads from the chat page are saved in `data/uploads/` and go through the same `ingest_file`.

- The **index** is the database (`PINECONE_INDEX_NAME`). Its vector size is fixed when it is created.
- A **namespace** is a folder inside the index (`PINECONE_NAMESPACE`). The first upload creates it.
- Ingest and chat must use the same pair, or chat finds nothing. Set them in `.env` only. The defaults in `app/config.py` are a fallback, and `.env` always wins.

## Embedding model

`BAAI/bge-small-en-v1.5`: free, runs on your computer, makes 384 numbers per vector, reads up to 512 tokens. On our 22 answerable test questions it ranked the right document first more often than `all-MiniLM-L6-v2` (95% vs 86%). The bigger `bge-base` (768 numbers) did not do better.

The index size must match the model. `store.py` checks this and stops with advice if it doesn't. It never deletes an index, and new indexes are created with deletion protection on. To change the model, set a new `PINECONE_INDEX_NAME` and ingest again.

Free plan limits: 5 indexes, 100 namespaces per index, 2 GB, AWS `us-east-1` only.
