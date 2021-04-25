from PyQt5 import QtCore, QtWidgets
from multiprocessing import Pool, cpu_count

from multibar.bar_updater import BarUpdater
from multibar.helpers.graphics_widgets import ZoomingScrollArea, LabeledProgressBar, Menu
from multibar.helpers.process_handler import ProcessHandler
from multibar.helpers.util import handle_mutex_and_catch_runtime


class MultibarCore(QtCore.QObject):
    appStarted = QtCore.pyqtSignal()
    allProcessesFinished = QtCore.pyqtSignal()
    setNameSignal = QtCore.pyqtSignal(int, object)
    setTotalSignal = QtCore.pyqtSignal(int, float)
    setValueSignal = QtCore.pyqtSignal(int, float)

    def __init__(self, title=None, batch_size=None, autoscroll=True, quit_on_finished=True,
                 max_bar_update_frequency=0.02):
        super(MultibarCore, self).__init__()
        self.app = QtWidgets.QApplication([])

        self.title = title
        self.batch_size = cpu_count() if batch_size is None else batch_size
        self.max_bar_update_frequency = max_bar_update_frequency

        self.all_paused = False
        self.autoscroll = autoscroll
        self.quit_on_finished = quit_on_finished

        self.pbars = dict()
        self.tasks = dict()
        self.running_tasks = dict()
        self.results = dict()
        self.failed_tasks = dict()

        self.mutex = QtCore.QMutex()
        self.pool = Pool(self.batch_size)

        self.setup_window(title)

    def __del__(self):
        QtCore.QMutexLocker(self.mutex)
        if self.pool is not None:
            self.pool.close()
        if len(self.running_tasks) > 0:
            running_pids = list(self.running_tasks.keys())
            for pid in running_pids:
                self.end_task(pid)
        if self.pool is not None:
            self.pool.terminate()

    def setup_window(self, title):
        self.layout = QtWidgets.QGridLayout()
        self.widget = QtWidgets.QWidget()
        self.widget.setLayout(self.layout)

        # window is a QScrollArea widget
        self.scroll_area = ZoomingScrollArea()
        self.scroll_area.setWindowTitle(title)
        self.scroll_area.setWidget(self.widget)
        self.scroll_area.setWidgetResizable(True)

        # force it to open as 1/3 width and height the screen, placed in the bottom right corner
        screen_size = QtWidgets.QDesktopWidget().screenGeometry(-1)
        screen_w, screen_h = screen_size.width(), screen_size.height()
        panel_w, panel_h = screen_w // 3, screen_h // 3
        panel_posx, panel_posy = screen_w - 1.05 * panel_w, (0.95 * screen_h) - 1.1 * panel_h
        self.scroll_area.resize(panel_w, panel_h)
        self.scroll_area.move(panel_posx, panel_posy)

        self.scroll_area.pauseAllSignal.connect(self.pause_all_tasks)

        self.scroll_area.setFocus()
        self.scroll_area.show()

    def set_autoscroll_enabled(self, enabled):
        self.autoscroll = enabled

    def scroll_down(self):
        if self.autoscroll:
            bottom = 0
            if len(self.results) > 0:
                bottom = min(max(self.results) + 1, len(self.pbars) - 1)
            self.scroll_area.ensureWidgetVisible(self.pbars[bottom].progress_label, 10, 10)

    def add_task(self, func: callable, func_args: tuple = (), func_kwargs: dict = None, descr='', total=1):
        if func_kwargs is None:
            func_kwargs = dict()
        if self.title is None:
            self.title = func.__name__
            self.scroll_area.setWindowTitle(self.title)

        i = len(self.pbars.keys())
        self.add_task_pbar(i, descr, total)
        self.add_task_worker(i, func, func_args, func_kwargs)
        self.add_connections(i)

    def add_task_pbar(self, i, pbar_descr, iters_total):
        self.pbars[i] = LabeledProgressBar(
            total=iters_total,
            name=pbar_descr,
            pid=i,
            max_update_freq=self.max_bar_update_frequency,
            parent=self.widget
        )
        self.layout.addWidget(self.pbars[i].prefix_label, i, 0)
        self.layout.addWidget(self.pbars[i], i, 1)
        self.layout.addWidget(self.pbars[i].progress_label, i, 2, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.pbars[i].frequency_label, i, 3, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.pbars[i].elapsed_time_label, i, 4, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.pbars[i].remaining_time_label, i, 5, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

    def add_task_worker(self, i, apply_func, func_args, func_kwargs):
        self.tasks[i] = ProcessHandler(apply_func, func_args, func_kwargs, pid=i, pbar=BarUpdater(), pool=self.pool)

    def add_connections(self, i):
        self.tasks[i].updateNameSignal.connect(self.update_name)
        self.tasks[i].updateTotalSignal.connect(self.update_total)
        self.tasks[i].updateValueSignal.connect(self.update_value)

        self.pbars[i].createMenuSignal.connect(self.create_menu)

    def begin_processing(self):
        self.setValueSignal.connect(self._set_pbar_value)
        self.setNameSignal.connect(self._set_pbar_name)
        self.setTotalSignal.connect(self._set_pbar_total)

        def start_initial_batch():
            self.task_queue = iter(self.tasks.values())
            for _ in range(self.batch_size):
                self.start_next()

        self.app.processEvents()

        QtCore.QTimer.singleShot(0, self.appStarted.emit)
        self.appStarted.connect(start_initial_batch)
        self.appStarted.connect(self.scroll_down)
        if self.quit_on_finished:
            self.allProcessesFinished.connect(self.app.quit)

        self.app.exec()

    def start_next(self):
        try:
            next_task = next(self.task_queue)
            next_task.taskFinishedSignal.connect(self.dequeue_task)
            next_task.sendResultSignal.connect(self._get_result)
            next_task.start()
            self.running_tasks[next_task.pid] = next_task
        except StopIteration:
            pass

    def end_task(self, pid, exit_code=ProcessHandler.SUCESSFUL):
        if exit_code == ProcessHandler.CANCELLED:
            self.pbars[pid].set_color(LabeledProgressBar.ColorCancelled)
            self.failed_tasks[pid] = ProcessHandler.CANCELLED
        if exit_code == ProcessHandler.EXCEPTION_RAISED:
            self.pbars[pid].set_color(LabeledProgressBar.ColorException)
            self.failed_tasks[pid] = ProcessHandler.EXCEPTION_RAISED

        if pid in self.running_tasks:
            self.tasks[pid].requestInterruption()
            self.running_tasks[pid].quit()
            self.running_tasks.pop(pid)

    def dequeue_task(self, pid, exit_code):
        self.update_value(pid, self.pbars[pid].total, exit_code)
        self.end_task(pid, exit_code)
        self.start_next()
        self.scroll_down()
        if len(self.running_tasks) == 0:
            self.allProcessesFinished.emit()

    def pause_all_tasks(self):
        self.all_paused = not self.all_paused
        for i in self.running_tasks:
            self.pbars[i].paused = self.all_paused
            self.tasks[i].set_pause_requested(self.all_paused)

    def cancel_task(self, pid):
        confirmed = Menu.confirm_remove_task(pid, self.pbars[pid].full_name)
        if confirmed:
            self.end_task(pid, LabeledProgressBar.ColorCancelled)
            print(f'Cancelling task {pid}: {self.pbars[pid].full_name}')

    def pause_task(self, pid):
        self.tasks[pid].set_pause_requested(not self.pbars[pid].paused)
        self.pbars[pid].paused = not self.pbars[pid].paused

    def create_menu(self, pid, mouse_pos, paused):
        # create the menu
        menu = Menu(self.autoscroll, pid, paused)

        # connect the menu signals to their slots
        menu.autoscrollSignal.connect(self.set_autoscroll_enabled, QtCore.Qt.ConnectionType.QueuedConnection)
        menu.pauseAllSignal.connect(self.pause_all_tasks)
        menu.cancelTaskSignal.connect(self.cancel_task)
        menu.pauseTaskSignal.connect(self.pause_task)

        # execute the menu
        autoscroll_state = self.autoscroll  # reset autoscroll to previous state, disable while menu active
        self.set_autoscroll_enabled(False)
        menu.exec(mouse_pos)
        self.set_autoscroll_enabled(autoscroll_state)

    @handle_mutex_and_catch_runtime
    def update_value(self, pid, value, exit_code=ProcessHandler.EXCEPTION_RAISED):
        if self.pbars[pid].allowed_to_set_value(value) or exit_code == ProcessHandler.SUCESSFUL:
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

    def get_results(self):
        return [{k: self.results[k] for k in sorted(self.results.keys())},
                {k: self.failed_tasks[k] for k in sorted(self.failed_tasks.keys())}]
