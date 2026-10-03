import os
import sys
import subprocess
import shutil

def build():
    print("Starting build process...")
    
    # Ensure dependencies are installed (optional, assuming they are or user will install)
    
    # Run PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--icon=app_icon.ico",
        "--name=AIA_PDF_Extractor",
        "--add-data=index.html;.",
        "--add-data=assets;assets",
        "--hidden-import=webview",
        "--hidden-import=olefile",
        "main.py"
    ]
    
    print("Executing PyInstaller command:", " ".join(cmd))
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("Build successful! Executable is located in the 'dist' folder.")
    else:
        print("Build failed.")

if __name__ == '__main__':
    build()
