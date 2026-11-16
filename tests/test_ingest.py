import sys
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from langchain_core.documents import Document

from app.config import get_settings
from app.rag import ingest, store

KB = Path(__file__).resolve().parents[1] / "data" / "kb"

GUIDE = """# VPN Guide

- Document ID: NR-IT-006

## Connect from home

To connect to the VPN from home, open the NovaConnect client and approve the MFA prompt.

## Error codes

Error NC-203 means the MFA prompt timed out.
"""


def make_pdf(path, text):
    """Write a one-page PDF by hand, so the test needs no PDF-writing library."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(out)


def test_markdown_is_cut_at_headings_and_each_chunk_names_its_section(tmp_path):
    file = tmp_path / "vpn-guide.md"
    file.write_text(GUIDE, encoding="utf-8")
    chunks = ingest.chunk(ingest.load_file(file))
    connect = next(c for c in chunks if "approve the MFA prompt" in c.page_content)
    assert connect.page_content.startswith("VPN Guide > Connect from home\n\n")
    assert connect.metadata == {"source": "vpn-guide.md", "title": "VPN Guide", "section": "Connect from home"}
    assert any(c.page_content.startswith("VPN Guide > Error codes") for c in chunks)


def test_a_long_section_is_cut_into_chunks_of_sensible_size(tmp_path):
    file = tmp_path / "long.md"
    file.write_text("# Long\n\n## Part\n\n" + "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(12)), encoding="utf-8")
    chunks = ingest.chunk(ingest.load_file(file))
    assert len(chunks) > 3
    assert all(len(c.page_content) <= 1000 for c in chunks)
    assert all(c.page_content.startswith("Long > Part") for c in chunks)


def test_plain_text_uses_the_file_name_as_its_label(tmp_path):
    file = tmp_path / "wifi_rules.txt"
    file.write_text("Use the staff network.", encoding="utf-8")
    (chunk,) = ingest.chunk(ingest.load_file(file))
    assert chunk.page_content == "wifi rules\n\nUse the staff network."


def test_word_headings_become_sections(tmp_path):
    file = tmp_path / "policy.docx"
    doc = DocxDocument()
    doc.add_heading("Password Policy", level=1)
    doc.add_heading("Resetting", level=2)
    doc.add_paragraph("Use the password portal.")
    doc.save(file)
    (chunk,) = ingest.chunk(ingest.load_file(file))
    assert chunk.page_content == "Password Policy > Resetting\n\nUse the password portal."


def test_pdf_pages_keep_their_page_number(tmp_path):
    file = tmp_path / "guide.pdf"
    make_pdf(file, "Printing needs a badge")
    (doc,) = ingest.load_file(file)
    assert "Printing needs a badge" in doc.page_content
    assert doc.metadata == {"source": "guide.pdf", "page": 1}


def test_an_empty_document_is_refused_with_a_reason(tmp_path):
    file = tmp_path / "blank.md"
    file.write_text("  \n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No readable text"):
        ingest.ingest_file(file)


def test_a_corrupt_pdf_is_refused_with_a_reason(tmp_path):
    file = tmp_path / "broken.pdf"
    file.write_bytes(b"this is not a pdf")
    with pytest.raises(ValueError, match="Could not read broken.pdf"):
        ingest.ingest_file(file)


def test_an_ingested_file_can_be_found_again(pinecone, tmp_path):
    file = tmp_path / "vpn-guide.md"
    file.write_text(GUIDE, encoding="utf-8")
    assert ingest.ingest_file(file) >= 2
    best = store.search("connect to the VPN from home")[0]
    assert best.metadata["source"] == "vpn-guide.md"
    assert "approve the MFA prompt" in best.page_content


def test_every_knowledge_base_document_cuts_into_clean_chunks():
    files = sorted(KB.rglob("*.md"))
    if not files:
        pytest.skip("data/kb has no documents yet")
    for file in files:
        chunks = ingest.chunk(ingest.load_file(file))
        assert chunks, file.name
        assert all(c.page_content.strip() and len(c.page_content) <= 1100 for c in chunks), file.name
        assert all(c.metadata["source"] == file.name for c in chunks)


def test_the_lines_under_the_title_join_the_first_section(tmp_path):
    file = tmp_path / "vpn-guide.md"
    file.write_text(GUIDE, encoding="utf-8")
    chunks = ingest.chunk(ingest.load_file(file))
    assert len(chunks) == 2  # no tiny chunk for the document id
    assert chunks[0].page_content.startswith("VPN Guide > Connect from home")
    assert "Document ID: NR-IT-006" in chunks[0].page_content


def run_command(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["ingest", *map(str, args)])
    ingest.main()


def test_the_command_reads_subfolders_and_skips_other_file_types(pinecone, tmp_path, monkeypatch, capsys):
    (tmp_path / "batch-1").mkdir()
    (tmp_path / "batch-1" / "a.md").write_text("# A\n\n## Part\n\nalpha text", encoding="utf-8")
    (tmp_path / "batch-1" / "bad.pdf").write_bytes(b"not a pdf")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "questions.json").write_text("[]", encoding="utf-8")
    run_command(monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert "a.md: 1 chunks" in out
    assert "skipped bad.pdf" in out
    assert "questions.json" not in out
    assert store.count() == 1


def test_without_a_folder_the_command_reads_the_kb_dir_setting(pinecone, tmp_path, monkeypatch, capsys):
    (tmp_path / "batch-1").mkdir()
    (tmp_path / "batch-1" / "a.md").write_text("# A\n\n## Part\n\nalpha text", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "kb_dir", tmp_path)
    run_command(monkeypatch)
    out = capsys.readouterr().out
    assert f"folder: {tmp_path} | 1 documents" in out
    assert "a.md: 1 chunks" in out


def test_the_default_kb_folder_is_anchored_to_the_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    kb_dir = get_settings().kb_dir
    assert kb_dir.is_absolute()
    assert kb_dir.parts[-2:] == ("data", "kb")


def test_the_command_refuses_two_files_with_the_same_name(pinecone, tmp_path, monkeypatch):
    for sub in ("one", "two"):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "same.md").write_text("text", encoding="utf-8")
    with pytest.raises(SystemExit, match="share a name"):
        run_command(monkeypatch, tmp_path)
    assert pinecone.live is None  # nothing was created


def test_the_command_says_so_when_the_folder_has_no_documents(pinecone, tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="No documents found"):
        run_command(monkeypatch, tmp_path)


def test_reset_asks_first_and_only_a_yes_empties_the_namespace(pinecone, tmp_path, monkeypatch):
    (tmp_path / "a.md").write_text("# A\n\n## Part\n\nalpha text", encoding="utf-8")
    run_command(monkeypatch, tmp_path)
    (tmp_path / "a.md").unlink()
    (tmp_path / "b.md").write_text("# B\n\n## Part\n\nbeta text", encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(SystemExit, match="Cancelled"):
        run_command(monkeypatch, tmp_path, "--reset")
    assert sorted(pinecone.live.data["test-ns"]) == ["a.md::0001"]

    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    run_command(monkeypatch, tmp_path, "--reset")
    assert sorted(pinecone.live.data["test-ns"]) == ["b.md::0001"]
