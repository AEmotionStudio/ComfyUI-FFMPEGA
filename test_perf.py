import timeit

setup = """
from core.executor.command_builder import Filter, FilterChain

fc = FilterChain()
fc.add_filter("scale", {"w": 1280, "h": 720})
fc.add_filter("fps", {"": 30})
fc.add_filter("eq", {"brightness": 0.1, "contrast": 1.1})
"""

stmt = "fc.to_string()"

print(timeit.timeit(stmt, setup=setup, number=10000))
