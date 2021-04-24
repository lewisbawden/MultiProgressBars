import time
import random
from PyQt5 import QtCore

random.seed(123)


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
        QtCore.QMutexLocker(inst.mutex)
        try:
            return func(inst, *args, **kwargs)
        except RuntimeError:
            return None
    return wrapper


def get_rand_string(min_length, max_length):
    length = random.randint(min_length, max_length)
    return "".join([chr(random.randint(97, 122)) for i in range(length)])


def get_rand_count(n, m):
    return random.randint(n, m)


def get_rand_sleep(p, q, dt):
    return random.randint(p, q) * dt
