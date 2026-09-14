#!/bin/bash
# tests/fixture_backend.sh
# Builds and starts a backend fixture for client model checks.
# Sign-in is always required, so this never creates accounts.
# Instead it copies users and API tokens from an existing set-up database.
# Usage: tests/fixture_backend.sh
#        DEN_URL=http://127.0.0.1:8688 DEN_API_TOKEN="$(cat ~/the-den-dev/admin-token.txt)" tests/run_all.sh

# Default settings (can be overridden by environment)
THE_DEN_REPO="${THE_DEN_REPO:-$(cd "$(dirname "$0")/../.." && pwd)/the-den}"
SOURCE_DB="${SOURCE_DB:-$HOME/the-den-dev/den.db}"
DEN_TOKEN_FILE="${DEN_TOKEN_FILE:-$HOME/the-den-dev/admin-token.txt}"
FIXTURE_DIR="${FIXTURE_DIR:-$HOME/the-den-client-fixture}"
PY="${PY:-$HOME/.venvs/the-den/bin/python}"
PORT="${PORT:-8688}"
TORRENT_PORT="${TORRENT_PORT:-6894}"
TVMAZE_PORT="${TVMAZE_PORT:-8085}"
TORZNAB_PORT="${TORZNAB_PORT:-8082}"
# SWARM_PORT is fixed at 8083; tests/local_swarm.py and tests/mock_torznab.py hardcode it
SWARM_PORT=8083

set -euo pipefail

die() {
    echo "fixture_backend: $*" >&2
    exit 1
}

# Preflight checks
[[ -f "$THE_DEN_REPO/app/main.py" ]] || die "missing $THE_DEN_REPO/app/main.py"
[[ -f "$SOURCE_DB" ]] || die "missing $SOURCE_DB"
[[ -s "$DEN_TOKEN_FILE" ]] || die "missing or empty $DEN_TOKEN_FILE"
[[ -x "$PY" ]] || die "$PY is not executable"
command -v sqlite3 >/dev/null 2>&1 || die "sqlite3 not on PATH"
command -v curl >/dev/null 2>&1 || die "curl not on PATH"
command -v jq >/dev/null 2>&1 || die "jq not on PATH"
[[ -n "$FIXTURE_DIR" && "$FIXTURE_DIR" != "/" && "$FIXTURE_DIR" != "$HOME" ]] || die "FIXTURE_DIR must be set to a non-empty, non-root directory"

# Read the token once (never echoed)
TOKEN="$(tr -d '\r\n' < "$DEN_TOKEN_FILE")"

# Stop any previous runs, ignoring failures
pkill -f "uvicorn app.main:app --host 127.0.0.1 --port $PORT" 2>/dev/null || true
pkill -f "uvicorn tests.mock_tvmaze:app --host 127.0.0.1 --port $TVMAZE_PORT" 2>/dev/null || true
pkill -f "uvicorn tests.mock_torznab:app --host 127.0.0.1 --port $TORZNAB_PORT" 2>/dev/null || true
sleep 1

# Refuse to run while something else answers on a port this script needs: the library
# clean-up below would otherwise delete that server's movies, series and indexers.
for p in "$PORT" "$TVMAZE_PORT" "$TORZNAB_PORT"; do
    if curl -s -o /dev/null -m 2 "http://127.0.0.1:$p/"; then
        die "port $p is already in use by another process; stop it or set a different port"
    fi
done

# Start clean, but only ever delete a folder this script created (it leaves a marker file)
MARKER="$FIXTURE_DIR/.the-den-client-fixture"
if [[ -e "$FIXTURE_DIR" ]]; then
    [[ -f "$MARKER" ]] || die "$FIXTURE_DIR exists but was not created by this script; set FIXTURE_DIR to a new folder"
    rm -rf "$FIXTURE_DIR"
fi
mkdir -p "$FIXTURE_DIR/state" "$FIXTURE_DIR/downloads" "$FIXTURE_DIR/movies" "$FIXTURE_DIR/tv" "$FIXTURE_DIR/swarm"
touch "$MARKER"

# Copy the database consistently even while its server runs
sqlite3 "$SOURCE_DB" ".backup '$FIXTURE_DIR/den.db'"

# Point settings at the fixture folders (stored values win over environment variables)
sqlite3 "$FIXTURE_DIR/den.db" "UPDATE settings SET movies_root='$FIXTURE_DIR/movies', tv_root='$FIXTURE_DIR/tv', downloads_root='$FIXTURE_DIR/downloads', torrent_port=NULL;"

# Helper to start a background service
start_bg() {
    local name="$1" port="$2"
    shift 2
    (cd "$THE_DEN_REPO" && setsid nohup "$PY" -m uvicorn "$@" --host 127.0.0.1 --port "$port" \
        > "$FIXTURE_DIR/$name.log" 2>&1 < /dev/null &)
    local i
    for i in $(seq 1 30); do
        curl -s -o /dev/null -m 2 "http://127.0.0.1:$port/" && return 0
        sleep 1
    done
    tail -n 15 "$FIXTURE_DIR/$name.log" >&2
    die "$name did not start on port $port"
}

# Start mock services
start_bg mock_tvmaze "$TVMAZE_PORT" tests.mock_tvmaze:app
start_bg mock_torznab "$TORZNAB_PORT" tests.mock_torznab:app

# Check if swarm is already running, otherwise start it
if ! curl -s -o /dev/null -m 2 "http://127.0.0.1:$SWARM_PORT/" >/dev/null 2>&1; then
    export SWARM_DIR="$FIXTURE_DIR/swarm"
    start_bg swarm "$SWARM_PORT" tests.local_swarm:app
else
    echo "reusing running swarm on port $SWARM_PORT"
fi

# Export environment for the backend
export DATABASE_URL="sqlite:///$FIXTURE_DIR/den.db"
export STATE_DIR="$FIXTURE_DIR/state"
export DOWNLOADS_ROOT="$FIXTURE_DIR/downloads"
export MOVIES_ROOT="$FIXTURE_DIR/movies"
export TV_ROOT="$FIXTURE_DIR/tv"
export TORRENT_PORT
export WEB_HOST=127.0.0.1
export WEB_PORT="$PORT"
export TVMAZE_BASE_URL="http://127.0.0.1:$TVMAZE_PORT"

# Run migrations from inside the den repo
(cd "$THE_DEN_REPO" && "$PY" -m alembic upgrade head) >> "$FIXTURE_DIR/alembic.log" 2>&1 || { tail -n 15 "$FIXTURE_DIR/alembic.log" >&2; die "database migration failed"; }

# Start the backend
start_bg backend "$PORT" app.main:app

# Wait for the backend's health check
for i in $(seq 1 30); do
    curl -fs -m 2 "http://127.0.0.1:$PORT/health" > /dev/null && break
    [[ "$i" == "30" ]] && { tail -n 30 "$FIXTURE_DIR/backend.log" >&2; die "backend never became healthy"; }
    sleep 1
done

# API helper: curl with the token header; the path is the argument that starts with /
api() {
    local a path="" args=()
    for a in "$@"; do
        if [[ -z "$path" && "$a" == /* ]]; then path="$a"; else args+=("$a"); fi
    done
    curl -fsS -m 60 -H "X-Api-Key: $TOKEN" -H "Content-Type: application/json" "${args[@]}" "http://127.0.0.1:$PORT$path"
}

# Check the token is accepted
api /api/auth/me > /dev/null || die "the token in $DEN_TOKEN_FILE was rejected by the copied database"

# Clear the library through the API so ids restart at 1
for id in $(api /movies | jq -r '.[].id'); do
    api -X DELETE "/movies/$id" > /dev/null
done
for id in $(api /series | jq -r '.[].id'); do
    api -X DELETE "/series/$id" > /dev/null
done
for id in $(api /indexers | jq -r '.[].id'); do
    api -X DELETE "/indexers/$id" > /dev/null
done

# Seed the library, checking each result with jq
api -X POST /indexers -d '{"name":"Mock Indexer","url":"http://127.0.0.1:'"$TORZNAB_PORT"'/api","protocol":"torznab","implementation":"torznab"}' > /dev/null
movie_id=$(api -X POST /movies -d '{"tmdb_id":27205,"title":"Inception","year":2010}' | jq -r '.id')
[[ "$movie_id" == "1" ]] || die "the new movie got id $movie_id, not 1; SOURCE_DB has other library rows, so use a database with an empty library"
series_id=$(api -X POST /series -d '{"tvmaze_id":169,"title":"Breaking Bad","year":2008}' | jq -r '.id')
[[ "$series_id" == "1" ]] || die "the new series got id $series_id, not 1; SOURCE_DB has other library rows, so use a database with an empty library"

# Check episodes count
count=$(api /series/1/episodes | jq -r '.|length')
[[ "$count" == "4" ]] || die "series 1 has $count episodes, expected 4"

# Check candidates exist
candidates=$(api /movies/1/candidates | jq -r '.|length')
[[ "$candidates" -ge 1 ]] || die "no release candidates for movie 1; check $FIXTURE_DIR/mock_torznab.log"

# Finish by printing status (without the token)
echo "Fixture backend ready on http://127.0.0.1:$PORT"
echo "  movie 1: Inception, with candidates from the mock indexer"
echo "  series 1: Breaking Bad, 4 episodes across 2 seasons"
echo "  logs and data: $FIXTURE_DIR"
echo "Run the client checks with:"
echo "  DEN_URL=http://127.0.0.1:$PORT DEN_API_TOKEN=\"\$(cat $DEN_TOKEN_FILE)\" tests/run_all.sh"
