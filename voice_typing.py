import sys
import os
import json
import wave
import tempfile
import threading
import shutil
import platform
import numpy as np

try:
    import sounddevice as sd
    import soundfile as sf
    from pynput import keyboard
    from openai import OpenAI
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
    from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
    from PySide6.QtCore import QObject, Signal, Slot, QTimer
    import time
    import subprocess
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Please install requirements: pip install pynput sounddevice soundfile numpy PySide6 openai")
    sys.exit(1)

CONFIG_FILE = "dictation_settings.json"

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

PLATFORM = sys.platform  # 'darwin', 'win32', 'linux'

def _detect_linux_display_server():
    """Detect whether the Linux session is X11 or Wayland."""
    xdg = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if xdg == "wayland":
        return "wayland"
    if xdg == "x11":
        return "x11"
    # Fallback heuristics
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"

LINUX_DISPLAY_SERVER = _detect_linux_display_server() if PLATFORM == "linux" else None

def _check_tool(name):
    """Return True if *name* is found on PATH."""
    return shutil.which(name) is not None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config():
    conf = {
        "base_url": "https://llm.hpc.pcss.pl/v1",
        "transcription_model": "whisper-large-v3-turbo:0.8b"
    }
    
    # Try to inherit generic settings from main app if they exist
    if os.path.exists("settings.json"):
        try:
            with open("settings.json", 'r') as f:
                main_settings = json.load(f)
                if "base_url" in main_settings:
                    conf["base_url"] = main_settings["base_url"]
                if "transcription_model" in main_settings:
                    conf["transcription_model"] = main_settings["transcription_model"]
        except Exception:
            pass

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            user_conf = json.load(f)
            conf.update(user_conf)
            return conf
            
    with open(CONFIG_FILE, 'w') as f:
        json.dump(conf, f, indent=4)
    return conf

def save_config(conf):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(conf, f, indent=4)

def create_tray_icon(color):
    """Creates a simple colored circle icon for the tray"""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor("transparent"))
    painter = QPainter(pixmap)
    painter.setBrush(QColor(color))
    painter.setPen(QColor(color))
    painter.drawEllipse(2, 2, 28, 28)
    painter.end()
    return QIcon(pixmap)

# ---------------------------------------------------------------------------
# Cross-platform permission / environment checks
# ---------------------------------------------------------------------------

def check_platform_permissions():
    """Check platform-specific permissions and environment.
    
    Returns a list of warning strings (empty == all OK).
    """
    warnings = []

    if PLATFORM == "darwin":
        try:
            script = 'tell application "System Events" to get UI elements enabled'
            output = subprocess.check_output(
                ['osascript', '-e', script], stderr=subprocess.DEVNULL
            )
            if "true" not in output.decode('utf-8').lower():
                warnings.append(
                    "macOS Accessibility permissions NOT detected!\n"
                    "Go to: System Settings -> Privacy & Security -> Accessibility\n"
                    "and enable your Terminal / Python application."
                )
        except Exception:
            warnings.append(
                "Could not verify macOS Accessibility permissions.\n"
                "Ensure Accessibility is enabled in System Settings."
            )

    elif PLATFORM == "win32":
        # pynput on Windows generally works without special permissions.
        # UAC-elevated apps may block input injection to non-elevated windows.
        pass

    elif PLATFORM == "linux":
        if LINUX_DISPLAY_SERVER == "wayland":
            warnings.append(
                "Wayland session detected!\n"
                "pynput global hotkeys and keyboard injection do NOT work\n"
                "under Wayland. Possible workarounds:\n"
                "  1. Switch to an X11 / Xorg session at the login screen.\n"
                "  2. Run this app under XWayland:\n"
                "     env GDK_BACKEND=x11 QT_QPA_PLATFORM=xcb python voice_typing.py\n"
                "  3. Install 'wtype' and 'wl-copy' for Wayland-native text\n"
                "     injection (experimental, hotkeys may still not work)."
            )
        elif LINUX_DISPLAY_SERVER == "x11":
            missing = []
            if not _check_tool("xdotool"):
                missing.append("xdotool")
            if not _check_tool("xclip") and not _check_tool("xsel"):
                missing.append("xclip (or xsel)")
            if missing:
                warnings.append(
                    f"Recommended tools not found: {', '.join(missing)}\n"
                    "These are used as fallback for text injection.\n"
                    "Install them via your package manager, e.g.:\n"
                    "  sudo apt install xdotool xclip   # Debian/Ubuntu\n"
                    "  sudo dnf install xdotool xclip   # Fedora"
                )
        else:
            warnings.append(
                "Could not detect display server (X11 or Wayland).\n"
                "Global hotkeys may not work."
            )

        # Check for system tray support on Linux
        if not _check_tool("dbus-send"):
            pass  # Can't check, just let Qt try
        else:
            # GNOME without AppIndicator extension won't show tray icons
            desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            if "gnome" in desktop:
                warnings.append(
                    "GNOME detected — QSystemTrayIcon may not be visible\n"
                    "without the 'AppIndicator' GNOME Shell extension.\n"
                    "Install it from: https://extensions.gnome.org\n"
                    "or use the 'gnome-shell-extension-appindicator' package."
                )

    return warnings

# ---------------------------------------------------------------------------
# Audio recorder
# ---------------------------------------------------------------------------

class AudioRecorder:
    def __init__(self, samplerate=16000, channels=1):
        self.samplerate = samplerate
        self.channels = channels
        self.recording = False
        self.frames = []
        self.stream = None

    def start(self):
        self.frames = []
        self.recording = True
        self.stream = sd.InputStream(samplerate=self.samplerate, channels=self.channels, callback=self._callback)
        self.stream.start()

    def _callback(self, indata, frames, time, status):
        if self.recording:
            self.frames.append(indata.copy())

    def stop(self):
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        if not self.frames:
            return None, False
        
        recording = np.concatenate(self.frames, axis=0)
        
        # Check if audio is completely silent (common when mic permissions are missing)
        is_silent = np.max(np.abs(recording)) == 0
        
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "dictation_chunk.wav")
        sf.write(temp_file, recording, self.samplerate)
        return temp_file, is_silent

# ---------------------------------------------------------------------------
# Hotkey manager
# ---------------------------------------------------------------------------

class HotkeyManager:
    def __init__(self, start_callback, stop_callback):
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.is_recording = False
        
        self.ctrl_pressed = False
        self.space_pressed = False
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()

    def on_press(self, key):
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l):
            self.ctrl_pressed = True
        elif key == keyboard.Key.space:
            self.space_pressed = True
            
        if self.ctrl_pressed and self.space_pressed and not self.is_recording:
            self.is_recording = True
            self.start_callback()

    def on_release(self, key):
        was_recording = self.is_recording
        
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l):
            self.ctrl_pressed = False
        elif key == keyboard.Key.space:
            self.space_pressed = False
            
        if was_recording and not (self.ctrl_pressed and self.space_pressed):
            self.is_recording = False
            self.stop_callback()

# ---------------------------------------------------------------------------
# Cross-platform text injection helpers
# ---------------------------------------------------------------------------

def _type_via_applescript(text):
    """macOS fallback: inject text via osascript keystroke command."""
    try:
        safe = text.replace('\\', '\\\\').replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{safe}"'
        subprocess.run(['osascript', '-e', script], check=True,
                       timeout=5, capture_output=True)
        return True
    except Exception as e:
        print(f"AppleScript fallback failed: {e}")
        return False


def _type_via_xdotool(text):
    """Linux/X11 fallback: inject text using xdotool."""
    if not _check_tool("xdotool"):
        return False
    try:
        subprocess.run(['xdotool', 'type', '--clearmodifiers', '--', text],
                       check=True, timeout=10, capture_output=True)
        return True
    except Exception as e:
        print(f"xdotool fallback failed: {e}")
        return False


def _type_via_xclip_paste(text):
    """Linux/X11 fallback: copy to clipboard via xclip, then simulate Ctrl+V."""
    clip_tool = None
    if _check_tool("xclip"):
        clip_tool = ["xclip", "-selection", "clipboard"]
    elif _check_tool("xsel"):
        clip_tool = ["xsel", "--clipboard", "--input"]
    if not clip_tool:
        return False
    if not _check_tool("xdotool"):
        return False
    try:
        proc = subprocess.run(clip_tool, input=text.encode("utf-8"),
                              check=True, timeout=5, capture_output=True)
        time.sleep(0.05)
        subprocess.run(['xdotool', 'key', '--clearmodifiers', 'ctrl+v'],
                       check=True, timeout=5, capture_output=True)
        return True
    except Exception as e:
        print(f"xclip+paste fallback failed: {e}")
        return False


def _type_via_wtype(text):
    """Linux/Wayland fallback: inject text using wtype."""
    if not _check_tool("wtype"):
        return False
    try:
        subprocess.run(['wtype', '--', text],
                       check=True, timeout=10, capture_output=True)
        return True
    except Exception as e:
        print(f"wtype fallback failed: {e}")
        return False


def _type_via_wl_paste(text):
    """Linux/Wayland fallback: copy to clipboard via wl-copy, then simulate Ctrl+V."""
    if not _check_tool("wl-copy") or not _check_tool("wtype"):
        return False
    try:
        subprocess.run(['wl-copy', '--', text],
                       check=True, timeout=5, capture_output=True)
        time.sleep(0.05)
        subprocess.run(['wtype', '-M', 'ctrl', '-P', 'v', '-m', 'ctrl'],
                       check=True, timeout=5, capture_output=True)
        return True
    except Exception as e:
        print(f"wl-copy+paste fallback failed: {e}")
        return False


def _type_via_powershell(text):
    """Windows fallback: inject text via PowerShell SendKeys / Set-Clipboard + Ctrl+V."""
    # First try clipboard + Ctrl+V — more reliable with Unicode
    try:
        # Copy to clipboard
        safe = text.replace("'", "''")
        subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             f"Set-Clipboard -Value '{safe}'"],
            check=True, timeout=5, capture_output=True
        )
        time.sleep(0.05)
        # Simulate Ctrl+V via SendKeys
        subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             'Add-Type -AssemblyName System.Windows.Forms; '
             '[System.Windows.Forms.SendKeys]::SendWait("^v")'],
            check=True, timeout=5, capture_output=True
        )
        return True
    except Exception as e:
        print(f"PowerShell fallback failed: {e}")
        return False


def type_text_crossplatform(text):
    """Try pynput first, then platform-specific fallbacks.

    This function MUST be called on the main thread (required by macOS TSM).
    Returns True if injection succeeded, False otherwise.
    """
    # --- Primary: pynput ---
    try:
        ctrl = keyboard.Controller()
        ctrl.type(text)
        return True
    except Exception as e:
        print(f"pynput typing failed ({e}), trying platform fallback...")

    # --- Fallback chain per platform ---
    if PLATFORM == "darwin":
        if _type_via_applescript(text):
            return True

    elif PLATFORM == "win32":
        if _type_via_powershell(text):
            return True

    elif PLATFORM == "linux":
        if LINUX_DISPLAY_SERVER == "wayland":
            if _type_via_wtype(text):
                return True
            if _type_via_wl_paste(text):
                return True
        else:
            # X11 or unknown — try X11 tools
            if _type_via_xdotool(text):
                return True
            if _type_via_xclip_paste(text):
                return True

    print("ERROR: All text injection methods failed. "
          "Text was transcribed but could not be typed:")
    print(f"  \"{text}\"")
    return False

# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class DictationApp(QObject):
    update_state = Signal(str)
    inject_text = Signal(str)
    show_warning = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.api_key = self.config.get("api_key", "")
        self.recorder = AudioRecorder()
        self.is_processing = False
        
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Tray Icon
        self.tray = QSystemTrayIcon()
        self.icon_idle = create_tray_icon("gray")
        self.icon_recording = create_tray_icon("red")
        self.icon_processing = create_tray_icon("yellow")
        
        self.tray.setIcon(self.icon_idle)
        self.tray.setVisible(True)

        self.menu = QMenu()
        
        # API Key Handling (Standard: Keyring)
        self.api_key = None
        
        # 1. Try environment variable
        self.api_key = os.environ.get("PCSS_API_KEY")
        
        # 2. Try Keyring (shared with main omni_agent)
        if not self.api_key:
            try:
                import keyring
                # Priority: Try to match exactly what omni_agent uses (lowercase)
                self.api_key = keyring.get_password("omni_agent", "api_key")
                if not self.api_key:
                     # Fallback to uppercase just in case legacy or different system
                     self.api_key = keyring.get_password("PCSS_LLM_APP", "api_key")
            except ImportError:
                print("Warning: 'keyring' library not found. Install it for secure key storage.")
        
        # 3. Try legacy plain text (and migrate it out)
        if not self.api_key and "api_key" in self.config:
            self.api_key = self.config["api_key"]
            print("Migrating API Key from dictation_settings.json to memory only.")

        # Cleanup dictation_settings.json to ensure no plain text keys remain
        if "api_key" in self.config:
            del self.config["api_key"]
            save_config(self.config)
            print("Secured dictation_settings.json (removed plain text API key).")
                
        if not self.api_key:
            print("\n" + "!" * 60)
            print("ERROR: No API Key found!")
            print("Please log in via the main PCSS LLM Agent first,")
            print("or set the PCSS_API_KEY environment variable.")
            print("!" * 60 + "\n")
            sys.exit(1)
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.config.get("base_url")
        )
        
        quit_action = QAction("Quit PCSS Dictation")
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)
        self.tray.setContextMenu(self.menu)

        self.update_state.connect(self._on_state_change)
        self.inject_text.connect(self._on_inject_text)
        self.show_warning.connect(self._on_show_warning)
        
        self.hotkey_mgr = HotkeyManager(self.start_recording, self.stop_recording)

    def start_recording(self):
        if self.is_processing:
            return
            
        self.update_state.emit("RECORDING")
        self.recorder.start()

    def stop_recording(self):
        result = self.recorder.stop()
        if result:
            file_path, is_silent = result
            if is_silent:
                # Audio is completely empty (all zeros)
                self.update_state.emit("IDLE")
                self.show_warning.emit(
                    "Brak dźwięku / No Audio",
                    "Zarejestrowany dźwięk jest całkowicie pusty. Prawdopodobnie brakuje uprawnień do Mikrofonu (Microphone permissions) w Ustawieniach Systemowych macOS!"
                )
                if os.path.exists(file_path):
                    os.remove(file_path)
            else:
                self.update_state.emit("PROCESSING")
                threading.Thread(target=self.transcribe_and_type, args=(file_path,), daemon=True).start()
        else:
            self.update_state.emit("IDLE")

    def transcribe_and_type(self, file_path):
        self.is_processing = True
        error_occurred = False
        try:
            with open(file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.config.get("transcription_model", "whisper-large-v3-turbo:0.8b"),
                    file=audio_file
                )
            
            text = transcript.text.strip()
            if text:
                # Emit signal to inject text on the main thread.
                self.inject_text.emit(text)
            else:
                self.show_warning.emit(
                    "Puste nagranie / Empty Transcript",
                    "Transkrypcja nie zwróciła żadnego tekstu. Nagranie było zbyt ciche lub za krótkie."
                )
                
        except Exception as e:
            print(f"Transcription error: {e}")
            error_occurred = True
            self.update_state.emit("ERROR")
        finally:
            self.is_processing = False
            if not error_occurred: # Keep error state if there was an exception
                self.update_state.emit("IDLE")
            if os.path.exists(file_path):
                os.remove(file_path)

    @Slot(str)
    def _on_inject_text(self, text):
        """Inject transcribed text into the active application.
        
        Runs on the main thread to satisfy macOS TSM requirements and to
        ensure consistent behaviour across all platforms.
        """
        # Small delay to ensure the system has returned focus after recording
        time.sleep(0.1)
        success = type_text_crossplatform(text)
        if not success:
            self.show_warning.emit(
                "Błąd wpisywania / Injection Error",
                f"Nie udało się automatycznie wpisać tekstu. Transkrypcja:\n\n{text}"
            )

    @Slot(str, str)
    def _on_show_warning(self, title, message):
        self.tray.showMessage(title, message, QSystemTrayIcon.Warning)

    @Slot(str)
    def _on_state_change(self, state):
        if state == "RECORDING":
            self.tray.setIcon(self.icon_recording)
            self.tray.setToolTip("Recording... (Release Ctrl+Space to finish)")
        elif state == "PROCESSING":
            self.tray.setIcon(self.icon_processing)
            self.tray.setToolTip("Transcribing via PCSS HPC...")
        elif state == "ERROR":
            self.tray.setIcon(self.icon_idle)
            self.tray.showMessage("Dictation Error", "An error occurred during transcription.", QSystemTrayIcon.Critical)
        else:
            self.tray.setIcon(self.icon_idle)
            self.tray.setToolTip("PCSS Dictation - Hold Left Ctrl+Space to dictate")

    def run(self):
        print("PCSS Dictation App is starting...")
        print(f"Platform: {PLATFORM} ({platform.machine()})")
        if PLATFORM == "linux":
            print(f"Display server: {LINUX_DISPLAY_SERVER}")
        
        platform_warnings = check_platform_permissions()
        if platform_warnings:
            for warning in platform_warnings:
                print("\n" + "!" * 60)
                print("WARNING: " + warning)
                print("!" * 60 + "\n")
            
            # Show the first (most critical) warning in the system tray
            first_warning = platform_warnings[0]
            # Truncate for tray notification readability
            short_msg = first_warning.split('\n')[0]
            QTimer.singleShot(1000, lambda: self.tray.showMessage(
                "Platform Warning", 
                short_msg,
                QSystemTrayIcon.Warning
            ))

        print("PCSS Dictation App is running in the system tray.")
        print("Hold Left Ctrl + Space keys to record and dictate.")
        sys.exit(self.app.exec())

if __name__ == "__main__":
    app = DictationApp()
    app.run()
