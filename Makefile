### Makefile - Project Development Commands

# Declare targets that are not actual files
.PHONY: install lint format test


# 1. Install Development Dependencies | Usage: make install
install:
	pip install -r requirements-dev.txt


# 2. Check Code Quality and Formatting | Usage: make lint
lint:
	ruff check .
	ruff format --check .


# 3. Automatically Fix and Format Code | Usage: make format
format:
	ruff check --fix .
	ruff format .


# 4. Run Tests | Usage: make test
test:
	pytest -q