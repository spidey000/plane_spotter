#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-app}"
APP_GROUP="${APP_GROUP:-app}"
LOG_DIR="${LOG_DIR:-/app/logs}"
DEFAULT_CMD=("python" "main.py")

log(){ printf '[entrypoint] %s\n' "$*"; }

require_user(){
  if ! id -u "$APP_USER" >/dev/null 2>&1; then
    log "User '$APP_USER' is missing" >&2
    exit 1
  fi
}

ensure_log_dir(){
  if [ ! -d "$LOG_DIR" ]; then
    log "Creating missing log directory at $LOG_DIR"
    mkdir -p "$LOG_DIR"
  else
    log "Log directory $LOG_DIR already exists"
  fi
}

ensure_permissions(){
  local app_uid app_gid current_owner
  app_uid="$(id -u "$APP_USER")"
  app_gid="$(id -g "$APP_USER")"
  current_owner="$(stat -c '%u:%g' "$LOG_DIR")"

  if [ "$current_owner" != "${app_uid}:${app_gid}" ]; then
    log "Adjusting ownership of $LOG_DIR to ${APP_USER}:${APP_GROUP}"
    chown -R "$APP_USER:$APP_GROUP" "$LOG_DIR"
  else
    log "Ownership for $LOG_DIR already matches ${APP_USER}:${APP_GROUP}"
  fi

  if gosu "$APP_USER" test -w "$LOG_DIR"; then
    log "Verified that ${APP_USER} can write to $LOG_DIR"
  else
    log "${APP_USER} still cannot write to $LOG_DIR after adjustments" >&2
    exit 1
  fi
}

main(){
  require_user
  ensure_log_dir
  ensure_permissions

  if [ "$#" -eq 0 ]; then
    set -- "${DEFAULT_CMD[@]}"
  fi

  log "Starting application as ${APP_USER}: $*"
  exec gosu "$APP_USER" "$@"
}

main "$@"
