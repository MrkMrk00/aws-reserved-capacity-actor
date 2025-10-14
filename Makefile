PY_EXE ?= python3
VENV_PATH := venv

all: install

lint: venv
	$(VENV_PATH)/bin/python ./lint.py

venv:
	$(PY_EXE) -m venv $(VENV_PATH)

clean:
	rm -rf \
		storage/key_value_stores/**/*	\
		storage/datasets/**/* 			\
		storage/request_queues/**/* 	\


clean-build: clean
	rm -rf build/ $(VENV_PATH)

install: venv
	$(VENV_PATH)/bin/pip install ".[dev]"

.PHONY: install clean clean-build

