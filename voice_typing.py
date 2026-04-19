import sys
import os
import json
import wave
import tempfile
import threading
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

def check_macos_accessibility():
    """Checks if the application has accessibility permissions on macOS"""
    if sys.platform != "darwin":
        return True
    try:
        # This is a bit of a hack but it works for checking TCC permissions
        script = 'tell application "System Events" to get UI elements enabled'
        output = subprocess.check_output(['osascript', '-e', script], stderr=subprocess.DEVNULL)
        return "true" in output.decode('utf-8').lower()
    except Exception:
        return False

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
            return None
        
        recording = np.concatenate(self.frames, axis=0)
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "dictation_chunk.wav")
        sf.write(temp_file, recording, self.samplerate)
        return temp_file

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

class DictationApp(QObject):
    update_state = Signal(str)

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
        
        self.hotkey_mgr = HotkeyManager(self.start_recording, self.stop_recording)

    def start_recording(self):
        if self.is_processing:
            return
            
        self.update_state.emit("RECORDING")
        self.recorder.start()

    def stop_recording(self):
        file_path = self.recorder.stop()
        if file_path:
            self.update_state.emit("PROCESSING")
            threading.Thread(target=self.transcribe_and_type, args=(file_path,), daemon=True).start()
        else:
            self.update_state.emit("IDLE")

    def transcribe_and_type(self, file_path):
        self.is_processing = True
        try:
            with open(file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.config.get("transcription_model", "whisper-large-v3-turbo:0.8b"),
                    file=audio_file
                )
            
            text = transcript.text.strip()
            if text:
                # Small delay to ensure the system has stopped recording and returned focus if needed
                time.sleep(0.1)
                
                keyboard_controller = keyboard.Controller()
                # Inject text natively
                # On macOS, sometimes .type() is too fast for the target app to process.
                # We can try to type character by character if it's unstable, 
                # but let's try standard first with a preceding small sleep.
                keyboard_controller.type(text)
                
                # OPTIONAL: Add a trailing space to make dictation feel more natural
                # keyboard_controller.type(" ")
                
        except Exception as e:
            print(f"Transcription error: {e}")
            self.update_state.emit("ERROR")
        finally:
            self.is_processing = False
            self.update_state.emit("IDLE")
            if os.path.exists(file_path):
                os.remove(file_path)

    @Slot(str)
    def _on_state_change(self, state):
        if state == "RECORDING":
            self.tray.setIcon(self.icon_recording)
            self.tray.setToolTip("Recording... (Release Option+Space to finish)")
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
        
        if not check_macos_accessibility():
            print("\n" + "!" * 60)
            print("WARNING: macOS Accessibility Permissions NOT Detected!")
            print("To allow global hotkeys and text injection, please go to:")
            print("System Settings -> Privacy & Security -> Accessibility")
            print("and enable your Terminal / Python application.")
            print("!" * 60 + "\n")
            
            # Also show a UI warning
            QTimer.singleShot(1000, lambda: self.tray.showMessage(
                "Permissions Required", 
                "Please enable Accessibility permissions for this app in System Settings to allow dictation.",
                QSystemTrayIcon.Warning
            ))

        print("PCSS Dictation App is running in the system tray.")
        print("Hold Left Ctrl + Space keys to record and dictate.")
        sys.exit(self.app.exec())

if __name__ == "__main__":
    app = DictationApp()
    app.run()
