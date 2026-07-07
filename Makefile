PYTHON ?= python3

.PHONY: test love ftball fork

test:
	$(PYTHON) -m unittest discover -s tests -v

fork:
	$(PYTHON) tools/make_fork.py

love:
	$(PYTHON) dbasic.py library/LOVE

ftball:
	$(PYTHON) dbasic.py library/FTBALL
