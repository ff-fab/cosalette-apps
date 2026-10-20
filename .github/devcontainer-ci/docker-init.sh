#!/bin/sh
# Bind-mounted over the docker-in-docker feature's entrypoint in CI (cap-1a0u):
# no CI step needs a Docker daemon inside the devcontainer, and starting one
# intermittently hung `devcontainer up` after "Setting dockerd Azure DNS.".
exec "$@"
