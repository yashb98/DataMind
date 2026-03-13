FROM golang:1.22-alpine AS builder
WORKDIR /build
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /server ./cmd/server

FROM alpine:3.20
RUN addgroup -S datamind && adduser -S -G datamind datamind
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /server /app/server
RUN chown -R datamind:datamind /app
USER datamind
EXPOSE 8100
HEALTHCHECK --interval=20s --timeout=10s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8100/health/liveness || exit 1
CMD ["/app/server"]
