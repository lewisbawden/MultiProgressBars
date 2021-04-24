import time
import random
from copy import copy
from multiprocessing import Pool
from tqdm import tqdm

from multibar import Multibar
from source.util import wrapped_timer
from bar_updater import BarUpdater


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
    i0 = time.time()
    for i in range(count):
        t0 = time.time()
        for j in range(loop_size):
            k = j + i
        times.append(time.time() - t0)
    print(f'loop size: {loop_size}, mean duration: {sum(times) / count}')
    print(f'full task iterations: {count}, duration: {time.time() - i0}')
    return idx, count


def get_random_string(min_length, max_length):
    length = random.randint(min_length, max_length)
    return "".join([chr(random.randint(97, 122)) for i in range(length)])


@wrapped_timer
def run_test_mbar(it, it_args):
    with Multibar() as mbar:
        for name, args in zip(it, it_args):
            rand_str, rand_count, rand_sleep = args
            mbar.add_task(slow_loop_test, (rand_str, rand_count,), {'sleep_time': rand_sleep}, descr=rand_str, total=rand_count)
    print(mbar.get())


@wrapped_timer
def run_test_tqdm_serial(it, it_args):
    for name, args in tqdm(zip(it, it_args), total=num_tasks):
        rand_str, rand_count, rand_sleep = args
        slow_loop_test2(rand_str, rand_count, **{'sleep_time': rand_sleep})


@wrapped_timer
def run_test_mprocess(it, it_args):
    with Pool() as pool:
        procs = []
        for name, args in zip(it, it_args):
            rand_str, rand_count, rand_sleep = args
            procs.append(pool.apply_async(slow_loop_test2, (rand_str, rand_count, rand_sleep,)))
        [proc.get() for proc in tqdm(procs, total=num_tasks)]


if __name__ == "__main__":
    random.seed(123)
    num_tasks = 50

    it = iter([get_random_string(8, 64) for i in range(num_tasks)])
    it_args = [[i, get_rand_count(), get_rand_sleep()] for i in copy(it)]
    nums = [i[1] for i in copy(it_args)]

    sorted_by_sleep = sorted(it_args, key=lambda d: d[2])

    # print('min: '), estimate_loop_time(0, 10, sorted_by_sleep[0][2])
    # print('max: '), estimate_loop_time(0, 10, sorted_by_sleep[-1][2])
    # print('min: '), estimate_loop_time(0, 50, sorted_by_sleep[0][2])
    # print('max: '), estimate_loop_time(0, 50, sorted_by_sleep[-1][2])

    run_test_mbar(copy(it), copy(it_args))
    # run_test_tqdm_serial(copy(it), copy(it_args))
    # run_test_mprocess(copy(it), copy(it_args))
