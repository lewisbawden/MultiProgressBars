import os
import time
from datetime import timedelta
from copy import copy
import random
import PyQt5.Qt as qt
from tqdm import tqdm
import multiprocessing as mp


def wrapped_timer(func):
    def wrapper(*args, **kwargs):
        t0 = time.time()
        print(f"Enter: {func.__name__}")
        out = func(*args, **kwargs)
        print(f"Duration {func.__name__}: {time.time() - t0}")
        return out
    return wrapper


def handle_mutex_and_catch_runtime(func):
    def wrapper(inst, *args, **kwargs):
        locker = qt.QMutexLocker(inst.mutex)
        try:
            return func(inst, *args, **kwargs)
        except RuntimeError:
            return None
    return wrapper


class InterruptTask(InterruptedError):
    """ Stop executing code within QThread immediately and safely quit """


class Messages:
    name = 'name'
    total = 'total'
    value = 'value'
    interruption_request = 'interruption_request'


class ProcessHandler(qt.QThread):
    taskFinished = qt.pyqtSignal(object, bool)
    sendResult = qt.pyqtSignal(object, object)
    updateName = qt.pyqtSignal(int, str)
    updateTotal = qt.pyqtSignal(int, float)
    updateValue = qt.pyqtSignal(int, float)

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

        self.worker_pipe, self.target_func_pipe = mp.Pipe()
        self.updater._set_pipe(self.target_func_pipe)
        self.poll_messages_frequency = 0.01

    def run(self):
        try:
            if self.pool is not None:
                p = self.pool.apply_async(self.func, args=self.args, kwds=self.kwargs)
                self.handle_messages(p)
                out = p.get()
            else:
                out = self.func(*self.args, **self.kwargs)
            self.sendResult.emit(self.pid, out)
        except InterruptTask:
            self.success = False
        self.taskFinished.emit(self.pid, self.success)

    def handle_messages(self, p):
        while not p.ready():
            if self.worker_pipe.poll(self.poll_messages_frequency):
                message = self.worker_pipe.recv()
                self.send_signal(message)
            if self.isInterruptionRequested():
                self.worker_pipe.send((Messages.interruption_request, True))

    def send_signal(self, message):
        field, value = message
        if field == Messages.value:
            self.updateValue.emit(self.pid, value)
        elif field == Messages.name:
            self.updateName.emit(self.pid, value)
        elif field == Messages.total:
            self.updateTotal.emit(self.pid, value)


class LabeledProgressBar(qt.QProgressBar):
    cancelTaskSignal = qt.pyqtSignal(int)
    unit_conv = {3: 'k', 6: 'M', 9: 'G', 12: 'T'}

    def __init__(self, total=100, name=" ", units_symbol="", max_update_freq=0.02, pid=None, parent=None):
        super(LabeledProgressBar, self).__init__(parent)
        self.total = total
        self.units_symbol = units_symbol
        self.pid = pid
        self.task_name = f"{name}"
        self.full_name = self.get_full_name(self.task_name)

        self.min_update_increment = total // 500
        self.max_update_frequency = max_update_freq

        self.last_updated = self.get_time()
        self.recent_iteration_speeds = []
        self.elapsed_time = 0
        self.remaining_time = 0

        self.total_str = self.get_formatted_number(total, self.units_symbol)
        self.progress_str = self.get_progress_str(0)
        self.frequency_str = self.get_frequency_str()
        self.elapsed_time_str = self.get_elapsed_time_str()
        self.remaining_time_str = self.get_remaining_time_str()

        self.prefix_label = qt.QLabel(self.full_name)
        self.progress_label = qt.QLabel(self.progress_str)
        self.frequency_label = qt.QLabel(self.frequency_str)
        self.elapsed_time_label = qt.QLabel(self.elapsed_time_str)
        self.remaining_time_label = qt.QLabel(self.remaining_time_str)

        self.prefix_label.setEnabled(False)
        self.progress_label.setEnabled(False)
        self.frequency_label.setEnabled(False)
        self.elapsed_time_label.setEnabled(False)
        self.remaining_time_label.setEnabled(False)

        self.setMinimumSize(200, 20)
        self.setRange(0, total)
        self.setMouseTracking(False)
        self.setTextVisible(False)

        self.show()

    def send_cancel_task_signal(self):
        self.cancelTaskSignal.emit(self.pid)

    def set_color_cancelled(self):
        self.setStyleSheet("""QProgressBar::chunk{background-color : #AAAAAA;}""")

    def set_max_update_frequency(self, value):
        self.max_update_frequency = value

    def mousePressEvent(self, a0: qt.QMouseEvent):
        if a0.button() == qt.Qt.RightButton:
            menu = qt.QMenu()
            cancel_task_act = menu.addAction('Cancel task')
            cancel_task_act.triggered.connect(self.send_cancel_task_signal)
            pos = a0.globalPos()
            menu.exec(pos)

    @classmethod
    def get_formatted_number(cls, value, symbol):
        factor, unit_prefix = cls.get_units_prefix(value)
        if factor == 0:
            fmt_value = f' {value}'
        else:
            fmt_value = '{:.2f}'.format(round(value / (10 ** factor), 2))
        return "  {} {}{}".format(fmt_value, unit_prefix, symbol)

    @classmethod
    def get_units_prefix(cls, num):
        # uses base10 location of digits to get units prefix, i.e. not equivlant to byte conversion if units are bytes
        digits = len(str(int(num))) - 2
        factor = 3 * round(digits / 3)
        if factor not in cls.unit_conv.keys():
            if factor > 2:
                factor = max(cls.unit_conv.keys())
            else:
                return 0, ''
        return factor, cls.unit_conv[factor]

    def get_progress_str(self, value):
        value_str = self.get_formatted_number(value, self.units_symbol)
        out = ' / '.join([value_str, self.total_str])
        return f'  {out}'

    def get_frequency_str(self):
        its_suffix = 'it/s'
        self.mean_speed = 1

        if len(self.recent_iteration_speeds) == 0:
            return f'  {its_suffix}'

        self.recent_iteration_speeds = self.recent_iteration_speeds[-10:]
        self.mean_speed = round(sum(self.recent_iteration_speeds) / len(self.recent_iteration_speeds), 1)
        return f'  {self.mean_speed} {its_suffix}'

    def get_elapsed_time_str(self):
        return f'  {timedelta(seconds=round(self.elapsed_time))}'

    def get_remaining_time_str(self):
        its_remaining = self.total - self.value()
        if self.mean_speed == 0:
            self.remaining_time = 0
        else:
            self.remaining_time = its_remaining / self.mean_speed
        return f'  {timedelta(seconds=round(self.remaining_time))}'

    @staticmethod
    def get_time():
        return time.time()

    def allowed_to_set_value(self, value):
        freq_cond = self.get_time() - self.last_updated >= self.max_update_frequency
        value_cond = value - self.value() >= self.min_update_increment
        return freq_cond and value_cond

    def set_value(self, value):
        value_difference = value - self.value()
        self.setValue(value)

        update_time = self.get_time()
        time_difference = update_time - self.last_updated
        self.last_updated = update_time
        self.elapsed_time += time_difference

        if time_difference > 0:
            self.recent_iteration_speeds.append(value_difference / time_difference)

        self.frequency_str = self.get_frequency_str()
        self.frequency_label.setText(self.frequency_str)

        self.elapsed_time_str = self.get_elapsed_time_str()
        self.elapsed_time_label.setText(self.elapsed_time_str)

        self.remaining_time_str = self.get_remaining_time_str()
        self.remaining_time_label.setText(self.remaining_time_str)

        self.progress_str = self.get_progress_str(value)
        self.progress_label.setText(self.progress_str)

    def get_full_name(self, name):
        if self.pid is None:
            return name
        else:
            return f"Task {self.pid}: {name}"

    def set_name(self, name):
        self.task_name = name
        self.full_name = self.get_full_name(name)
        self.prefix_label.setText(self.full_name)

    def set_total(self, total):
        self.total = total
        progress = self.value()
        self.setRange(progress, self.total)
        self.total_str = self.get_formatted_number(total, self.units_symbol)
        self.progress_str = self.get_progress_str(progress)
        self.progress_label.setText(self.progress_str)


class ZoomingScrollArea(qt.QScrollArea):
    adjustFontSignal = qt.pyqtSignal(object)

    def __init__(self, fontname=None, fontsize=None):
        super().__init__()
        font = qt.QFont()
        if fontname is None:
            fontname = font.defaultFamily()
        if fontsize is None:
            fontsize = font.pointSize()

        self.fontname = fontname
        self.fontsize = fontsize

        self.adjust_font(1)
        self.adjustFontSignal.connect(self.adjust_font)

    def wheelEvent(self, a0: qt.QWheelEvent):
        mods = a0.modifiers()
        if mods == qt.Qt.KeyboardModifier.ControlModifier:
            delta = a0.angleDelta()
            incr = delta.y() // abs(delta.y())
            self.adjustFontSignal.emit(incr)
        else:
            super().wheelEvent(a0)

    def adjust_font(self, incr):
        if incr < 0:
            self.fontsize = max(1, self.fontsize + incr)
        else:
            self.fontsize = min(100, self.fontsize + incr)
        self.setFont(qt.QFont(self.fontname, self.fontsize))


class Multibar(qt.QObject):
    allProcessesFinished = qt.pyqtSignal()
    setNameSignal = qt.pyqtSignal(int, object)
    setTotalSignal = qt.pyqtSignal(int, float)
    setValueSignal = qt.pyqtSignal(int, float)

    def __init__(self, title=None, batch_size=None):
        super(Multibar, self).__init__()
        self.title = title
        self.batch_size = os.cpu_count() if batch_size is None else batch_size
        self.max_bar_update_frequency = 0.02

        self.app = qt.QApplication([])

        self.pbars = dict()
        self.tasks = dict()
        self.running_tasks = dict()
        self.results = dict()

        self.mutex = qt.QMutex()
        self.pool = mp.Pool(self.batch_size)

        self.setup_window(title)

    def __del__(self):
        if len(self.running_tasks) > 0:
            running_pids = list(self.running_tasks.keys())
            for pid in running_pids:
                self.end_task(pid)
        if self.pool is not None:
            self.pool.close()
            self.pool.terminate()
        self.allProcessesFinished.emit()

    def setup_window(self, title):
        self.layout = qt.QGridLayout()
        self.widget = qt.QWidget()
        self.widget.setLayout(self.layout)

        # window is a QScrollArea widget
        self.scroll_area = ZoomingScrollArea()
        self.scroll_area.setWindowTitle(title)
        self.scroll_area.setWidget(self.widget)
        self.scroll_area.setWidgetResizable(True)

        # force it to open as 1/3 width and height the screen, placed in the bottom right corner
        screen_size = qt.QDesktopWidget().screenGeometry(-1)
        screen_w, screen_h = screen_size.width(), screen_size.height()
        panel_w, panel_h = screen_w // 3, screen_h // 3
        panel_posx, panel_posy = screen_w - 1.05 * panel_w, (0.95 * screen_h) - 1.1 * panel_h
        self.scroll_area.resize(panel_w, panel_h)
        self.scroll_area.move(panel_posx, panel_posy)

        self.scroll_area.setFocus()
        self.scroll_area.show()

    def scroll_down(self):
        if len(self.running_tasks) > 0:
            bottom = min(max(self.running_tasks) + 1, len(self.pbars) - 1)
            self.scroll_area.ensureWidgetVisible(self.pbars[bottom].progress_label, 10, 10)

    def add_task(self, func=callable, func_args=tuple, func_kwargs=None, descr='', total=1):
        """
        Add a task to be processed with the progress monitored.
        :param func: Function to call (must accept 'pid: int, mbar: Multibar' as kwargs)
        :param func_args: tuple: args of the function to be called
        :param func_kwargs: dict: kwargs of the function to be called
        :param descr: Progress bar label
        :param total: Total iterations expected within the task
        """
        if func_kwargs is None:
            func_kwargs = dict()
        if self.title is None:
            self.title = func.__name__
            self.scroll_area.setWindowTitle(self.title)

        i = len(self.pbars.keys())
        self.add_task_pbar(i, descr, total)
        self.add_task_worker(i, func, func_args, func_kwargs)

    def add_task_pbar(self, i, pbar_descr, iters_total):
        self.pbars[i] = LabeledProgressBar(
            total=iters_total,
            name=pbar_descr,
            pid=i,
            max_update_freq=self.max_bar_update_frequency,
            parent=self.scroll_area
        )
        self.pbars[i].cancelTaskSignal.connect(self.confirm_remove_task)

        self.layout.addWidget(self.pbars[i].prefix_label, i, 0)
        self.layout.addWidget(self.pbars[i], i, 1)
        self.layout.addWidget(self.pbars[i].progress_label, i, 2, alignment=qt.Qt.AlignRight)
        self.layout.addWidget(self.pbars[i].frequency_label, i, 3, alignment=qt.Qt.AlignRight)
        self.layout.addWidget(self.pbars[i].elapsed_time_label, i, 4, alignment=qt.Qt.AlignRight)
        self.layout.addWidget(self.pbars[i].remaining_time_label, i, 5, alignment=qt.Qt.AlignRight)
        self.scroll_area.ensureWidgetVisible(self.pbars[0].progress_label, 10, 10)

    def add_task_worker(self, i, apply_func, func_args, func_kwargs):
        self.tasks[i] = ProcessHandler(apply_func, func_args, func_kwargs, pid=i, pbar=BarUpdater(), pool=self.pool)
        self.tasks[i].updateName.connect(self.update_name)
        self.tasks[i].updateTotal.connect(self.update_total)
        self.tasks[i].updateValue.connect(self.update_value)

    def confirm_remove_task(self, pid):
        confirm = qt.QMessageBox()
        confirm.addButton('Cancel task', qt.QMessageBox.AcceptRole)
        confirm.addButton('Resume task', qt.QMessageBox.RejectRole)
        confirm.setWindowTitle('Confirm cancelling task:')
        confirm.setText(f'Cancel task {pid}?\n {self.pbars[pid].task_name}')

        def cancel():
            print(f'Cancelling task {pid}: {self.pbars[pid].full_name}')
            self.pbars[pid].set_color_cancelled()
            self.end_task(pid)

        confirm.accepted.connect(cancel)
        confirm.exec()

    def begin_processing(self):
        self.setValueSignal.connect(self._set_pbar_value)
        self.setNameSignal.connect(self._set_pbar_name)
        self.setTotalSignal.connect(self._set_pbar_total)

        self.allProcessesFinished.connect(self.app.quit)

        self.app.processEvents()

        self.task_queue = iter(self.tasks.values())
        for i in range(self.batch_size):
            self.start_next()

        self.app.exec()

    def start_next(self):
        try:
            next_task = next(self.task_queue)
            next_task.taskFinished.connect(self.check_all_finished)
            next_task.sendResult.connect(self._get_result)
            next_task.start()
            self.running_tasks[next_task.pid] = next_task
        except StopIteration:
            pass

    def end_task(self, pid):
        if pid in self.running_tasks:
            self.tasks[pid].requestInterruption()
            self.running_tasks[pid].quit()
            self.running_tasks.pop(pid)

    def check_all_finished(self, pid, success):
        self.update_value(pid, self.pbars[pid].total, success)
        self.end_task(pid)
        self.start_next()
        self.scroll_down()
        if len(self.running_tasks) == 0:
            self.allProcessesFinished.emit()

    @handle_mutex_and_catch_runtime
    def update_value(self, pid, value, force=False):
        if self.pbars[pid].allowed_to_set_value(value) or force:
            self.setValueSignal.emit(pid, value)

    @handle_mutex_and_catch_runtime
    def update_name(self, pid, name):
        self.setNameSignal.emit(pid, name)

    @handle_mutex_and_catch_runtime
    def update_total(self, pid, total):
        self.setTotalSignal.emit(pid, total)

    def _set_pbar_value(self, pbar_id, value):
        self.pbars[pbar_id].set_value(value)

    def _set_pbar_name(self, pbar_id, name):
        self.pbars[pbar_id].set_name(name)

    def _set_pbar_total(self, pbar_id, total):
        self.pbars[pbar_id].set_total(total)

    def _get_result(self, pid, result):
        self.results[pid] = result


class BarUpdater:
    def __init__(self):
        self._interruption_requested = False

    def __call__(self, iterator, descr=None, total=None):
        if descr is not None:
            self.update_name(descr)
        if total is not None:
            self.update_total(total)

        iterator = iter(iterator)
        value = 0
        try:
            while True:
                value = next(iterator)
                yield value
                self.update_value(value)
        except StopIteration:
            self.update_value(value)
            return value

    def _set_pipe(self, pipe):
        self._pipe = pipe

    def update_name(self, name):
        self._pipe.send((Messages.name, name))

    def update_total(self, total):
        self._pipe.send((Messages.total, total))

    def update_value(self, value):
        self._pipe.send((Messages.value, value))
        if self._pipe.poll():
            message_type, message = self._pipe.recv()
            if message_type == Messages.interruption_request and message == True:
                raise InterruptTask


def slow_loop_test(idx, count, sleep_time, pbar: BarUpdater = None):
    for i in pbar(range(count), descr=f'{idx}', total=count):
        for j in range(int(30000 * sleep_time * 1000)):
            k = j + i
    return idx, count


def slow_loop_test2(idx, count, sleep_time):
    for i in range(count):
        for j in range(int(30000 * sleep_time * 1000)):
            k = j + i
    return idx, count


def estimate_loop_time(idx, count, sleep_time):
    times = []
    loop_size = int(30000 * sleep_time * 1000)
    for i in range(count):
        t0 = time.time()
        for j in range(loop_size):
            k = j + i
        times.append(time.time() - t0)
    print(f'loop size: {loop_size}, mean duration: {sum(times) / count}')
    return idx, count


def get_random_string(min_length, max_length):
    length = random.randint(min_length, max_length)
    return "".join([chr(random.randint(97, 122)) for i in range(length)])


@wrapped_timer
def run_test_mbar(it, it_args):
    mbar = Multibar()
    for name, args in zip(it, it_args):
        rand_str, rand_count, rand_sleep = args
        mbar.add_task(slow_loop_test, (rand_str, rand_count,), {'sleep_time': rand_sleep}, descr=rand_str, total=rand_count)
    mbar.begin_processing()


@wrapped_timer
def run_test_tqdm_serial(it, it_args):
    for name, args in tqdm(zip(it, it_args), total=num_tasks):
        rand_str, rand_count, rand_sleep = args
        slow_loop_test2(rand_str, rand_count, **{'sleep_time': rand_sleep})


@wrapped_timer
def run_test_mprocess(it, it_args):
    with mp.Pool() as pool:
        procs = []
        for name, args in zip(it, it_args):
            rand_str, rand_count, rand_sleep = args
            procs.append(pool.apply_async(slow_loop_test2, (rand_str, rand_count, rand_sleep,)))
        [proc.get() for proc in tqdm(procs, total=num_tasks)]


if __name__ == "__main__":
    random.seed(123)
    num_tasks = 20
    get_rand_count = lambda: random.randint(10, 100)
    get_rand_sleep = lambda: random.randint(1, 5) * 0.01

    it = iter([get_random_string(8, 64) for i in range(num_tasks)])
    it_args = [[i, get_rand_count(), get_rand_sleep()] for i in copy(it)]
    nums = [i[1] for i in copy(it_args)]

    sorted_by_sleep = sorted(it_args, key=lambda d: d[2])

    # print('min: ', end=''), estimate_loop_time(0, 20, sorted_by_sleep[0][2])
    # print('max: ', end=''), estimate_loop_time(0, 20, sorted_by_sleep[-1][2])

    run_test_mbar(copy(it), copy(it_args))
    # run_test_tqdm_serial(copy(it), copy(it_args))
    # run_test_mprocess(copy(it), copy(it_args))
