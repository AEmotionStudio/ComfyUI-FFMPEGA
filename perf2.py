import timeit

setup = """
from skills.registry import SkillRegistry
from skills.category.temporal import register_skills as temporal_reg
from skills.category.spatial import register_skills as spatial_reg
reg = SkillRegistry()
temporal_reg(reg)
spatial_reg(reg)
"""

stmt = "reg.search('scale crop test filter resize')"

print(timeit.timeit(stmt, setup=setup, number=10000))
