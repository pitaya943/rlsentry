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
# Pre-pull the lab images so sessions start fast (cached when the script finishes in ~5 min).
docker info >/dev/null 2>&1 && (cd /tmp && supabase init --force >/dev/null 2>&1 || true)
