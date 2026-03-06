import timeit

setup = """
from core.executor.command_builder import Filter, FilterChain

fc = FilterChain()
for i in range(10):
    fc.add_filter("scale", {"w": 1280, "h": 720, "x": "10+i"})
"""

stmt = "fc.to_string()"

print(timeit.timeit(stmt, setup=setup, number=10000))
