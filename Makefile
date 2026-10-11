# Gold Phase Monitor — top-level build (paper simulation only)
# Layout: Python app at repo root (Streamlit Cloud compatible), fastpath-go/ (Go daemon), native/ (Rust hot loop).
PY ?= python

.PHONY: all test py-test go-test go-build native native-test bench clean colony
all: test

test: py-test go-test

py-test:
	$(PY) -m pytest -q

go-test:
	cd fastpath-go && go vet ./... && go test -race -count=1 ./...

go-build:
	cd fastpath-go && CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o ../dist/fastpath .

native:            ## optional: build + install the Rust arena loop into the active venv
	cd native/gpm_native && maturin develop --release

native-test: native
	$(PY) -m pytest -q tests/test_native.py

bench:
	cd fastpath-go && go test -run xxx -bench . -benchmem
	PYTHONPATH=. $(PY) native/bench.py

clean:
	rm -rf dist native/gpm_native/target

colony:            ## local paper colony: 8 instances, cap 21
	$(PY) -m core.colony run --n 8 --max 21 --checks 6 --every 30
