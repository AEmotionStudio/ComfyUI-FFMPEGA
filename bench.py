import functools

@functools.lru_cache(maxsize=None)
def foo(): return 1

@functools.cache
def bar(): return 1

import timeit
print("lru_cache:", timeit.timeit("foo()", setup="from __main__ import foo", number=10000000))
print("cache:", timeit.timeit("bar()", setup="from __main__ import bar", number=10000000))
