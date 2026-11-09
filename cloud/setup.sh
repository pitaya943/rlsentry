#!/usr/bin/env bash
# Setup script for the claude.ai/code cloud environment (paste into the environment's
# "Setup script" field). Installs what the harness and the Supabase lab need.
# Shared by every session (rlsentry, rlsentry-arena): it installs tools only and never
# fetches any repository's source. No step may fail the environment (warnings only).
set -uo pipefail

SUPABASE_VERSION="3.0.0"   # the version the lab was measured with (MS7 approval note 3)

pip install --quiet pytest pyyaml ruff mypy mutmut || echo "pip: install failed (PyPI error); install by hand later"

command -v ssh-keygen >/dev/null || (sudo apt-get update -q && sudo apt-get install -y -q openssh-client) \
  || echo "ssh-keygen: install failed"

if [ "$(supabase --version 2>/dev/null)" != "${SUPABASE_VERSION}" ]; then
  ARCH="$(dpkg --print-architecture)"
  if curl -fL --retry 5 --retry-delay 5 --retry-all-errors -o /tmp/supabase.tar.gz \
       "https://github.com/supabase/cli/releases/download/v${SUPABASE_VERSION}/supabase_linux_${ARCH}.tar.gz"; then
    sudo tar -xzf /tmp/supabase.tar.gz -C /usr/local/bin supabase || echo "supabase: extract failed"
    rm -f /tmp/supabase.tar.gz
  else
    echo "supabase: download failed (GitHub error); install v${SUPABASE_VERSION} by hand later"
  fi
fi
supabase --version || echo "supabase: NOT installed"

# Docker: the daemon is not started automatically in cloud containers (Stage 0 finding).
if ! docker info >/dev/null 2>&1; then
  (sudo -n dockerd >/tmp/dockerd.log 2>&1 &) || true
  for _ in $(seq 1 20); do docker info >/dev/null 2>&1 && break; sleep 1; done
fi
if docker info >/dev/null 2>&1; then echo "docker: running"; else echo "docker: NOT running (see /tmp/dockerd.log)"; fi

exit 0   # never fail the environment because of optional warm-up steps
