import argparse
import io
import re
import struct
import sys
import zipfile
from pathlib import Path
import olefile

def sanitize_filename(name: str) -> str:
    """Strips invalid filesystem characters, path separators, and control codes."""
    clean = re.sub(r'[\r\n\\/*?:"<>|]', "_", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "extracted_document"

def get_unique_path(target_dir: Path, filename: str) -> Path:
    """Avoids overwriting by appending an incremental index."""
    dest = target_dir / filename
    if not dest.exists():
        return dest

    stem, ext = dest.stem, dest.suffix
    counter = 1
    while dest.exists():
        dest = target_dir / f"{stem}_{counter}{ext}"
        counter += 1
    return dest

def is_pdf(data: bytes) -> bool:
    """Quick byte signature check for PDF payloads."""
    return b"%PDF" in data[:1024]

def parse_ole10_native(stream_bytes: bytes) -> tuple[str | None, bytes]:
    """
    Parses \\x01Ole10Native with dynamic payload offset detection.
    """
    if len(stream_bytes) < 6:
        return None, stream_bytes

    pos = 6  # Skip total size (4 bytes) + type flag (2 bytes)
    label = None

    # 1. Read original filename label
    null_idx = stream_bytes.find(b"\x00", pos)
    if null_idx != -1:
        try:
            label = stream_bytes[pos:null_idx].decode("latin1", errors="replace").strip()
        except Exception:
            label = None
        pos = null_idx + 1

    # 2. Skip secondary path if present
    null_idx2 = stream_bytes.find(b"\x00", pos)
    if null_idx2 != -1:
        pos = null_idx2 + 1

    # 3. Dynamic search for NativeDataSize matching remaining stream length
    payload = None
    stream_len = len(stream_bytes)
    for i in range(pos, stream_len - 4):
        candidate_len = struct.unpack_from("<I", stream_bytes, i)[0]
        if candidate_len == stream_len - (i + 4) and candidate_len > 0:
            payload = stream_bytes[i + 4:]
            break

    # 4. Fallback byte-carving targeted explicitly for PDFs
    if payload is None:
        idx = stream_bytes.find(b"%PDF")
        if idx != -1:
            payload = stream_bytes[idx:]

    return label, (payload if payload is not None else stream_bytes)

def extract_pdf_from_ole(ole_bytes: bytes, index: int) -> tuple[str | None, bytes | None]:
    """Decompounds OLE object binary, returning only validated PDF payloads."""
    # If it's not a structured OLE file, check if the raw bytes are just a PDF
    if not olefile.isOleFile(io.BytesIO(ole_bytes)):
        if is_pdf(ole_bytes):
            return f"file_{index}.pdf", ole_bytes
        return None, None

    with olefile.OleFileIO(io.BytesIO(ole_bytes)) as ole:
        # Case 1: Adobe Acrobat OLE object (raw data in CONTENTS stream)
        for item in ole.listdir():
            if len(item) == 1 and item[0].upper() == "CONTENTS":
                contents = ole.openstream(item).read()
                if is_pdf(contents):
                    return f"document_{index}.pdf", contents

        # Case 2: Packaged file inside \x01Ole10Native
        if ole.exists("\x01Ole10Native"):
            raw_stream = ole.openstream("\x01Ole10Native").read()
            label, payload = parse_ole10_native(raw_stream)

            if is_pdf(payload):
                clean_label = Path(label).name if label else f"attachment_{index}.pdf"
                if not clean_label.lower().endswith(".pdf"):
                    clean_label = f"{clean_label}.pdf"
                return clean_label, payload

    # Fallback: Check if the entire wrapper happens to prefix a PDF
    if is_pdf(ole_bytes):
        return f"object_{index}.pdf", ole_bytes

    # Not a PDF, ignore it
    return None, None

def extract_pdfs(docx_path: str | Path, output_base_dir: str | Path | None = None) -> Path:
    source = Path(docx_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"File not found: {source}")

    # Output directly to a single folder named after the document
    root_dir = Path(output_base_dir or source.parent) / f"{source.stem}_pdfs"
    root_dir.mkdir(parents=True, exist_ok=True)

    pdf_count = 0

    with zipfile.ZipFile(source, "r") as z:
        embed_entries = [
            name for name in z.namelist()
            if name.startswith("word/embeddings/") and not name.endswith("/")
        ]

        if not embed_entries:
            print(f"No embedded objects located in: {source.name}")
            return root_dir

        for idx, entry in enumerate(embed_entries, start=1):
            raw_data = z.read(entry)
            filename, payload = None, None

            # Process OLE binaries
            if entry.lower().endswith((".bin", ".ole")):
                filename, payload = extract_pdf_from_ole(raw_data, idx)
            # Process direct embeddings
            else:
                if is_pdf(raw_data):
                    filename = Path(entry).name
                    payload = raw_data

            # Write to disk only if a PDF was successfully identified
            if filename and payload:
                safe_name = sanitize_filename(filename)
                dest_path = get_unique_path(root_dir, safe_name)
                dest_path.write_bytes(payload)
                pdf_count += 1
                print(f"  [+] Extracted [PDF]: {dest_path.name} ({len(payload):,} bytes)")

    print(f"\nCompleted PDF extraction for: {source.name}")
    print(f"Location: {root_dir}")
    print(f"Summary:  {pdf_count} PDFs extracted")
    
    # Clean up empty directory if no PDFs were found
    if pdf_count == 0 and root_dir.exists() and not any(root_dir.iterdir()):
        root_dir.rmdir()
        
    return root_dir

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract embedded PDFs from a Word document.")
    parser.add_argument("docx_path", help="Path to target .docx file")
    parser.add_argument("-o", "--output-dir", help="Directory where output folder will be created", default=None)
    args = parser.parse_args()

    try:
        extract_pdfs(args.docx_path, args.output_dir)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)