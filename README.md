# multiprogressbars

multiprogressbars is a Python library for processing tasks via pickled processes using the multiprocessing library.
It uses the localhost to communicate progress, which is displayed in real time using a GUI built with PyQt5.
The GUI offers some features custom interrupting and throttling tasks for convenience.

#### Features
Menu appears when right clicking on any bar with the following options:
* Resizeable, moveable, scrollable GUI for displaying the progress bars 
* Pinch and scroll zooming by enlarging text
* Autoscrolling enable / disable (so running tasks are always visible)
* Basic speed and remaining time estimation
* Ability to (un)pause any / all tasks.
    * Pausing all tasks also is shortcut to the spacebar
* Ability to cancel any given task (signified as 'grey').
* Traceback on any failed tasks without interrupting processing of other tasks (signified as 'red').
* Throttling cpu core usage by dynamically setting the pool size when requested through the menu
    * The options range from 1 to your cpu core total and the current tasks are (un)paused appropriately and dispatched when a process becomes available

### Structure
#### Interface
The two interface objects are:
* multiprogressbars.multibar.Multibar
  * This object handles creating and dispatching tasks
* multiprogressbars.bar_updater.BarUpdater
  * This object handles communicating updates to the progress bar it runs
  * It is not necessary for the user to know which bar is run by which process this is done internally

#### Helpers
The Multibar and BarUpdater objects both have an underlying driver which they inherit from.
The Multibar object handles the main GUI and has information about the
   * the multiprocessing.Pool
   * the tasks
   * the progress bars
   * the results

The tasks are distributed using QThreads to a multiprogressbars.helpers.process_handler.ProcessHandler object.
Each ProcessHandler uses a multiprocessing.Pool to asynchronously run its given task as pickled process.
It has a two-way local host multiprocessing.Pipe for the task to communicate its results as they come in, and for the ProcessHandler to signal to interrupt processing if requested.

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install multiprogressbars.
```bash
pip install multiprogressbars
``` 

For now, PyQt5 must be installed separately with the following command:
```bash
pip install pyqt5
``` 

## Usage
### Potential use cases:
For tasks that would benefit from python multiprocessing this is a vast improvement on serial execution. 
It does not improve on the speed of the multiprocessing library alone.

It is likely to be best used when there are tasks that could be done in parallel that have a long enough iterative execution that individual task progress is worth monitoring.
Some examples would be loading and processing a log file, or processing and saving results of a calculation.

#### Try the examples
First example running randomly generated tasks that take different amounts of time to execute
```python
from multiprogressbars.example import run_example
run_example()
```

Second example where some tasks will raise an exception
```python
from multiprogressbars.example import run_example_exceptions
run_example_exceptions()
```


#### Initialising the main Multibar task handling object

```python
from multiprogressbars.multibar import Multibar

# create the Multibar object - can add tasks and get results through this
mbar = Multibar()
# tasks are created using the following example arguments - they are not run immediately
mbar.add_task(
    func=target_func,
    func_args=(target_func_arg1, target_func_arg2, ...),  # optional
    func_kwargs={'target_func_kwarg1_key': target_func_kwarg1_value}  # optional
)

# processing begins by calling 'begin_processing()', or 'get()'
# both are blocking until the tasks are finished or the app is quit.
# this quits all processes and returns the results that have already finished
results_dict, failed_tasks_dict = mbar.get()
```

#### Adding the BarUpdater object to the target function for callbacks: wrapping

```python
from multiprogressbars.bar_updater import BarUpdater

def target_func(
        target_func_arg1,
        target_func_arg2,
        target_func_kwarg1_key=target_func_kwarg1_value,
        pbar: BarUpdater = None):
    
    # wrap an iterator in the BarUpdater object to automatically yield and update the internally designated progress bar
    for _ in pbar(iterator, desc=description_str, total=len(iterator)):
        # execute code
    return results
```

#### Adding the BarUpdater object to the target function for callbacks: manually calling

```python
from multiprogressbars.bar_updater import BarUpdater

def target_func(
        target_func_arg1,
        target_func_arg2,
        target_func_kwarg1_key=target_func_kwarg1_value,
        pbar: BarUpdater = None):
    
    # wrap an iterator in the BarUpdater object to automatically yield and update the internally designated progress bar
    pbar.update_name(description_string)
    pbar.update_total(total)
    while True:
        # execute code
        # more complicated user progress calculation
        pbar.update_value(new_total_progress)
        # break condition
    return results
```

## Contributing
Please make any pull requests that would add or fix functionality. This is not intended for major use.

## License
[GNU GPL](https://choosealicense.com/licenses/gpl-3.0/#)