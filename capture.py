"""Frame-grabber för Twitch-strömmar.

Löser upp Twitch-URL:en till en HLS-ström via streamlink och låter ffmpeg
skriva om den senaste bildrutan till en jpg-fil med några sekunders intervall.
Servern läser sedan alltid den senaste sparade bildrutan — ingen videoström
behöver hanteras i Python.

Kräver att `streamlink` och `ffmpeg` finns i PATH.
"""

import os
import shutil
import subprocess
import threading
import time

FRAME_MAX_AGE_S = 30  # äldre bildruta än så räknas som död ström


class FrameGrabber:
    def __init__(self, frame_path: str = "latest_frame.jpg", interval_s: int = 3):
        self.frame_path = frame_path
        self.interval_s = interval_s
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.stream_url: str | None = None
        self.error: str | None = None

    @staticmethod
    def dependencies_ok() -> list[str]:
        """Returnerar en lista med saknade beroenden (tom = allt ok)."""
        missing = []
        if shutil.which("streamlink") is None:
            missing.append("streamlink")
        if shutil.which("ffmpeg") is None:
            missing.append("ffmpeg")
        return missing

    def start(self, twitch_url: str) -> None:
        with self._lock:
            self._stop_locked()
            self.error = None
            self.stream_url = twitch_url

            try:
                hls_url = subprocess.check_output(
                    ["streamlink", "--stream-url", twitch_url, "720p,720p60,best"],
                    text=True,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                ).strip()
            except subprocess.CalledProcessError as e:
                self.error = f"streamlink kunde inte öppna strömmen: {e.output.strip()[:300]}"
                raise RuntimeError(self.error)
            except subprocess.TimeoutExpired:
                self.error = "streamlink svarade inte inom 30 sekunder"
                raise RuntimeError(self.error)

            self._proc = subprocess.Popen(
                [
                    "ffmpeg",
                    "-loglevel", "error",
                    "-i", hls_url,
                    "-vf", f"fps=1/{self.interval_s}",
                    "-update", "1",
                    "-q:v", "3",
                    "-y", self.frame_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()
            self.stream_url = None

    def _stop_locked(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def frame_age_s(self) -> float | None:
        try:
            return time.time() - os.path.getmtime(self.frame_path)
        except OSError:
            return None

    def latest_frame(self) -> bytes | None:
        """Senaste bildrutan som jpg-bytes, eller None om ingen färsk finns."""
        age = self.frame_age_s()
        if age is None or age > FRAME_MAX_AGE_S:
            return None
        try:
            with open(self.frame_path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def status(self) -> dict:
        return {
            "running": self.is_running(),
            "stream_url": self.stream_url,
            "frame_age_s": self.frame_age_s(),
            "error": self.error,
        }
