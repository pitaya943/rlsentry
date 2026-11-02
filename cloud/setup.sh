#!/usr/bin/env bash
# Setup script for the claude.ai/code cloud environment (paste into the environment's
# "Setup script" field). Installs what the harness and the Supabase lab need.
set -euo pipefail
pip install --quiet pytest pyyaml ruff mypy mutmut
command -v ssh-keygen >/dev/null || (sudo apt-get update -q && sudo apt-get install -y -q openssh-client)
if ! command -v supabase >/dev/null; then
  ARCH="$(dpkg --print-architecture)"
  # Pin a version for reproducibility: replace latest/download with download/v<version>.
  curl -fsSL "https://github.com/supabase/cli/releases/latest/download/supabase_linux_${ARCH}.tar.gz" \
    | sudo tar -xz -C /usr/local/bin supabase
fi
supabase --version
# Docker: the daemon is not started automatically in cloud containers (Stage 0 finding).
if ! docker info >/dev/null 2>&1; then
  (sudo -n dockerd >/tmp/dockerd.log 2>&1 &) || true
  for _ in $(seq 1 20); do docker info >/dev/null 2>&1 && break; sleep 1; done
fi
if docker info >/dev/null 2>&1; then echo "docker: running"; else echo "docker: NOT running (see /tmp/dockerd.log)"; fi
exit 0   # never fail the environment because of optional warm-up steps
