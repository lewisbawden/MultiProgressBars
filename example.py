from multibar.multibar import Multibar
from multibar.helpers.util import wrapped_timer, get_rand_string, get_rand_count
from multibar.bar_updater import BarUpdater


def slow_loop_test(idx, count, count_inner, pbar: BarUpdater = None):
    for i in pbar(range(count), descr=f'{idx}', total=count):
        for j in range(int(count_inner)):
            _ = j + i
    return idx, count


@wrapped_timer
def run_test_mbar(it, outer_lb, outer_ub, inner_lb, inner_ub):
    # create the Multibar object - can add tasks and get results through this
    mbar = Multibar()

    # 'it' was a list of strings which are the random names of the tasks
    for name in it:
        rand_count_outer = get_rand_count(outer_lb, outer_ub)
        rand_count_inner = get_rand_count(inner_lb, inner_ub)

        # tasks are created using the following example arguments - they are not run immediately
        mbar.add_task(
            func=slow_loop_test,
            func_args=(name, rand_count_outer,),
            func_kwargs={'count_inner': rand_count_inner},
            descr=name,
            total=rand_count_outer
        )

    # processing begins by calling 'begin_processing()', or 'get()'
    # both are blocking until the tasks are finished or the app is quit.
    # this quits all processes and returns the results that have already finished
    print(mbar.get())


if __name__ == "__main__":
    # Initial parameters to imitate tasks that need processing, and individual monitoring

    # tasks to run (bars displayed)
    num_tasks = 25
    # get random counts for the example tasks (two loops, inner and outer)
    # bounds for outer loop range - this sets the total iterations of the example task
    n, m = 10, 50
    # bounds for inner loop range - this simulates a calculation between iterations of the main loop
    p, q = 5e5, 10e5

    # iterator - in this case is a list of random strings but it can be anything iterable
    name_list = [get_rand_string(8, 32) for _ in range(num_tasks)]

    run_test_mbar(name_list, n, m, p, q)
