import functools
import re

c1 = re.compile(r"\[0:v\]")
def f1(s):
    return c1.sub("[_pre]", s)

def f2(s):
    return s.replace("[0:v]", "[_pre]")

import timeit
s = "[0:v]eq=brightness=0.1:contrast=1.2[_pre];[0:v]scale=1920:1080"
print("re.sub:", timeit.timeit("f1(s)", setup="from __main__ import f1, s", number=1000000))
print("replace:", timeit.timeit("f2(s)", setup="from __main__ import f2, s", number=1000000))
