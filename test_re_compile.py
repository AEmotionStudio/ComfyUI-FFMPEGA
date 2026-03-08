import re
import timeit

def f1(s):
    return re.sub(r'concat=n=(\d+):v=1:a=1', r'concat=n=\1:v=1:a=0', s)

_CONCAT_A1_RE = re.compile(r'concat=n=(\d+):v=1:a=1')
def f2(s):
    return _CONCAT_A1_RE.sub(r'concat=n=\1:v=1:a=0', s)

setup = "from __main__ import f1, f2\ns='[0:v] [1:v] concat=n=2:v=1:a=1'"

print("inline re.sub:", timeit.timeit("f1(s)", setup=setup, number=100000))
print("compiled re.sub:", timeit.timeit("f2(s)", setup=setup, number=100000))
