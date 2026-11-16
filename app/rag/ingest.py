"""Turns a document into chunks and stores them. Used by the upload API and by the command line."""
import re
from pathlib import Path

from docx import Document as DocxDocument
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.rag import store

SUPPORTED = {".pdf", ".txt", ".md", ".docx"}
BY_HEADING = {".md", ".docx"}  # these are cut at their headings first
HEADINGS = MarkdownHeaderTextSplitter([("#", "title"), ("##", "section"), ("###", "subsection")])
SPLITTER = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)


def _docx_as_markdown(path: Path) -> str:
    """Word headings become # lines, so a docx is cut by section like a markdown file."""
    doc = DocxDocument(str(path))
    lines = []
    for p in doc.paragraphs:
        text, style = p.text.strip(), (p.style.name if p.style is not None else "")
        if not text:
            continue
        level = re.fullmatch(r"Heading (\d)", style)
        if level:
            text = "#" * min(int(level[1]), 3) + " " + text
        elif style == "Title":
            text = "# " + text
        lines.append(text)
    for table in doc.tables:
        lines += [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
    return "\n\n".join(lines)


def load_file(path: Path) -> list[Document]:
    """Read a pdf, txt, md or docx file into Documents. metadata["source"] is the file name."""
    suffix, meta = path.suffix.lower(), {"source": path.name}
    if suffix in {".txt", ".md"}:
        return [Document(page_content=path.read_text(encoding="utf-8-sig", errors="replace"), metadata=meta)]
    if suffix == ".docx":
        return [Document(page_content=_docx_as_markdown(path), metadata=meta)]
    if suffix == ".pdf":
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError(f"{path.name} is password-protected.")
        return [
            Document(page_content=page.extract_text() or "", metadata={**meta, "page": number})
            for number, page in enumerate(reader.pages, 1)
        ]
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk(docs: list[Document]) -> list[Document]:
    """Cut documents into chunks of about 900 characters. Each chunk starts with its title and section,
    so it still makes sense when it is found on its own."""
    out = []
    for doc in docs:
        source = doc.metadata["source"]
        if Path(source).suffix.lower() in BY_HEADING:
            parts = [
                Document(page_content=p.page_content, metadata={**doc.metadata, **p.metadata})
                for p in HEADINGS.split_text(doc.page_content)
            ]
            if len(parts) > 1 and "section" not in parts[0].metadata:  # the lines under the # title (id, owner...) join the first section
                head, first, *rest = parts
                parts = [Document(page_content=f"{head.page_content}\n\n{first.page_content}", metadata=first.metadata), *rest]
        else:
            parts = [doc]
        for part in SPLITTER.split_documents(parts):
            m, text = part.metadata, part.page_content.strip()
            label = " > ".join(filter(None, [m.get("title"), m.get("section"), m.get("subsection")]))
            label = label or Path(source).stem.replace("-", " ").replace("_", " ")
            if text:
                out.append(Document(page_content=f"{label}\n\n{text}", metadata=m))
    return out


def ingest_file(path: Path) -> int:
    """Load, cut and store one file. Return how many chunks were stored."""
    try:
        docs = load_file(path)
    except ValueError:
        raise
    except Exception as exc:  # a corrupt or unreadable file
        raise ValueError(f"Could not read {path.name}: {exc}") from exc
    chunks = chunk(docs)
    if not chunks:
        raise ValueError(f"No readable text found in {path.name} (a scanned PDF has no text layer).")
    return store.add_chunks(chunks)


def main() -> None:
    import argparse
    import logging
    import sys

    from app.config import get_settings

    parser = argparse.ArgumentParser(description="Load documents into the Pinecone knowledge base.")
    parser.add_argument("folder", nargs="?", type=Path, help="folder with documents (subfolders are read too). Default: kb_dir in app/config.py")
    parser.add_argument("--reset", action="store_true", help="first delete every stored chunk in the namespace")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("app").setLevel(logging.INFO)  # show our own progress; keep the Pinecone and HTTP chatter quiet

    s = get_settings()
    folder = args.folder or s.kb_dir
    files = sorted(f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED)
    print(f"index: {s.pinecone_index_name} | namespace: {s.pinecone_namespace} | model: {s.embedding_model}")
    print(f"folder: {folder} | {len(files)} documents")
    if not files:
        sys.exit(f"No documents found in {folder}")
    names = [f.name for f in files]
    if len(set(names)) < len(names):
        sys.exit("Two files share a name. Rename one: the file name is how its chunks are tracked.")
    if args.reset:
        answer = input(f"Delete ALL stored chunks in namespace '{s.pinecone_namespace}'? Type yes to continue: ")
        if answer.strip().lower() != "yes":
            sys.exit("Cancelled. Nothing was changed.")
        store.reset()
    total = 0
    for file in files:
        try:
            stored = ingest_file(file)
        except ValueError as exc:
            print(f"  skipped {file.name}: {exc}")
            continue
        print(f"  {file.name}: {stored} chunks")
        total += stored
    print(f'Done: {total} chunks. Check with: python -m app.rag.store "How do I connect to the VPN from home?"')


if __name__ == "__main__":
    main()
