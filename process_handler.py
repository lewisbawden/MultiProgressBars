from multiprocessing import Pipe
from PyQt5 import QtCore


class ProcessHandler(QtCore.QThread):
    taskFinished = QtCore.pyqtSignal(object, bool)
    sendResult = QtCore.pyqtSignal(object, object)
    updateName = QtCore.pyqtSignal(int, str)
    updateTotal = QtCore.pyqtSignal(int, float)
    updateValue = QtCore.pyqtSignal(int, float)

    def __init__(self, apply_func, func_args=tuple, func_kwargs=None, pid=None, pbar=None, pool=None):
        super().__init__()
        self.func = apply_func
        self.args = func_args
        self.kwargs = func_kwargs if func_kwargs is not None else dict()

        self.pid = pid
        self.pool = pool
        self.updater = pbar
        self.kwargs['pbar'] = pbar
        self.success = True

        self.pipe, self.target_func_pipe = Pipe()
        self.updater._set_pipe(self.target_func_pipe)
        self.poll_messages_frequency = 0.01
        self.pause_requested = False
        self.paused = False

    def set_pause_requested(self, new_paused_state):
        self.pause_requested = True
        self.paused = new_paused_state

    def run(self):
        try:
            p = self.pool.apply_async(self.func, args=self.args, kwds=self.kwargs)
            self.handle_messages(p)
            out = p.get()
            self.sendResult.emit(self.pid, out)
        except InterruptTask:
            self.success = False
        self.taskFinished.emit(self.pid, self.success)

    def handle_messages(self, p):
        while not p.ready():
            if self.pipe.poll(self.poll_messages_frequency):
                message = self.pipe.recv()
                self.send_signal(message)
            if self.isInterruptionRequested():
                self.pipe.send((Messages.interruption_request, True))
            if self.pause_requested:
                self.pipe.send((Messages.pause_request, self.paused))
                self.pause_requested = False

    def send_signal(self, message):
        field, value = message
        if field == Messages.value:
            self.updateValue.emit(self.pid, value)
        elif field == Messages.name:
            self.updateName.emit(self.pid, value)
        elif field == Messages.total:
            self.updateTotal.emit(self.pid, value)


class Messages:
    name = 'name'
    total = 'total'
    value = 'value'
    interruption_request = 'interruption_request'
    pause_request = 'pause_request'


class InterruptTask(InterruptedError):
    """ Stop executing code within QThread immediately and safely quit """
