from source.multibar_core import MultibarCore


class Multibar:
    def __init__(self, title=None, batch_size=None, autoscroll=True,
                 quit_on_finished=True, max_bar_update_frequency=0.02):
        self._mbar = MultibarCore(
            title=title, batch_size=batch_size, autoscroll=autoscroll,
            quit_on_finished=quit_on_finished, max_bar_update_frequency=max_bar_update_frequency)

    def __del__(self):
        self._mbar.__del__()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        yield self._mbar.__exit__(exc_type, exc_val, exc_tb)

    def add_task(self, func: callable, func_args: tuple = (), func_kwargs: dict = None, descr='', total=1):
        """
        Add a task to be processed with the progress monitored.
        :param func: Function to call (must accept 'pid: int, mbar: Multibar' as kwargs)
        :param func_args: tuple: args of the function to be called
        :param func_kwargs: dict: kwargs of the function to be called
        :param descr: Progress bar label
        :param total: Total iterations expected within the task
        """
        self._mbar.add_task(func, func_args, func_kwargs, descr, total)

    def begin_processing(self):
        self._mbar.begin_processing()

    def update_name(self, name):
        self._mbar.update_name(name)

    def update_total(self, total):
        self._mbar.update_total(total)

    def update_value(self, value):
        self._mbar.update_value(value)

    def get(self):
        self._mbar.begin_processing()
        return self._mbar.get_results()