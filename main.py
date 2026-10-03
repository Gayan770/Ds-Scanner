import sys
import os
import json
import threading
from pathlib import Path
import webview

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def sanitize_filename(name: str) -> str:
    import re
    clean = re.sub(r'[\r\n\\/*?:"<>|]', "_", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "extracted_document"

def get_unique_path(target_dir: Path, filename: str) -> Path:
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
    return b"%PDF" in data[:1024]

def parse_ole10_native(stream_bytes: bytes) -> tuple[str | None, bytes]:
    import struct
    if len(stream_bytes) < 6:
        return None, stream_bytes
    pos = 6
    label = None
    null_idx = stream_bytes.find(b"\x00", pos)
    if null_idx != -1:
        try:
            label = stream_bytes[pos:null_idx].decode("latin1", errors="replace").strip()
        except Exception:
            label = None
        pos = null_idx + 1
    null_idx2 = stream_bytes.find(b"\x00", pos)
    if null_idx2 != -1:
        pos = null_idx2 + 1
    pdf_idx = stream_bytes.find(b"%PDF", pos)
    if pdf_idx != -1:
        payload = stream_bytes[pdf_idx:]
    else:
        payload = None
    return label, (payload if payload is not None else stream_bytes)

def extract_pdf_from_ole(ole_bytes: bytes, index: int) -> tuple[str | None, bytes | None]:
    import io
    import olefile
    if not olefile.isOleFile(io.BytesIO(ole_bytes)):
        if is_pdf(ole_bytes):
            return f"file_{index}.pdf", ole_bytes
        return None, None
    with olefile.OleFileIO(io.BytesIO(ole_bytes)) as ole:
        for item in ole.listdir():
            if len(item) == 1 and item[0].upper() == "CONTENTS":
                contents = ole.openstream(item).read()
                if is_pdf(contents):
                    return f"document_{index}.pdf", contents
        if ole.exists("\x01Ole10Native"):
            raw_stream = ole.openstream("\x01Ole10Native").read()
            label, payload = parse_ole10_native(raw_stream)
            if is_pdf(payload):
                clean_label = Path(label).name if label else f"attachment_{index}.pdf"
                if not clean_label.lower().endswith(".pdf"):
                    clean_label = f"{clean_label}.pdf"
                return clean_label, payload
    if is_pdf(ole_bytes):
        return f"object_{index}.pdf", ole_bytes
    return None, None

def extract_pdfs(docx_path: str | Path, output_base_dir: str | Path | None = None) -> tuple[Path, int]:
    import zipfile
    source = Path(docx_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"File not found: {source}")
    root_dir = Path(output_base_dir or source.parent) / source.stem
    root_dir.mkdir(parents=True, exist_ok=True)
    pdf_count = 0
    with zipfile.ZipFile(source, "r") as z:
        embed_entries = [name for name in z.namelist() if name.startswith("word/embeddings/") and not name.endswith("/")]
        if not embed_entries:
            return root_dir, pdf_count
        for idx, entry in enumerate(embed_entries, start=1):
            raw_data = z.read(entry)
            filename, payload = None, None
            if entry.lower().endswith((".bin", ".ole")):
                filename, payload = extract_pdf_from_ole(raw_data, idx)
            else:
                if is_pdf(raw_data):
                    filename = Path(entry).name
                    payload = raw_data
            if filename and payload:
                safe_name = sanitize_filename(filename)
                dest_path = get_unique_path(root_dir, safe_name)
                dest_path.write_bytes(payload)
                pdf_count += 1
    if pdf_count == 0 and root_dir.exists() and not any(root_dir.iterdir()):
        root_dir.rmdir()
    return root_dir, pdf_count

class Api:
    def __init__(self):
        self.window = None

    def set_window(self, window):
        self.window = window

    def minimize(self):
        if self.window: self.window.minimize()

    def maximize(self):
        if self.window: self.window.toggle_fullscreen()
        
    def close(self):
        if self.window: self.window.destroy()

    def select_directory(self):
        try:
            result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
            if not result:
                return {"success": False, "error": "No folder selected"}
            folder_path = result[0]
            files = []
            for p in Path(folder_path).glob("*.docx"):
                if not p.name.startswith("~"):
                    files.append({"name": p.name, "path": str(p)})
            return {"success": True, "folder_path": folder_path, "files": files}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def start_pipeline(self, folder_path):
        t = threading.Thread(target=self._run_pipeline, args=(folder_path,), daemon=True)
        t.start()
        return {"success": True}

    def _run_pipeline(self, folder_path):
        try:
            docx_files = [p for p in Path(folder_path).glob("*.docx") if not p.name.startswith("~")]
            total_docs = len(docx_files)
            total_extracted = 0
            
            output_base = Path(folder_path) / "Extracted_PDFs"
            output_base.mkdir(exist_ok=True)

            for idx, docx_path in enumerate(docx_files, start=1):
                progress_percent = int(((idx - 1) / total_docs) * 100) if total_docs > 0 else 0
                self.window.evaluate_js(f"if (window.onPipelineProgress) window.onPipelineProgress({{ 'current_doc': {idx}, 'total_docs': {total_docs}, 'doc_name': {json.dumps(docx_path.name)}, 'percent': {progress_percent}, 'message': {json.dumps(f'Extracting from {docx_path.name}')} }})")
                try:
                    out_dir, count = extract_pdfs(docx_path, output_base)
                    total_extracted += count
                except Exception as e:
                    print(f"Error on {docx_path}: {e}")
            
            self.window.evaluate_js(f"if (window.onPipelineProgress) window.onPipelineProgress({{ 'percent': 100, 'message': 'Complete' }})")
            self.window.evaluate_js(f"if (window.onPipelineComplete) window.onPipelineComplete({{ 'total_docs': {total_docs}, 'total_extracted': {total_extracted}, 'output_dir': {json.dumps(str(output_base))} }})")
        except Exception as e:
            self.window.evaluate_js(f"if (window.onPipelineError) window.onPipelineError({{ 'error': {json.dumps(str(e))} }})")

    def open_output_dir(self, path):
        if os.path.exists(path):
            os.startfile(path)

def main():
    api = Api()
    html_path = get_resource_path("index.html")
    
    # We removed min_size because forcing minimum bounds during 
    # initial DOM layout causes freezing issues when maximized on EdgeChromium.
    window = webview.create_window(
        'AIA - Embedded PDF Extractor', 
        url=html_path,
        js_api=api, 
        width=1024, 
        height=768,
        background_color='#F8FAFC'
    )
    api.set_window(window)
    
    # Removed problematic on_shown maximize handler that caused freezing on startup
    
    webview.start(gui='edgechromium', debug=False)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].endswith('.docx'):
        import argparse
        parser = argparse.ArgumentParser(description="Extract embedded PDFs from a Word document.")
        parser.add_argument("docx_path", help="Path to target .docx file")
        parser.add_argument("-o", "--output-dir", help="Directory where output folder will be created", default=None)
        args = parser.parse_args()
        try:
            out_dir, count = extract_pdfs(args.docx_path, args.output_dir)
            print(f"Extracted {count} PDFs to {out_dir}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        main()
