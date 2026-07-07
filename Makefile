PYTHON ?= python3

.PHONY: test love ftball

test:
	$(PYTHON) -m unittest discover -s tests -v

love:
	$(PYTHON) dbasic.py library/LOVE

ftball:
	$(PYTHON) dbasic.py library/FTBALL
