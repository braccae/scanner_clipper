#!/usr/bin/env python3
"""
Desktop App Wrapper - Wraps the Photo Dashboard into a native desktop window using pywebview.
"""

import sys
import threading
import time
import socket
from pathlib import Path

# Import our existing local http server module
import gui

try:
    import webview
except ImportError:
    print("\n" + "=" * 60)
    print("  ERROR: 'pywebview' is not installed.")
    print("  Please install it to run this project as a desktop app:")
    print("  ")
    print("    pip install pywebview")
    print("    ")
    print("  Or run the web server dashboard instead:")
    print("    python gui.py")
    print("=" * 60 + "\n")
    sys.exit(1)


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def start_server_backend():
    """Starts the Python HTTP Server on a separate thread."""
    # Run the existing gui.py server entrypoint
    gui.main()


def main():
    port = gui.PORT
    
    # Start the local HTTP server in a daemon thread
    server_thread = threading.Thread(target=start_server_backend, daemon=True)
    server_thread.start()
    
    # Wait for the server to bind and start listening
    attempts = 0
    while not is_port_in_use(port) and attempts < 30:
        time.sleep(0.1)
        attempts += 1
        
    print(f"Backend server is ready on port {port}. Spawning desktop window...")
    
    # Create the native desktop window pointing to our local backend server
    # We set a clean widescreen layout suitable for dashboard configuration
    window = webview.create_window(
        title="Photo Scanning & Metadata Utilities",
        url=f"http://localhost:{port}",
        width=1280,
        height=850,
        min_size=(900, 600),
        resizable=True
    )
    
    # Start the native OS GUI window loop (blocks until the window is closed)
    webview.start()
    print("Desktop window closed. Exiting.")


if __name__ == "__main__":
    main()
