.PHONY: install-local test-cli

install-local:
	python -m pip install -e .

test-cli:
	multi-agent-tcp --help
	multi-agent-tcp doctor --json
