import os
import time
import random
from copy import copy
import PyQt5.Qt as qt


def wrapped_timer(func):
    def wrapper(*args, **kwargs):
        t0 = time.time()
        print(f"Enter: {func.__name__}")
        out = func(*args, **kwargs)
        print(f"Duration {func.__name__}: {time.time() - t0}")
        return out
    return wrapper


class Worker(qt.QThread):
    finished = qt.pyqtSignal(object)
    send_result = qt.pyqtSignal(object, object)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.pid = kwargs.get('pid', None)

    def run(self):
        out = self.func(*self.args, **self.kwargs)
        self.send_result.emit(self.pid, out)
        self.finished.emit(self.pid)


class LabeledProgressBar(qt.QProgressBar):
    unit_conv = {3: 'k', 6: 'M', 9: 'G', 12: 'T'}

    def __init__(self, total=100, name=" ", units_symbol="", parent=None):
        super(LabeledProgressBar, self).__init__(parent)
        self.name = f"{name}"
        self.progress = 0
        self.total = total
        self.units_symbol = units_symbol

        self.min_update_increment = 1  # e.g. total // 500
        self.max_update_frequency = 0  # e.g. 0.01 seconds
        self.last_updated = self.get_time()

        self.total_str = self.get_formatted_number(total)
        self.progress_str = " / ".join([self.get_formatted_number(self.progress), self.total_str])

        self.prefix_label = qt.QLabel(self.name)
        self.progress_label = qt.QLabel(self.progress_str)

        self.setRange(0, total)
        self.setMouseTracking(False)
        self.setTextVisible(False)

        self.show()

    def get_formatted_number(self, value):
        factor, unit_prefix = self.get_units_prefix(value)
        return "{:.2f} {}{}".format(value / (10 ** factor), unit_prefix, self.units_symbol)

    @staticmethod
    def get_time():
        return time.time()

    def allowed_to_set_value(self, value):
        freq_cond = self.get_time() - self.last_updated >= self.max_update_frequency
        value_cond = value - self.value() >= self.min_update_increment
        return freq_cond and value_cond

    def set_value(self, value):
        self.setValue(value)
        self.last_updated = self.get_time()
        self.progress_str = " / ".join([self.get_formatted_number(value), self.total_str])
        self.progress_label.setText(self.progress_str)

    def set_name(self, name):
        self.name = f"{name}"
        self.prefix_label.setText(self.name)

    def set_total(self, total):
        self.total = total
        self.setRange(0, self.total)
        self.total_str = self.get_formatted_number(total)
        self.progress_str = " / ".join([self.get_formatted_number(self.progress), self.total_str])
        self.progress_label.setText(self.progress_str)

    def get_units_prefix(self, num):
        # uses base10 location of digits to get units prefix, i.e. not equivlant to byte conversion if units are bytes
        digits = len(str(num)) - 2
        factor = 3 * round(digits / 3)
        if factor not in self.unit_conv.keys():
            if factor > 2:
                factor = max(self.unit_conv.keys())
            else:
                return 1, ''
        return factor, self.unit_conv[factor]


class Multibar(qt.QObject):
    allProcessesFinished = qt.pyqtSignal()
    setValueSignal = qt.pyqtSignal(object, object)
    setNameSignal = qt.pyqtSignal(object, object)
    setTotalSignal = qt.pyqtSignal(object, object)

    def __init__(self, func, it, it_args=None, batch_size=None):
        super(Multibar, self).__init__()
        self.func = func
        self.it = copy(it)
        self.it_args = it_args

        self.batch_size = os.cpu_count() - 1 if batch_size is None else batch_size
        task_generator = (Worker(self.func, *self.it_args[pid], pid=pid, mbar=self)
                          for pid, itx in enumerate(self.it))
        self.task_queue = iter(task_generator)

        self.running_tasks = dict()
        self.results = {}

        self.mutex = qt.QMutex()

        self.setup_window()
        self.setup_pbars()

        self.scroll_area.show()

        self.initialise_processing()

    def setup_window(self):
        self.layout = qt.QGridLayout()
        self.widget = qt.QWidget()
        self.widget.setEnabled(False)
        self.widget.setLayout(self.layout)

        # window is a QScrollArea widget
        self.scroll_area = qt.QScrollArea()
        self.scroll_area.setWindowTitle("{}: progress updates".format(self.func.__name__))
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

    def setup_pbars(self):
        self.pbars = {}
        for i, args in enumerate(self.it_args):
            name, total, _ = args
            self.pbars[i] = LabeledProgressBar(total=total, name=name, units_symbol="B", parent=self.scroll_area)
            self.layout.addWidget(self.pbars[i].prefix_label, i, 0)
            self.layout.addWidget(self.pbars[i], i, 1)
            self.layout.addWidget(self.pbars[i].progress_label, i, 2, alignment=qt.Qt.AlignRight)

        # update must be done through sending a signal so the task itself is not updating the main display
        self.setValueSignal.connect(self._set_pbar_value)

    def initialise_processing(self):
        for i in range(self.batch_size):
            self.start_next()

    def start_next(self):
        try:
            next_task = next(self.task_queue)
            next_task.finished.connect(self.check_all_finished)
            next_task.send_result.connect(self.get_result)
            next_task.start()
            self.running_tasks[next_task.pid] = next_task
        except StopIteration:
            pass

    def end_task(self, pid):
        if pid in self.running_tasks:
            self.update_value(pid, self.pbars[pid].maximum())
            self.running_tasks[pid].deleteLater()
            self.running_tasks[pid].quit()
            self.running_tasks.pop(pid)

    def check_all_finished(self, pid):
        self.end_task(pid)
        self.start_next()
        if len(self.running_tasks) == 0:
            self.allProcessesFinished.emit()

    def update_value(self, pid, value):
        locker = qt.QMutexLocker(self.mutex)
        try:
            if self.pbars[pid].allowed_to_set_value(value):
                self.setValueSignal.emit(pid, value)
        except RuntimeError:
            pass

    def update_name(self, pid, name):
        locker = qt.QMutexLocker(self.mutex)
        try:
            self.setNameSignal.emit(pid, name)
        except RuntimeError:
            pass

    def update_total(self, pid, total):
        locker = qt.QMutexLocker(self.mutex)
        try:
            self.setTotalSignal.emit(pid, total)
        except RuntimeError:
            pass

    def _set_pbar_value(self, pbar_id, value):
        self.pbars[pbar_id].set_value(value)

    def _set_pbar_name(self, pbar_id, name):
        self.pbars[pbar_id].set_name(name)

    def _set_pbar_total(self, pbar_id, total):
        self.pbars[pbar_id].set_total(total)

    def get_result(self, pid, result):
        self.results[pid] = result


def multibar(it, it_args, func):
    app = qt.QApplication([])
    mbar = Multibar(it, it_args, func)
    mbar.all_processes_finished.connect(app.quit)
    yield mbar
    app.exec()
    return mbar


@wrapped_timer
def multibar_test(it, it_args, func):
    app = qt.QApplication([])
    mbar = Multibar(func, it, it_args)
    mbar.allProcessesFinished.connect(app.quit)
    app.exec()


def sleep_test_callback(idx, count, sleep_time, pid, mbar: Multibar):
    for i in range(count):
        time.sleep(sleep_time)
        mbar.update_value(pid, i)
    return idx, count


def slow_loop_test(idx, count, sleep_time, pid, mbar: Multibar):
    for i in range(count):
        for j in range(10000):
            k = j + i
        mbar.update_value(pid, i)
    return idx, count


def get_random_string(min_length, max_length):
    length = random.randint(min_length, max_length)
    return "".join([chr(random.randint(97, 122)) for i in range(length)])


def run_test():
    it = iter([get_random_string(8, 64) for i in range(num_tasks)])  # iter(range(num_tasks))
    it_args = [[i, get_rand_count(), get_rand_sleep()] for i in copy(it)]

    multibar_test(copy(it), it_args, slow_loop_test)


if __name__ == "__main__":
    #TODO: allow Multibar object setup without giving args or funcs - test using 'with' context to initialise
    # add create_task feature, takes func, task_name, args, create pid in this func, have a lookup of pid->name
    # setup main object without displaying anything, add tasks iteratively through loop outside main func only
    # add a terminate all tasks when deleting
    # test funcs for updating total and name in the target func
    # add iterations/s label, time elapsed label, time remaining estimate label
    # create decorator for try except and locker

    random.seed(123)
    num_tasks = 20
    get_rand_count = lambda: random.randint(100, 2000)
    get_rand_sleep = lambda: random.randint(1, 5) * 0.001

    run_test()
