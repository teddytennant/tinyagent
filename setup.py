from setuptools import setup

setup(name="tinyagent", version="0.1.0", description="a coding agent in 1000 lines", license="MIT",
      packages=["tinyagent"], python_requires=">=3.10", install_requires=[],
      extras_require={"testing": ["pytest", "ruff"]},
      entry_points={"console_scripts": ["agent=tinyagent.main:cli"]})
