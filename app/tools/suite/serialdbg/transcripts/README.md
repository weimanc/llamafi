# serialdbg transcripts — fixtures for `gate/check_can_go_red.py` (TASK-671)

One `<id>.json` per registered test id, written by the runner's `--record DIR` flag
(`RECORD_DIR=app/tools/suite/serialdbg/transcripts ./run/test`), in the format
`lib/replay.py` defines (`TRANSCRIPT_SCHEMA`). Redacted at record time.

A transcript here is a **healthy path for the body**, used to ask whether the body can be MADE to
go red by poisoning it (`lib/canfail.py`). It is *not* a statement about the current firmware —
the ELF stamp is recorded but the can-go-red gate does not require it to match the build, and
says why in its docstring. The falsification job (TASK-641/642/643) does require it.

Recording costs a board reset. Check `./run/monitor-read` for a live TASK-557 window first.
