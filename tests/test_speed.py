import sys
from time import time
from random import seed
from multiprocessing import Pool
from tqdm import tqdm

from multiprogressbars.multibar import Multibar
from multiprogressbars.helpers.util import get_rand_string, get_rand_count
from multiprogressbars.bar_updater import BarUpdater


def slow_loop_test_mbar(idx, count, count_inner, pbar: BarUpdater = None):
    for i in pbar(range(count), desc=f'{idx}', total=count):
        for j in range(int(count_inner)):
            _ = j + i
    return idx, count


def slow_loop_test_tqdm(idx, count, count_inner):
    for i in range(count):
        for j in range(int(count_inner)):
            _ = j + i
    return idx, count


def slow_loop_test_mppool(idx, count, count_inner):
    for i in range(count):
        for j in range(int(count_inner)):
            _ = j + i
    return idx, count


# @wrapped_timer
def run_test_mbar(it, outer_lb, outer_ub, inner_lb, inner_ub):
    t0 = time()
    mbar = Multibar()
    for name in it:
        rand_count_outer = get_rand_count(outer_lb, outer_ub)
        rand_count_inner = get_rand_count(inner_lb, inner_ub)
        mbar.add_task(slow_loop_test_mbar, (name, rand_count_outer, rand_count_inner,))
    mbar.get()
    mbar.close()
    return time() - t0


# @wrapped_timer
def run_test_tqdm_serial(it, outer_lb, outer_ub, inner_lb, inner_ub):
    t0 = time()
    results = []
    for name in tqdm(it, total=len(it), file=sys.stdout):
        rand_count_outer = get_rand_count(outer_lb, outer_ub)
        rand_count_inner = get_rand_count(inner_lb, inner_ub)
        results.append(slow_loop_test_tqdm(name, rand_count_outer, rand_count_inner))
    return time() - t0


# @wrapped_timer
def run_test_mppool(it, outer_lb, outer_ub, inner_lb, inner_ub):
    t0 = time()
    results = []
    procs = []
    with Pool() as pool:
        for name in it:
            rand_count_outer = get_rand_count(outer_lb, outer_ub)
            rand_count_inner = get_rand_count(inner_lb, inner_ub)
            procs.append(pool.apply_async(slow_loop_test_mppool, (name, rand_count_outer, rand_count_inner,)))
        for proc in tqdm(procs, total=len(procs), file=sys.stdout):
            result = proc.get()
            results.append(result)
    return time() - t0


def estimate_loop_time(count_inner, test_size=100):
    times = []
    for i in range(test_size):
        t0 = time()
        for j in range(int(count_inner)):
            _ = j + i
        times.append(time() - t0)
    print(f'With loop size: {count_inner}, iterations {test_size},\n\tapprox. loop time: {round(sum(times) / test_size, 3)}')


def run_speed_tests(num_tasks, n, m, p, q):
    name_list = [get_rand_string(8, 32) for _ in range(num_tasks)]

    estimate_loop_time((p + q) // 2, (n + m) // 2)

    a = run_test_mbar(name_list, n, m, p, q)
    b = run_test_mppool(name_list, n, m, p, q)
    c = run_test_tqdm_serial(name_list, n, m, p, q)
    return a, b, c


if __name__ == "__main__":
    seed(123)

    a, b, c = run_speed_tests(10, 100, 1000, 1e3, 1e4)
    print(f'mbar: {round(a, 3)}, pool: {round(b, 3)}, serial: {round(c, 3)}\n')
    a, b, c = run_speed_tests(10, 100, 1000, 1e4, 1e5)
    print(f'mbar: {round(a, 3)}, pool: {round(b, 3)}, serial: {round(c, 3)}\n')
    a, b, c = run_speed_tests(50, 100, 1000, 1e3, 1e4)
    print(f'mbar: {round(a, 3)}, pool: {round(b, 3)}, serial: {round(c, 3)}\n')
    a, b, c = run_speed_tests(50, 1000, 10000, 1e3, 1e4)
    print(f'mbar: {round(a, 3)}, pool: {round(b, 3)}, serial: {round(c, 3)}\n')
    a, b, c = run_speed_tests(50, 10, 100, 1e5, 1e6)
    print(f'mbar: {round(a, 3)}, pool: {round(b, 3)}, serial: {round(c, 3)}\n')
