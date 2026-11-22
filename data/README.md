# data/

Files the app reads or creates.

- `kb/` - the company IT knowledge base: documents written for the fictional NovaRetail (made with the prompt in `../docs/kb-generation-prompt.md`). This is the folder `python -m app.rag.ingest` loads (`kb_dir` in `app/config.py`). Subfolders such as `batch-1/` are read too.
- `uploads/` - made when the app runs. Documents uploaded by staff. Not in git.
- `audit.db` - made when the first question is asked (not at start-up). SQLite log of questions and decision paths. It is not a text file, so read it on the Settings page (Recent Questions) or with a SQLite viewer. Not in git.

`kb/` is only the source material. Once ingest has stored it in Pinecone, the app answers from Pinecone and never reads `kb/` again.

`kb/` has no README on purpose. The loader indexes every `.md` file in it, so a README there would end up in the knowledge base.
