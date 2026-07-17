VENV=.venv
PYTHON=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

.PHONY: all venv upgrade_pip install run clean fclean re

all: venv upgrade_pip install
	@echo ""
	@echo "✅ Project ready."
	@echo "-->   make run        (or) source .venv/bin/activate && python gomoku.py"

run: all
	@$(PYTHON) gomoku.py

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)

upgrade_pip:
	@$(PIP) install --upgrade pip

install:
	@$(PIP) install -r requirements.txt

clean:
	@rm -rf __pycache__ */__pycache__ .pytest_cache

fclean: clean
	@rm -rf $(VENV)

re: fclean all