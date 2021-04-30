from multiprogressbars.multibar import Multibar
from multiprogressbars.helpers.util import wrapped_timer, get_rand_string, get_rand_count
from multiprogressbars.bar_updater import BarUpdater


def exception_test(idx, count, count_inner, pbar: BarUpdater = None):
    for i in pbar(range(count), desc=f'{idx}', total=count):
        if i > 70:
            raise ValueError('Example of possible exception in task')
        for j in range(int(count_inner)):
            _ = j + i
    return idx, count


def slow_loop_test(idx, count, count_inner, pbar: BarUpdater = None):
    for i in pbar(range(count), desc=f'{idx}', total=count):
        for j in range(int(count_inner)):
            _ = j + i
    return idx, count


@wrapped_timer
def run_test_mbar(it, outer_lb, outer_ub, inner_lb, inner_ub, func=slow_loop_test):
    # create the Multibar object - can add tasks and get results through this
    mbar = Multibar()

    # 'it' was a list of strings which are the random names of the tasks
    for name in it:
        rand_count_outer = get_rand_count(outer_lb, outer_ub)
        rand_count_inner = get_rand_count(inner_lb, inner_ub)

        # tasks are created using the following example arguments - they are not run immediately
        mbar.add_task(
            func=func,
            func_args=(name, rand_count_outer,),
            func_kwargs={'count_inner': rand_count_inner}
        )

    # processing begins by calling 'begin_processing()', or 'get()'
    # both are blocking until the tasks are finished or the app is quit.
    # this quits all processes and returns the results that have already finished
    print(mbar.get())


def run_example(
        num_tasks=25,
        iters_lb=10,
        iters_ub=100,
        inner_loop_lb=1e5,
        inner_loop_ub=1e6
):
    name_list = [get_rand_string(8, 32) for _ in range(num_tasks)]
    run_test_mbar(name_list, iters_lb, iters_ub, inner_loop_lb, inner_loop_ub)


def run_example_exceptions(
        num_tasks=25,
        iters_lb=10,
        iters_ub=100,
        inner_loop_lb=1e5,
        inner_loop_ub=1e6
):
    name_list = [get_rand_string(8, 32) for _ in range(num_tasks)]
    run_test_mbar(name_list, iters_lb, iters_ub, inner_loop_lb, inner_loop_ub, exception_test)


if __name__ == "__main__":
    # Initial parameters to imitate tasks that need processing, and individual monitoring

    # tasks to run (bars displayed)
    num_tasks = 25

    # get random counts for the example tasks (two loops, inner and outer)
    # bounds for outer loop range - this sets the total iterations of the example task
    n, m = 10, 100
    # bounds for inner loop range - this simulates a calculation between iterations of the main loop
    p, q = 1e5, 1e6

    # iterator - in this case is a list of random strings but it can be anything iterable
    name_list = [get_rand_string(8, 32) for _ in range(num_tasks)]

    run_test_mbar(name_list, n, m, p, q)
