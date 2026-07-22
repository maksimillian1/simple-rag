FROM --platform=$BUILDPLATFORM golang:1.25-alpine AS builder
ARG TARGETOS
ARG TARGETARCH
WORKDIR /app
COPY go.mod go.sum ./
COPY mocks ./mocks
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH:-amd64} go build -o api main.go

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/api .
EXPOSE 8080
CMD ["./api"]
