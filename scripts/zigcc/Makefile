.PHONY: build test clean

build: bin/zigcc

# always build for linux and the machine's native architecture
bin/zigcc: *.go go.mod
	GOOS=linux go build -o $@ -ldflags="-s -w" -v ./...

test:
	go test -v ./...

fmt:
	go fmt ./...

vet:
	go vet ./...

clean:
	go clean
	rm -f bin/*
	rmdir bin
