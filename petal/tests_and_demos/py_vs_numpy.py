# -*- coding: utf-8 -*-
"""
Some comparative timings of common numpy vs python list comprehension operations.
I think these are useful and interesting for when we optimize petal code, such as collision detections.
Joe
"""

import timeit
import numpy as np

array_lengths = [1,5,10,25,50,100,250,500,1000,5000,10000]
n_runs = 100

np_dot_timings = []
py_dot_timings = []

np_max_timings = []
py_max_timings = []

np_where_timings = []
py_where_timings = []

np_cond_timings = []
py_cond_timings = []

for L in array_lengths:
    nparray1 = np.random.rand(L)
    nparray2 = np.random.rand(L)
    pylist1 = nparray1.tolist()
    pylist2 = nparray2.tolist()

    np_dot_timer = timeit.Timer(lambda: nparray1 * nparray2)
    py_dot_timer = timeit.Timer(lambda: [pylist1[i]*pylist2[i] for i in range(len(pylist1))])
    np_dot_timings.append(np_dot_timer.timeit(number=n_runs))
    py_dot_timings.append(py_dot_timer.timeit(number=n_runs))

    np_max_timer = timeit.Timer(lambda: np.max(nparray1))
    py_max_timer = timeit.Timer(lambda: max(pylist1))
    np_max_timings.append(np_max_timer.timeit(number=n_runs))
    py_max_timings.append(py_max_timer.timeit(number=n_runs))
    
    search_val = pylist1[int(len(pylist1)/2)]
    np_where_timer = timeit.Timer(lambda: np.where(nparray1 == search_val))
    py_where_timer = timeit.Timer(lambda: [pylist1.index(x) for x in pylist1 if x == search_val])
    np_where_timings.append(np_where_timer.timeit(number=n_runs))
    py_where_timings.append(py_where_timer.timeit(number=n_runs))
    
    np_cond_timer = timeit.Timer(lambda: nparray1[nparray1 > search_val])
    py_cond_timer = timeit.Timer(lambda: [x for x in pylist1 if x > search_val])
    np_cond_timings.append(np_where_timer.timeit(number=n_runs))
    py_cond_timings.append(py_where_timer.timeit(number=n_runs))
    
print('number of repeated timing runs = ',n_runs)
print('all values in microseconds')
print('array length    np dot    py dot    np_max    py_max    np_where    py_where    np_cond    py_cond')

def fmt(value,n_spaces):
    code = format(n_spaces) + '.1f'
    return format(value*1000000,code)

for i in range(len(array_lengths)):
    print(format(array_lengths[i],'12d'),fmt(np_dot_timings[i],9),fmt(py_dot_timings[i],9), \
                                         fmt(np_max_timings[i],9),fmt(py_max_timings[i],9), \
                                         fmt(np_where_timings[i],11),fmt(py_where_timings[i],11), \
                                         fmt(np_cond_timings[i],10),fmt(py_cond_timings[i],10))
