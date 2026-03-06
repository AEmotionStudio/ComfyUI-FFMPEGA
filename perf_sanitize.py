import timeit

setup = """
from core.sanitize import sanitize_text_param
"""

stmt = "sanitize_text_param(\"test:string,with=symbols\")"

print(timeit.timeit(stmt, setup=setup, number=100000))
