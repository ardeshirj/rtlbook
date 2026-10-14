# Common commands. `make` alone lists them. Everything runs in Docker (nothing to install).

.DEFAULT_GOAL := help
.PHONY: help build core core-amd64 test bench bump tag

help: ## List the commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-z0-9-]+:.*## / {printf "  make %-11s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## The image, rtlbook:dev
	docker build -f docker/Dockerfile -t rtlbook:dev .

core: ## The same image as rtlbook:core, the name other projects build on
	docker build -f docker/Dockerfile --target core -t rtlbook:core .

core-amd64: ## The image for linux/amd64 hosts, rtlbook:core-amd64 (emulated, so slower, on Apple Silicon)
	docker buildx build --platform linux/amd64 -f docker/Dockerfile --target core -t rtlbook:core-amd64 --load .

test: ## Run the tests in rtlbook:dev (tests that need PDFs in input/ run when they are there)
	docker run --rm -v "$$PWD":/app -w /app --entrypoint python rtlbook:dev -m pytest -q -p no:cacheprovider tests

bench: ## The scorecard (ROADMAP.md), added to bench/results.jsonl: make bench SET=path/to/set [READER=tesseract]
	docker run --rm -v "$$PWD":/app -w /app $(if $(SET),-v "$(abspath $(SET))":/sets/$(notdir $(abspath $(SET))):ro) \
		--entrypoint rtlbook rtlbook:dev bench --reader $(or $(READER),tesseract) \
		$(if $(SET),--set /sets/$(notdir $(abspath $(SET)))) --save bench/results.jsonl \
		--image-mb $$(docker image inspect rtlbook:core --format '{{.Size}}' | awk '{print int($$1 / 1e6)}') \
		--commit $$(git describe --always --dirty)

bump: ## Set the version in pyproject.toml, __init__.py and uv.lock: make bump V=0.6.0
	tools/release bump $(V)

tag: ## Tag the committed version on this commit as vX.Y.Z (optional NOTE="…"); push it yourself
	tools/release tag "$(NOTE)"
