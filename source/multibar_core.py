from time import sleep
from PyQt5 import QtCore, QtWidgets
from multiprocessing import Pool, cpu_count

from bar_updater import BarUpdater
from source.graphics_widgets import ZoomingScrollArea, LabeledProgressBar
from source.process_handler import ProcessHandler
from source.util import handle_mutex_and_catch_runtime


class MultibarCore(QtCore.QObject):
    appStarted = QtCore.pyqtSignal()
    allProcessesFinished = QtCore.pyqtSignal()
    setNameSignal = QtCore.pyqtSignal(int, object)
    setTotalSignal = QtCore.pyqtSignal(int, float)
    setValueSignal = QtCore.pyqtSignal(int, float)

    def __init__(self, title=None, batch_size=None, autoscroll=True,
                 quit_on_finished=True, max_bar_update_frequency=0.02):
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

        self.mutex = QtCore.QMutex()
        self.pool = Pool(self.batch_size)

        self.setup_window(title)
        self.reset_menu()

    def __del__(self):
        if len(self.running_tasks) > 0:
            running_pids = list(self.running_tasks.keys())
            for pid in running_pids:
                self.end_task(pid)
        if self.pool is not None:
            self.pool.close()
            self.pool.terminate()
        sleep(0.5)

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

    def reset_menu(self):
        self.menu = QtWidgets.QMenu()
        autoscroll_str = 'Turn autoscrolling {}'.format('off' if self.autoscroll else 'on')
        autoscroll_act = self.menu.addAction(autoscroll_str)
        autoscroll_act.triggered.connect(self.toggle_autoscroll)
        pause_all_act = self.menu.addAction('Pause / Unpause all (spacebar)')
        pause_all_act.triggered.connect(self.pause_all_tasks)
        self.menu.addSeparator()

        self.widget.menu = self.menu

    def set_autoscroll_enabled(self, enabled):
        self.autoscroll = enabled

    def toggle_autoscroll(self):
        self.autoscroll = not self.autoscroll
        self.reset_menu()

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
        self.layout.addWidget(self.pbars[i].progress_label, i, 2, alignment=QtCore.Qt.AlignRight)
        self.layout.addWidget(self.pbars[i].frequency_label, i, 3, alignment=QtCore.Qt.AlignRight)
        self.layout.addWidget(self.pbars[i].elapsed_time_label, i, 4, alignment=QtCore.Qt.AlignRight)
        self.layout.addWidget(self.pbars[i].remaining_time_label, i, 5, alignment=QtCore.Qt.AlignRight)

    def add_task_worker(self, i, apply_func, func_args, func_kwargs):
        self.tasks[i] = ProcessHandler(apply_func, func_args, func_kwargs, pid=i, pbar=BarUpdater(), pool=self.pool)

    def add_connections(self, i):
        self.tasks[i].updateName.connect(self.update_name)
        self.tasks[i].updateTotal.connect(self.update_total)
        self.tasks[i].updateValue.connect(self.update_value)

        self.pbars[i].cancelTaskSignal.connect(self.confirm_remove_task)
        self.pbars[i].pauseTaskSignal.connect(self.tasks[i].set_pause_requested)
        self.pbars[i].allowAutoScroll.connect(self.set_autoscroll_enabled)

    def confirm_remove_task(self, pid):
        confirm = QtWidgets.QMessageBox()
        confirm.addButton('Cancel task', QtWidgets.QMessageBox.AcceptRole)
        confirm.addButton('Resume task', QtWidgets.QMessageBox.RejectRole)
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

        def start_initial_batch():
            self.task_queue = iter(self.tasks.values())
            for i in range(self.batch_size):
                self.start_next()

        self.app.processEvents()

        QtCore.QTimer.singleShot(0, self.appStarted.emit)
        self.appStarted.connect(start_initial_batch)
        self.appStarted.connect(self.scroll_down)
        if self.quit_on_finished:
            self.allProcessesFinished.connect(self.app.quit, QtCore.Qt.QueuedConnection)

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

    def pause_all_tasks(self):
        self.all_paused = not self.all_paused
        for i in self.running_tasks:
            self.pbars[i].paused = self.all_paused
            self.tasks[i].set_pause_requested(self.all_paused)

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

    def get_results(self):
        return {k: self.results[k] for k in sorted(self.results.keys())}
