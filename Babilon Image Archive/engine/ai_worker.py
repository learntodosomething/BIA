from PyQt6.QtCore import QThread, pyqtSignal


class AIWorker(QThread):
    finished  = pyqtSignal(object)   # PIL Image
    error     = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, ai_server, prompt: str, negative_prompt: str,
                 width: int, height: int, steps: int = 2, cfg: float = 0.0):
        super().__init__()
        self.ai_server       = ai_server
        self.prompt          = prompt
        self.negative_prompt = negative_prompt
        self.width           = width
        self.height          = height
        self.steps           = steps
        self.cfg             = cfg
        self._cancelled      = False

    def cancel(self):
        """Leállítja a generálást amint lehetséges."""
        self._cancelled = True

    def run(self):
        if self._cancelled:
            self.cancelled.emit()
            return
        try:
            img = self.ai_server.generate(
                self.prompt, self.width, self.height,
                steps=self.steps, cfg=self.cfg,
            )
            if self._cancelled:
                self.cancelled.emit()
            else:
                self.finished.emit(img)
        except Exception as e:
            if self._cancelled:
                self.cancelled.emit()
            else:
                self.error.emit(str(e))
