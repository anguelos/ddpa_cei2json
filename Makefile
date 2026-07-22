.PHONY: clean test doc build

clean:
	rm -rf build dist src/*.egg-info .pytest_cache .coverage docs/_build tmp
	find . -name __pycache__ -type d -exec rm -rf {} +

test:
	pytest test/unit_coverage test/bugfixing test/corner_cases

doc:
	sphinx-build -b html docs docs/_build/html

build:
	python -m build
