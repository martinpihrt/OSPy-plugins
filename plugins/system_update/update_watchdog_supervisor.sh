#!/bin/sh

# Keep the Python watchdog alive across legacy OSPy SysV restarts.  Old init
# scripts performed a broad /usr/bin/python3 cleanup, so this shell remains the
# systemd unit's main process and relaunches only a helper killed by a signal.

PYTHON="$1"
HELPER="$2"
shift 2

STATE=""
PREVIOUS=""
for ARGUMENT in "$@"; do
    if [ "$PREVIOUS" = "--state" ]; then
        STATE="$ARGUMENT"
        break
    fi
    PREVIOUS="$ARGUMENT"
done

if [ -z "$PYTHON" ] || [ -z "$HELPER" ] || [ -z "$STATE" ]; then
    exit 2
fi

while :; do
    "$PYTHON" "$HELPER" "$@"
    STATUS=$?

    case "$STATUS" in
        0|2|4)
            exit "$STATUS"
            ;;
        137|143)
            # SIGKILL/SIGTERM may come from the legacy broad Python cleanup.
            # A pending state means the watchdog still owns recovery work.
            if [ ! -f "$STATE" ]; then
                exit "$STATUS"
            fi
            sleep 1
            ;;
        *)
            exit "$STATUS"
            ;;
    esac
done
