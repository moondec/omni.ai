import sys
import os

# --- Windows DLL workaround for PySide6 in Conda environments ---
if os.name == 'nt':
    # 1. Add Conda's Library/bin if available
    conda_prefix = os.environ.get('CONDA_PREFIX')
    if conda_prefix:
        dll_path = os.path.join(conda_prefix, 'Library', 'bin')
        if os.path.exists(dll_path):
            try:
                os.add_dll_directory(dll_path)
            except Exception:
                pass

    # 2. Add PySide6 site-packages directory
    try:
        import site
        for site_pkg in site.getsitepackages():
            pyside_dir = os.path.join(site_pkg, "PySide6")
            if os.path.exists(pyside_dir):
                os.add_dll_directory(pyside_dir)
                break
    except Exception:
        pass

    # 3. Conda often leaks SSL_CERT_FILE into the global user environment.
    # If using venv, this path might not exist and will crash httpx/OpenAI.
    ssl_cert = os.environ.get('SSL_CERT_FILE')
    if ssl_cert and not os.path.exists(ssl_cert):
        del os.environ['SSL_CERT_FILE']
        
    curl_ca = os.environ.get('CURL_CA_BUNDLE')
    if curl_ca and not os.path.exists(curl_ca):
        del os.environ['CURL_CA_BUNDLE']
# ----------------------------------------------------------------

# Add project root to path if running directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from pcss_llm_app.ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Optional: Set styling
    app.setStyle("Fusion")

    # Set App Icon Global
    logo_path = os.path.join(os.path.dirname(__file__), "..", "resources", "logo.png")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
