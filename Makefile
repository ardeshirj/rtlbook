# Common commands. `make` alone lists them. Everything runs in Docker (nothing to install).

.DEFAULT_GOAL := help
.PHONY: help build core core-amd64 test

help: ## List the commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-z0-9-]+:.*## / {printf "  make %-11s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## The full image, rtlbook:dev (EPUB and Kindle KFX)
	docker build -f docker/Dockerfile -t rtlbook:dev .

core: ## The slim image, rtlbook:core: EPUB only, without calibre (about 680 MB smaller)
	docker build -f docker/Dockerfile --target core -t rtlbook:core .

core-amd64: ## The slim image for linux/amd64 hosts, rtlbook:core-amd64 (emulated, so slower, on Apple Silicon)
	docker buildx build --platform linux/amd64 -f docker/Dockerfile --target core -t rtlbook:core-amd64 --load .

test: ## Run the tests in rtlbook:dev (tests that need PDFs in input/ run when they are there)
	docker run --rm -v "$$PWD":/app -w /app --entrypoint python rtlbook:dev -m pytest -q -p no:cacheprovider tests
