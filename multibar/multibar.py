from multibar.helpers.multibar_core import MultibarCore


class Multibar:
    """
    Object for adding tasks, processing tasks, and collecting results.
    """
    def __init__(self, title=None, batch_size=None, autoscroll=True,
                 quit_on_finished=True, max_bar_update_frequency=0.02):
        self._mbar = MultibarCore(
            title=title, batch_size=batch_size, autoscroll=autoscroll, quit_on_finished=quit_on_finished,
            max_bar_update_frequency=max_bar_update_frequency)
        self.running = False

    def __del__(self):
        self._mbar.__del__()

    def add_task(self, func: callable, func_args: tuple = (), func_kwargs: dict = None, descr='', total=1):
        """
        Add a task to be processed and monitored. Processing is not started until requested.
        Tasks are created as a QThread object, the processing is executed using a multiprocessing.Pool object.

        :param func: Function to call (must accept 'pid: int, mbar: Multibar' as kwargs)
        :param func_args: tuple: args of the function to be called
        :param func_kwargs: dict: kwargs of the function to be called
        :param descr: Progress bar label
        :param total: Total iterations expected within the task
        """
        self._mbar.add_task(func, func_args, func_kwargs, descr, total)

    def begin_processing(self):
        """
        Begin processing the QThread tasks, executing the target function using a multiprocessing.Pool.
        Call is blocking until tasks are executed or cancelled (or the app closed).
        """
        self.running = True
        self._mbar.begin_processing()

    def get(self):
        """
        Collect results once they are finished. Starts processing if it is not processing.
        Call is blocking until tasks are executed or cancelled (or the app closed).
        :return: list[results: dict, failed_tasks: dict]
        """
        if not self.running:
            self._mbar.begin_processing()
        return self._mbar.get_results()
