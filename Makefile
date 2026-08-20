# Portable Makefile: GNU make on Linux, macOS, and Windows.
#
# On Windows make usually runs without any shell (no sh.exe in PATH), so it
# hands each recipe line straight to CreateProcess. Every line below is
# therefore a single executable invocation -- no `;`, `&&`, pipes, globs or
# redirections -- and paths use forward slashes, which every platform accepts.
# Whatever has to be scripted is done by Python, which this project has by
# definition, rather than by `rm`, `test` or `rmdir`.

VENV = .venv

ifeq ($(OS),Windows_NT)
    SYSTEM_PYTHON = python
    PYTHON = $(VENV)/Scripts/python.exe
else
    SYSTEM_PYTHON = python3
    PYTHON = $(VENV)/bin/python
endif

PIP = $(PYTHON) -m pip

# Recursive delete, without rm -rf.
REMOVE = $(SYSTEM_PYTHON) -c "import shutil, sys; [shutil.rmtree(p, ignore_errors=True) for p in sys.argv[1:]]"
REMOVE_PYCACHE = $(SYSTEM_PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__') if '$(VENV)' not in p.parts]"

# Delete plain files, without rm -f.
REMOVE_FILES = $(SYSTEM_PYTHON) -c "import pathlib, sys; [pathlib.Path(p).unlink(missing_ok=True) for p in sys.argv[1:]]"

.PHONY: all venv upgrade_pip install run test viz clean fclean re

# Messages stay free of quotes and of shell metacharacters such as > or ( ),
# so that they read the same through sh and through make's own echo.
all: install
	@echo Project ready.
	@echo Start the game with: make run
	@echo See how the engine thinks: make viz
	@echo Or directly: $(PYTHON) gomoku.py

# The interpreter itself is the proof that the venv exists: make only builds
# it when the file is missing, no `test -d` needed.
$(PYTHON):
	$(SYSTEM_PYTHON) -m venv $(VENV)

venv: $(PYTHON)

upgrade_pip: $(PYTHON)
	@$(PIP) install --upgrade pip

install: upgrade_pip
	@$(PIP) install -r requirements.txt

run: $(PYTHON)
	@$(PYTHON) gomoku.py

test: $(PYTHON)
	@$(PYTHON) -m pytest

# Opens the studio: build a position, take it apart five ways. ARGS passes
# through, so `make viz ARGS=--explore` and `ARGS=--panels` reach the other
# two views.
viz: $(PYTHON)
	@$(PYTHON) -m viz $(ARGS)

clean:
	@$(REMOVE_PYCACHE)
	@$(REMOVE) .pytest_cache

fclean: clean
	@$(REMOVE) $(VENV)

# Two sub-makes: `all` must look at the filesystem *after* fclean emptied it.
re:
	@$(MAKE) fclean
	@$(MAKE) all
