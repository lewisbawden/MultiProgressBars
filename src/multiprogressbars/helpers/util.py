from time import time
from random import randint
from PyQt5 import QtCore
from contextlib import contextmanager


@contextmanager
def context_timer(name=''):
    t0 = time()
    print(f'Start {name}:', end='')
    yield t0
    tf = round(time() - t0, 3)
    print(f' Duration: {tf} s')
    print()
    return tf


def wrapped_timer(func):
    def wrapper(*args, **kwargs):
        t0 = time()
        print(f"Enter: {func.__name__}")
        out = func(*args, **kwargs)
        print(f"Duration {func.__name__}: {time() - t0}\n")
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
    length = randint(min_length, max_length)
    return "".join([chr(randint(97, 122)) for _ in range(length)])


def get_rand_count(n, m):
    return randint(n, m)


def get_rand_sleep(p, q, dt):
    return randint(p, q) * dt
