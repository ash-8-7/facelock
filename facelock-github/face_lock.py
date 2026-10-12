"""
face_lock.py - Face recognition lock screen for Windows.

Modes:
    python face_lock.py register   -> Capture face samples and train the model
    python face_lock.py test       -> Run lock screen (for testing)
    python face_lock.py            -> Run lock screen
"""

import cv2
import numpy as np
import os
import sys
import time
import ctypes
import tkinter as tk
import keyboard
from PIL import Image, ImageTk


# ---------------- Configuration ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "face_data")
TRAINER_FILE = os.path.join(DATA_DIR, "trainer.yml")
INSTANCE_MUTEX = None

CONFIDENCE_THRESHOLD = 70       # lower = stricter match
CAMERA_TIMEOUT = 50             # seconds camera stays on
SAMPLES_PER_POSE = 75           # samples per pose
TOTAL_POSES = 6                 # number of poses
HOTKEY_FORCE_QUIT = "ctrl+shift+q"
ATTEMPTS_DIR = os.path.join(BASE_DIR, "login_attempts")

# ---------------- Helpers ----------------
def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def acquire_single_instance():
    """Prevent the logon launcher and unlock task from opening duplicates."""
    global INSTANCE_MUTEX
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, "Local\\FaceLockApp")
    if not INSTANCE_MUTEX:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(INSTANCE_MUTEX)
        INSTANCE_MUTEX = None
        return False
    return True

def log_login_attempt(frame):
    """Save a snapshot of the first frame each time the lock starts."""
    if not os.path.exists(ATTEMPTS_DIR):
        os.makedirs(ATTEMPTS_DIR)

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(ATTEMPTS_DIR, f"attempt_{timestamp}.jpg")
    cv2.imwrite(path, frame)
    print(f"[log] login attempt saved: {path}")

def lock_screen():
    """Lock the Windows workstation."""
    try:
        ctypes.windll.user32.LockWorkStation()
    except Exception as e:
        print(f"[warn] could not lock screen: {e}")


# ---------------- Register Face ----------------
def capture_faces():
    ensure_data_dir()

    # Clear old data
    for f in os.listdir(DATA_DIR):
        if f.startswith("user.") or f == "trainer.yml":
            try:
                os.remove(os.path.join(DATA_DIR, f))
            except Exception:
                pass
    print("Old face data cleared.")

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("[error] cannot open camera.")
        return False

    poses = [
        "Look straight at the camera",
        "Turn your head slightly LEFT",
        "Turn your head slightly RIGHT",
        "Tilt your head slightly UP",
        "Tilt your head slightly DOWN",
        "Move a bit CLOSER to the camera",
    ]

    sample_id = 0

    for pose_index, pose_text in enumerate(poses):
        print(f"\nPose {pose_index + 1}/{TOTAL_POSES}: {pose_text}")
        print("SPACE = start, Q = abort")

        # Wait for SPACE
        while True:
            ret, frame = cam.read()
            if not ret:
                cam.release()
                cv2.destroyAllWindows()
                return False

            cv2.putText(frame, f"Pose {pose_index + 1}/{TOTAL_POSES}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, pose_text,
                        (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "SPACE = start   Q = abort",
                        (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow("Register Face", frame)

            k = cv2.waitKey(1) & 0xFF
            if k == ord(' '):
                break
            if k == ord('q'):
                cam.release()
                cv2.destroyAllWindows()
                return False

        # Capture samples for this pose
        count = 0
        while count < SAMPLES_PER_POSE:
            ret, frame = cam.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)

            for (x, y, w, h) in faces:
                x, y, w, h = int(x), int(y), int(w), int(h)
                sample_id += 1
                count += 1

                face_img = gray[y:y + h, x:x + w]
                cv2.imwrite(
                    os.path.join(DATA_DIR, f"user.{sample_id}.jpg"),
                    face_img,
                )

                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, f"{count}/{SAMPLES_PER_POSE}",
                            (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (0, 255, 0), 2)

                if count >= SAMPLES_PER_POSE:
                    break

            cv2.imshow("Register Face", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        print(f"Pose {pose_index + 1} done: {count} samples.")

    cam.release()
    cv2.destroyAllWindows()
    print(f"\nTotal samples saved: {sample_id}")
    return True


def train_model():
    print("\nTraining...")

    files = [f for f in os.listdir(DATA_DIR)
             if f.startswith("user.") and f.endswith(".jpg")]

    if not files:
        print("[error] no samples found.")
        return False

    faces, ids = [], []

    for fn in files:
        try:
            uid = int(fn.split(".")[1])
        except (IndexError, ValueError):
            continue

        img = cv2.imread(os.path.join(DATA_DIR, fn), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue

        faces.append(img)
        ids.append(uid)

    if not faces:
        print("[error] no valid images.")
        return False

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(faces, np.array(ids))
    recognizer.save(TRAINER_FILE)

    print(f"Model saved: {TRAINER_FILE}")
    return True


# ---------------- Lock Screen ----------------
class FaceLockApp:
    def __init__(self, root):
        self.root = root
        self.cap = None
        self.video_item = None
        self.photo = None
        self.start_time = time.time()
        self.should_quit = False
        self.finished = False
        self.exit_action = None   # "close" | "lock" | "force"
        self._snapshot_saved = False

        # Load recognizer and detector
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.recognizer.read(TRAINER_FILE)

        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        # Window setup
        self.root.title("Face Lock")
        self.root.configure(bg="black")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_attempt)

        self.canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Camera
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("[error] cannot open camera. Locking laptop.")
            self.finish_and_lock()
            return

        # Hidden hotkey
        try:
            keyboard.add_hotkey(HOTKEY_FORCE_QUIT, self._hotkey_callback)
        except Exception as e:
            print(f"[warn] hotkey not registered: {e}")

        # Start frame loop
        self.root.after(100, self.update_frame)

    # ----- Exit paths -----
    def _hotkey_callback(self):
        # Runs on keyboard thread - just set a flag
        self.should_quit = True

    def on_close_attempt(self):
        # Alt+F4 or X button -> lock the laptop
        print("Close attempt detected. Locking laptop.")
        self._begin_shutdown("lock")

    def finish_and_close(self):
        # Face recognized -> close the app
        print("Owner recognized. Closing lock.")
        self._begin_shutdown("close")

    def finish_and_lock(self):
        # Timeout / failure -> lock the laptop
        print("Owner NOT recognized. Locking laptop.")
        self._begin_shutdown("lock")

    def _begin_shutdown(self, action):
        if self.finished:
            return
        self.finished = True
        self.exit_action = action
        self.cleanup()
        try:
            self.root.quit()
        except Exception:
            pass

    def cleanup(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        try:
            keyboard.remove_all_hotkeys()
        except Exception:
            pass

    # ----- Main loop -----
    def update_frame(self):
        try:
            self._update_frame()
        except Exception as e:
            print(f"[error] frame processing failed: {e}")
            self.finish_and_lock()

    def _update_frame(self):
        if self.finished:
            return

        if self.should_quit:
            print("Face lock closed by emergency hotkey.")
            self._begin_shutdown("force")
            return

        elapsed = time.time() - self.start_time
        remaining = CAMERA_TIMEOUT - elapsed

        if remaining <= 0:
            self.finish_and_lock()
            return

        ret, frame = self.cap.read()
        if ret:
            # Save first frame as a login-attempt snapshot (once per run)
            if not self._snapshot_saved:
                log_login_attempt(frame)
                self._snapshot_saved = True

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)

            for (x, y, w, h) in faces:
                x, y, w, h = int(x), int(y), int(w), int(h)

                face_img = gray[y:y + h, x:x + w]
                label, confidence = self.recognizer.predict(face_img)
                is_owner = confidence < CONFIDENCE_THRESHOLD

                color = (0, 255, 0) if is_owner else (0, 0, 255)
                text = f"{'OWNER' if is_owner else 'UNKNOWN'} ({confidence:.0f})"

                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(frame, text, (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                if is_owner:
                    self.finish_and_close()
                    return

            # Countdown + instruction
            cv2.putText(frame, f"Time left: {int(remaining)}s", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            cv2.putText(frame, "Look at the camera", (20, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # Show frame in fullscreen
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            img = img.resize((sw, sh), Image.Resampling.BILINEAR)
            self.photo = ImageTk.PhotoImage(img)

            if self.video_item is None:
                self.video_item = self.canvas.create_image(
                    0, 0, anchor=tk.NW, image=self.photo
                )
            else:
                self.canvas.itemconfig(self.video_item, image=self.photo)

        if not self.finished:
            self.root.after(30, self.update_frame)


def run_lock_screen():
    if not os.path.exists(TRAINER_FILE):
        print("[error] no trained model. Run 'python face_lock.py register' first.")
        lock_screen()
        return

    root = tk.Tk()
    try:
        app = FaceLockApp(root)
    except Exception as e:
        print(f"[error] could not initialize face lock: {e}")
        try:
            root.destroy()
        except Exception:
            pass
        lock_screen()
        return

    try:
        root.mainloop()
    except Exception as e:
        print(f"[error] mainloop: {e}")
        lock_screen()
        return

    # After mainloop exits, apply the requested action
    if app.exit_action == "lock":
        lock_screen()


# ---------------- Main ----------------
def main():
    args = [a.lower() for a in sys.argv[1:]]

    if "register" in args:
        print("=== Register Face Mode ===")
        if capture_faces():
            train_model()
            print("\nDone. Run without arguments to activate the lock.")
        return

    try:
        if not acquire_single_instance():
            print("Face Lock is already running; skipping duplicate launch.")
            return
    except Exception as e:
        print(f"[error] could not create single-instance guard: {e}")
        return

    ensure_data_dir()

    # Force mode (for testing) uses the same lock-screen flow.
    if "test" in args or "force" in args:
        run_lock_screen()
        return

    run_lock_screen()


if __name__ == "__main__":
    main()
