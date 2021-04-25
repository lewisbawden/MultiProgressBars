from multibar.helpers.process_handler import Messages, InterruptTask


class BarUpdater:
    """
    Object that wraps an iterator and handles updating the progress bar.
    This must be added to the arguments of the target function of tasks that are added
    through the main Multibar object. This object is run in a separate Python process and communicates
    via a localhost socket with the ProcessHandler QThread that is controlling it.

    Argument of the form e.g. 'pbar: BarUpdater = None' must be added to the tasks function header manually.
    """
    def __init__(self):
        self._interruption_requested = False
        self._manually_updating_value = False

    def __del__(self):
        if hasattr(self, '_pipe') and self._pipe is not None and not self._pipe.closed:
            self._pipe.close()

    def __call__(self, iterator, descr=None, total=None):
        """
        Object is callable and yields results of an iterator.
        Handles updating the value itself each iteration.
        :param iterator: 'iterable' object whose values are yielded sequentially
        :param descr: str: description of the progress bar
        :param total: value the progress bar is counting towards
        """
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
                self._update_value(value)
        except StopIteration:
            self._update_value(value)
            return value

    def _set_pipe(self, pipe):
        self._pipe = pipe

    def _wait_for_unpause(self):
        while True:
            if self._pipe.poll(0.1):
                message_type, message = self._pipe.recv()
                if message_type == Messages.pause_request and message == False:
                    return

    def _handle_update_messages(self, value):
        self._pipe.send((Messages.value, value))
        if self._pipe.poll():
            message_type, message = self._pipe.recv()
            if message_type == Messages.interruption_request and message == True:
                raise InterruptTask
            if message_type == Messages.pause_request and message == True:
                self._wait_for_unpause()

    def _update_value(self, value):
        if not self._manually_updating_value:
            self._handle_update_messages(value)

    def update_value(self, value):
        """
        Manually update the progress bar value to the given 'value'
        :param value: update progress bar to 'value' (not by, i.e. not an increment)
        """
        self._manually_updating_value = True
        self._handle_update_messages(value)

    def update_name(self, name):
        """
        Manually set the name / description of the progress bar
        """
        self._pipe.send((Messages.name, name))

    def update_total(self, total):
        """
        Manually set the total (maximum value of) the progress bar
        """
        self._pipe.send((Messages.total, total))
