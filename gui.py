#!/usr/bin/env python3
"""
Dashboard GUI Backend - Zero-dependency Python server.
Serves a beautiful, dark-theme web dashboard in the browser and handles
all back-end CLI script executions with real-time SSE log streaming.
"""

import http.server
import socketserver
import json
import os
import sys
import uuid
import queue
import threading
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

PORT = 8081
WORKSPACE_DIR = Path(__file__).parent.resolve()

# Global dictionary to track active background tasks and output streams
# task_id -> { 'process': Popen, 'queue': queue.Queue, 'status': str }
TASKS = {}
TASKS_LOCK = threading.Lock()

# Supported file extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".webp", ".png", ".tif", ".tiff"}


def run_process_reader(process, task_queue, task_id):
    """Reads subprocess output line-by-line and pushes it into the SSE queue."""
    for line in iter(process.stdout.readline, ''):
        task_queue.put(line.rstrip('\r\n'))
    
    process.stdout.close()
    return_code = process.wait()
    
    with TASKS_LOCK:
        if task_id in TASKS:
            TASKS[task_id]['status'] = 'success' if return_code == 0 else 'error'
            
    # Push sentinel to signal completion
    task_queue.put(None)


class DashboardRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress standard request logs to keep terminal output clean
        pass

    def send_json(self, data, status=200):
        """Helper to send a JSON response."""
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        except Exception as e:
            print(f"Error sending JSON response: {e}")

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path_str = url.path
        query = urllib.parse.parse_qs(url.query)

        # 1. Main HTML serve
        if path_str == "/" or path_str == "/index.html":
            index_path = WORKSPACE_DIR / "index.html"
            if not index_path.exists():
                self.send_error(404, "index.html not found in workspace")
                return
            
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            with open(index_path, "rb") as f:
                self.wfile.write(f.read())
            return

        # 2. File tree explorer API
        if path_str == "/api/browse":
            target_dir_str = query.get("path", ["."])[0]
            try:
                # Safe path resolution
                if target_dir_str == ".":
                    target_dir = WORKSPACE_DIR
                else:
                    target_dir = Path(target_dir_str).resolve()

                if not target_dir.exists() or not target_dir.is_dir():
                    self.send_json({"error": "Path is not a directory or does not exist"}, 400)
                    return

                directories = []
                files = []

                for entry in sorted(os.scandir(target_dir), key=lambda e: e.name.lower()):
                    if entry.is_dir():
                        if not entry.name.startswith("."): # Hide hidden system directories
                            directories.append({
                                "name": entry.name,
                                "path": str(Path(entry.path).resolve())
                            })
                    else:
                        if not entry.name.startswith(".") and Path(entry.name).suffix.lower() in SUPPORTED_EXTENSIONS:
                            files.append({
                                "name": entry.name,
                                "size": entry.stat().st_size
                            })

                parent_path = str(target_dir.parent.resolve()) if target_dir != target_dir.parent else None

                self.send_json({
                    "current_path": str(target_dir.resolve()),
                    "parent": parent_path,
                    "directories": directories,
                    "files": files
                })
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        # 3. Serving active local images for walkthrough previews
        if path_str == "/api/image":
            img_path_str = query.get("path", [""])[0]
            if not img_path_str:
                self.send_error(400, "Missing image path")
                return
            
            img_path = Path(img_path_str).resolve()
            if not img_path.exists() or not img_path.is_file():
                self.send_error(404, "Image file not found")
                return

            suffix = img_path.suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                self.send_error(400, "Unsupported image type")
                return

            # Determine content type
            mime_type = "image/jpeg"
            if suffix == ".webp":
                mime_type = "image/webp"
            elif suffix == ".png":
                mime_type = "image/png"
            elif suffix in (".tiff", ".tif"):
                mime_type = "image/tiff"

            try:
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Cache-Control", "max-age=3600")
                self.end_headers()
                with open(img_path, "rb") as f:
                    self.wfile.write(f.read())
            except Exception as e:
                print(f"Error serving image: {e}")
            return

        # 4. Walkthrough recursive folder list fetcher
        if path_str == "/api/interactive-exif/folders":
            root_path_str = query.get("path", ["."])[0]
            try:
                root_path = Path(root_path_str).resolve()
                if not root_path.exists() or not root_path.is_dir():
                    self.send_json({"error": "Invalid root path"}, 400)
                    return

                folders = []
                
                # Check root directory first
                root_images = []
                for entry in sorted(os.scandir(root_path), key=lambda e: e.name.lower()):
                    if entry.is_file() and Path(entry.name).suffix.lower() in SUPPORTED_EXTENSIONS:
                        root_images.append({
                            "name": entry.name,
                            "path": str(Path(entry.path).resolve())
                        })
                if root_images:
                    folders.append({
                        "display_name": "Root Folder",
                        "path": str(root_path),
                        "images": root_images
                    })

                # Recursively walk subdirectories
                for dirpath, dirnames, filenames in os.walk(root_path):
                    # Skip output or downsized directories if nested inside input folder
                    # by checking names
                    dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                    
                    for dirname in sorted(dirnames):
                        sub_path = Path(dirpath) / dirname
                        sub_images = []
                        
                        for entry in sorted(os.scandir(sub_path), key=lambda e: e.name.lower()):
                            if entry.is_file() and Path(entry.name).suffix.lower() in SUPPORTED_EXTENSIONS:
                                sub_images.append({
                                    "name": entry.name,
                                    "path": str(Path(entry.path).resolve())
                                })
                        
                        if sub_images:
                            rel_path = sub_path.relative_to(root_path)
                            folders.append({
                                "display_name": str(rel_path),
                                "path": str(sub_path.resolve()),
                                "images": sub_images
                            })

                self.send_json({"folders": folders})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        # 5. Server-Sent Events real-time log output stream
        if path_str == "/api/logs":
            task_id = query.get("task_id", [""])[0]
            if not task_id:
                self.send_error(400, "Missing task ID")
                return

            with TASKS_LOCK:
                task_exists = task_id in TASKS

            if not task_exists:
                self.send_error(404, "Task ID not found")
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            task_queue = TASKS[task_id]['queue']

            while True:
                try:
                    line = task_queue.get(timeout=30)
                    if line is None:
                        # Process completed
                        status = TASKS[task_id]['status']
                        self.wfile.write(f"data: {json.dumps({'done': True, 'status': status})}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        
                        # Clean up task
                        with TASKS_LOCK:
                            if task_id in TASKS:
                                del TASKS[task_id]
                        break
                    
                    # Stream single line of log
                    self.wfile.write(f"data: {json.dumps({'done': False, 'line': line})}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Keep-alive heartbeat comment to prevent browser timeout
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                except Exception as e:
                    print(f"SSE client disconnected: {e}")
                    break
            return

        self.send_error(404, "Page not found")

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        path_str = url.path

        if path_str.startswith("/api/run/"):
            tool_name = path_str.split("/")[-1]
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                params = json.loads(body)
            except Exception as e:
                self.send_json({"error": f"Invalid JSON payload: {e}"}, 400)
                return

            # Construct arguments based on tool name
            args = []
            
            if tool_name == "clipper":
                inp = params.get("input", "input")
                out = params.get("output", "output")
                shave = str(params.get("shave", 10))
                threshold = str(params.get("threshold", 240))
                fmt = params.get("format", "webp")
                quality = str(params.get("quality", 90))
                
                args = [sys.executable, "scanner_clipper.py", "-i", inp, "-o", out, "--shave", shave, "--threshold", threshold, "-f", fmt, "-q", quality]
                if params.get("debug"):
                    args.append("--debug")

            elif tool_name == "resizer":
                inp = params.get("input", "output")
                out = params.get("output", "downsized")
                fmt = params.get("format", "jpg")
                quality = str(params.get("quality", 90))
                
                args = [sys.executable, "image_resizer.py", "-i", inp, "-o", out, "-f", fmt, "-q", quality]
                
                if "scale" in params:
                    args.extend(["-s", str(params["scale"])])
                elif "max_dim" in params:
                    args.extend(["--max-dim", str(params["max_dim"])])

                if not params.get("recursive", True):
                    args.append("--no-recursive")

            elif tool_name == "exif":
                inp = params.get("input", "output")
                quality = str(params.get("quality", 95))
                increment = str(params.get("increment", 60))
                
                args = [sys.executable, "exif_date_editor.py", "-i", inp, "-q", quality, "--increment", increment]
                
                if params.get("output"):
                    args.extend(["-o", params["output"]])
                if params.get("date"):
                    args.extend(["-d", params["date"]])
                if params.get("random_time"):
                    args.append("--random-time")
                if params.get("dry_run"):
                    args.append("--dry-run")
                if params.get("no_recursive"):
                    args.append("--no-recursive")

            else:
                self.send_json({"error": "Unknown tool specified"}, 400)
                return

            try:
                # Trigger process execution in background thread
                process = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=str(WORKSPACE_DIR)
                )
                
                task_id = str(uuid.uuid4())
                task_queue = queue.Queue()
                
                with TASKS_LOCK:
                    TASKS[task_id] = {
                        "process": process,
                        "queue": task_queue,
                        "status": "running"
                    }
                
                # Start logging output reader thread
                thread = threading.Thread(target=run_process_reader, args=(process, task_queue, task_id))
                thread.daemon = True
                thread.start()

                self.send_json({"task_id": task_id})
            except Exception as e:
                self.send_json({"error": f"Failed to execute process: {e}"}, 500)
            return

        self.send_error(404, "Endpoint not found")


def main():
    # Attempt to start server
    handler = DashboardRequestHandler
    
    # Simple port finder
    server_port = PORT
    server = None
    while server_port < PORT + 10:
        try:
            server = socketserver.TCPServer(("", server_port), handler)
            break
        except OSError:
            print(f"Port {server_port} already in use. Retrying on port {server_port + 1}...")
            server_port += 1

    if not server:
        print("ERROR: Could not find an open port to start the server.")
        sys.exit(1)

    url = f"http://localhost:{server_port}"
    print("\n" + "=" * 60)
    print("  🚀 Photo Scanning Utilities Dashboard is Starting!")
    print(f"  🔗 Server is running at: {url}")
    print("  Press Ctrl+C in this terminal to shut down.")
    print("=" * 60 + "\n")

    # Automatic browser launching disabled to guarantee stability in headless/sandbox environments.
    # The printed URL is fully clickable in standard terminals.
    pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        
        # Terminate any active background subprocesses
        with TASKS_LOCK:
            for task in TASKS.values():
                try:
                    task['process'].terminate()
                except Exception:
                    pass
        server.server_close()
        print("Done.")


if __name__ == "__main__":
    main()
