import importlib

import cv2
import numpy as np
import win32gui, win32ui, win32con, win32api
import os
import sys
import ctypes
import tkinter as tk
from tkinter import messagebox


def check_dependencies():
    required_packages = {
        'cv2': 'opencv-python',
        'numpy': 'numpy',
        'PIL': 'Pillow',
        'keyboard': 'keyboard',
        'win32gui': 'pywin32',
        'pynput': 'pynput',
        'requests': 'requests',
        'autoit': 'pyautoit'
    }
    missing_packages = []
    for module, package in required_packages.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print("Missing required packages:")
        for package in missing_packages:
            print(f"  pip install {package}")
        print("\nPlease install the missing packages and try again.")
        sys.exit(1)

def check_display_scale():
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()

        hdc = user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        user32.ReleaseDC(0, hdc)

        scale_percent = (dpi * 100) // 96

        if scale_percent != 100:
            root = tk.Tk()
            root.withdraw()

            messagebox.showerror(
                "Display Scale Error",
                f"ERROR: Display scale is set to {scale_percent}%. This tool requires 100% display scaling to work correctly."
            )

            root.destroy()
            sys.exit(1)

    except Exception:
        pass


def send_click():
    try:
        user32 = ctypes.windll.user32

        INPUT_MOUSE = 0
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long),
                        ("dy", ctypes.c_long),
                        ("mouseData", ctypes.wintypes.DWORD),
                        ("dwFlags", ctypes.wintypes.DWORD),
                        ("time", ctypes.wintypes.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG))]

        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("mi", MOUSEINPUT)]

            _anonymous_ = ("_input",)
            _fields_ = [("type", ctypes.wintypes.DWORD),
                        ("_input", _INPUT)]

        input_down = INPUT()
        input_down.type = INPUT_MOUSE
        input_down.mi.dx = 0
        input_down.mi.dy = 0
        input_down.mi.mouseData = 0
        input_down.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
        input_down.mi.time = 0
        input_down.mi.dwExtraInfo = None

        input_up = INPUT()
        input_up.type = INPUT_MOUSE
        input_up.mi.dx = 0
        input_up.mi.dy = 0
        input_up.mi.mouseData = 0
        input_up.mi.dwFlags = MOUSEEVENTF_LEFTUP
        input_up.mi.time = 0
        input_up.mi.dwExtraInfo = None

        inputs = (INPUT * 2)(input_down, input_up)
        user32.SendInput(2, inputs, ctypes.sizeof(INPUT))

    except Exception as e:
        try:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        except Exception as e2:
            print(f"Click failed: {e}, {e2}")


class ScreenCapture:
    def __init__(self):
        self.hwnd = win32gui.GetDesktopWindow()
        self.hwindc = None
        self.srcdc = None
        self.memdc = None
        self.bmp = None
        self._initialized = False
        self._last_bbox = None
        self._last_width = 0
        self._last_height = 0

    def _initialize_dc(self, width, height):
        try:
            self.hwindc = win32gui.GetWindowDC(self.hwnd)
            self.srcdc = win32ui.CreateDCFromHandle(self.hwindc)
            self.memdc = self.srcdc.CreateCompatibleDC()
            self.bmp = win32ui.CreateBitmap()
            self.bmp.CreateCompatibleBitmap(self.srcdc, width, height)
            self.memdc.SelectObject(self.bmp)
            self._initialized = True
            self._last_width = width
            self._last_height = height
        except Exception:
            self._cleanup()
            return False
        return True

    def _cleanup(self):
        try:
            if self.srcdc: self.srcdc.DeleteDC()
            if self.memdc: self.memdc.DeleteDC()
            if self.hwindc: win32gui.ReleaseDC(self.hwnd, self.hwindc)
            if self.bmp: win32gui.DeleteObject(self.bmp.GetHandle())
        except Exception:
            pass
        self._initialized = False

    def capture(self, bbox=None):
        if not bbox: return None
        left, top, right, bottom = bbox
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0: return None

        if (self._last_bbox != bbox or not self._initialized or
                width != self._last_width or height != self._last_height):
            self._cleanup()
            self._last_bbox = bbox

        if not self._initialized:
            if not self._initialize_dc(width, height): return None

        try:
            self.memdc.BitBlt((0, 0), (width, height), self.srcdc, (left, top), win32con.SRCCOPY)
            signedIntsArray = self.bmp.GetBitmapBits(True)
            img = np.frombuffer(signedIntsArray, dtype='uint8').reshape((height, width, 4))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception:
            self._cleanup()
            return None

    def close(self):
        self._cleanup()


def get_window_list():
    windows = []

    def enum_windows_callback(hwnd, windows_list):
        if win32gui.IsWindowVisible(hwnd):
            window_text = win32gui.GetWindowText(hwnd)
            if window_text:
                rect = win32gui.GetWindowRect(hwnd)
                windows_list.append({
                    'hwnd': hwnd,
                    'title': window_text,
                    'rect': rect,
                    'width': rect[2] - rect[0],
                    'height': rect[3] - rect[1]
                })
        return True

    win32gui.EnumWindows(enum_windows_callback, windows)
    return windows


def focus_window(hwnd):
    try:
        win32gui.SetForegroundWindow(hwnd)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        return True
    except Exception as e:
        print(f"Failed to focus window: {e}")
        return False


def get_window_info(hwnd):
    try:
        title = win32gui.GetWindowText(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        is_visible = win32gui.IsWindowVisible(hwnd)

        return {
            'hwnd': hwnd,
            'title': title,
            'class_name': class_name,
            'rect': rect,
            'width': rect[2] - rect[0],
            'height': rect[3] - rect[1],
            'visible': is_visible
        }
    except Exception as e:
        print(f"Failed to get window info: {e}")
        return None


def find_window_by_title(title_pattern, exact_match=False):
    windows = get_window_list()

    for window in windows:
        if exact_match:
            if window['title'] == title_pattern:
                return window
        else:
            if title_pattern.lower() in window['title'].lower():
                return window

    return None


def capture_window(hwnd):
    try:
        rect = win32gui.GetWindowRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]

        hwindc = win32gui.GetWindowDC(hwnd)
        srcdc = win32ui.CreateDCFromHandle(hwindc)
        memdc = srcdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(srcdc, width, height)
        memdc.SelectObject(bmp)

        memdc.BitBlt((0, 0), (width, height), srcdc, (0, 0), win32con.SRCCOPY)

        signedIntsArray = bmp.GetBitmapBits(True)
        img = np.frombuffer(signedIntsArray, dtype='uint8').reshape((height, width, 4))
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        srcdc.DeleteDC()
        memdc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwindc)
        win32gui.DeleteObject(bmp.GetHandle())

        return img

    except Exception as e:
        print(f"Window capture failed: {e}")
        return None


def get_screen_resolution():
    try:
        user32 = ctypes.windll.user32
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        return width, height
    except Exception:
        return 1920, 1080


def is_point_in_rect(point, rect):
    x, y = point
    left, top, right, bottom = rect
    return left <= x <= right and top <= y <= bottom


def rect_intersection(rect1, rect2):
    left = max(rect1[0], rect2[0])
    top = max(rect1[1], rect2[1])
    right = min(rect1[2], rect2[2])
    bottom = min(rect1[3], rect2[3])

    if left < right and top < bottom:
        return (left, top, right, bottom)
    return None


def normalize_rect(rect):
    x1, y1, x2, y2 = rect
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def expand_rect(rect, padding):
    left, top, right, bottom = rect
    return (left - padding, top - padding, right + padding, bottom + padding)


def clamp_rect_to_screen(rect):
    screen_width, screen_height = get_screen_resolution()
    left, top, right, bottom = rect

    left = max(0, left)
    top = max(0, top)
    right = min(screen_width, right)
    bottom = min(screen_height, bottom)

    return (left, top, right, bottom)


def save_image(image, filepath, quality=95):
    try:
        if filepath.lower().endswith('.jpg') or filepath.lower().endswith('.jpeg'):
            cv2.imwrite(filepath, image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        else:
            cv2.imwrite(filepath, image)
        return True
    except Exception as e:
        print(f"Failed to save image: {e}")
        return False


def load_image(filepath):
    try:
        return cv2.imread(filepath)
    except Exception as e:
        print(f"Failed to load image: {e}")
        return None


def resize_image(image, target_size, maintain_aspect=True):
    try:
        if maintain_aspect:
            h, w = image.shape[:2]
            target_w, target_h = target_size

            scale = min(target_w / w, target_h / h)
            new_w = int(w * scale)
            new_h = int(h * scale)

            resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

            if new_w != target_w or new_h != target_h:
                canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
                y_offset = (target_h - new_h) // 2
                x_offset = (target_w - new_w) // 2
                canvas[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized
                return canvas
            else:
                return resized
        else:
            return cv2.resize(image, target_size, interpolation=cv2.INTER_AREA)

    except Exception as e:
        print(f"Failed to resize image: {e}")
        return image


def create_directory(path):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        print(f"Failed to create directory {path}: {e}")
        return False


def get_file_timestamp():
    import time
    return int(time.time())


def format_timestamp(timestamp=None):
    import time
    if timestamp is None:
        timestamp = time.time()
    return time.strftime('%Y%m%d_%H%M%S', time.localtime(timestamp))


def cleanup_old_files(directory, pattern, max_age_days=7):
    import glob
    import time

    try:
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        files = glob.glob(os.path.join(directory, pattern))

        deleted_count = 0
        for file_path in files:
            try:
                if os.path.getmtime(file_path) < cutoff_time:
                    os.remove(file_path)
                    deleted_count += 1
            except Exception:
                continue

        return deleted_count
    except Exception as e:
        print(f"Cleanup failed: {e}")
        return 0


def get_system_info():
    try:
        import platform
        import psutil

        info = {
            'os': platform.system(),
            'os_version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'cpu_count': psutil.cpu_count(),
            'memory_total': psutil.virtual_memory().total,
            'memory_available': psutil.virtual_memory().available,
            'screen_resolution': get_screen_resolution()
        }
        return info
    except Exception as e:
        print(f"Failed to get system info: {e}")
        return {}


def log_performance(func):
    import time
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000

        if execution_time > 16.67:
            print(f"Performance warning: {func.__name__} took {execution_time:.2f}ms")

        return result

    return wrapper


class PerformanceMonitor:
    def __init__(self, window_size=100):
        self.window_size = window_size
        self.frame_times = []
        self.last_time = None

    def tick(self):
        import time
        current_time = time.perf_counter()

        if self.last_time is not None:
            frame_time = current_time - self.last_time
            self.frame_times.append(frame_time)

            if len(self.frame_times) > self.window_size:
                self.frame_times.pop(0)

        self.last_time = current_time

    def get_fps(self):
        if not self.frame_times:
            return 0

        avg_frame_time = sum(self.frame_times) / len(self.frame_times)
        return 1.0 / avg_frame_time if avg_frame_time > 0 else 0

    def get_frame_time_ms(self):
        if not self.frame_times:
            return 0

        avg_frame_time = sum(self.frame_times) / len(self.frame_times)
        return avg_frame_time * 1000