### Makefile - Project Development Commands

# Declare targets that are not actual files
.PHONY: install lint format test check-sources fetch-sources


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


# 5. Validate Source Registry and Check Downloaded Files | Usage: make check-sources
check-sources:
	PYTHONPATH=src python -m app.ingest.sources

# 6. Download Approved Sources | Usage: make fetch-sources
fetch-sources:
	PYTHONPATH=src python scripts/fetch_sources.py
build-documents:
	PYTHONPATH=src python -m app.ingest.documents

build-chunks:
	PYTHONPATH=src python -m app.indexing.chunker

embed-chunks:
	PYTHONPATH=src python -m app.indexing.embeddings

build-vector-index:
	PYTHONPATH=src python -m app.indexing.vector_index
