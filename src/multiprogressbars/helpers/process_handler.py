from sys import exc_info, stderr
from traceback import format_exception
from multiprocessing import Pipe
from PyQt5 import QtCore


class ProcessHandler(QtCore.QThread):
    """
    Handles executing the task as a process in the multiprocessing.Pool.
    Communicates about progress and interruptions between ProcessHandler and process through localhost.
    Communicates progress with the main GUI thread through pyqtSignals.
    """
    taskFinishedSignal = QtCore.pyqtSignal(object, int)
    sendResultSignal = QtCore.pyqtSignal(object, object)
    updateNameSignal = QtCore.pyqtSignal(int, str)
    updateTotalSignal = QtCore.pyqtSignal(int, float)
    updateValueSignal = QtCore.pyqtSignal(int, float)

    SUCESSFUL = 0
    CANCELLED = 1
    EXCEPTION_RAISED = 2

    def __init__(self, apply_func, func_args=tuple, func_kwargs=None, pid=None, pbar=None, pool=None):
        super().__init__()
        self.func = apply_func
        self.args = func_args
        self.kwargs = func_kwargs if func_kwargs is not None else dict()

        self.pid = pid
        self.pool = pool
        self.updater = pbar
        self.kwargs['pbar'] = pbar
        self.success = False

        self.pipe, self.target_func_pipe = Pipe()
        self.updater._set_pipe(self.target_func_pipe)
        self.poll_messages_frequency = 0.01
        self.pause_requested = False
        self.paused = False
        self.closed = False

    def __del__(self):
        if not self.closed:
            self.close()

    def close(self):
        self.target_func_pipe.close()
        self.pipe.close()
        self.wait(100)
        self.quit()
        self.closed = True

    def set_pause_requested(self, new_paused_state):
        self.pause_requested = True
        self.paused = new_paused_state

    def run(self):
        try:
            p = self.pool.apply_async(self.func, args=self.args, kwds=self.kwargs)
            self.handle_messages(p)
            out = p.get()
            self.sendResultSignal.emit(self.pid, out)
            self.taskFinishedSignal.emit(self.pid, self.SUCESSFUL)
        except InterruptTask:
            self.taskFinishedSignal.emit(self.pid, self.CANCELLED)
        except:
            self.taskFinishedSignal.emit(self.pid, self.EXCEPTION_RAISED)
            ex = exc_info()
            print(f'----- EXCEPTION RAISED BY TASK: {self.pid} -----', file=stderr)
            [print(arg.replace('\n\n', '\n'), file=stderr) for arg in format_exception(*ex)]
            print(f'----- End traceback for task: {self.pid} -----\n', file=stderr)

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
            self.updateValueSignal.emit(self.pid, value)
        elif field == Messages.name:
            self.updateNameSignal.emit(self.pid, value)
        elif field == Messages.total:
            self.updateTotalSignal.emit(self.pid, value)


class Messages:
    name = 'name'
    total = 'total'
    value = 'value'
    interruption_request = 'interruption_request'
    pause_request = 'pause_request'


class InterruptTask(InterruptedError):
    """ Stop executing code within QThread immediately and safely quit """
