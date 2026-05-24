// Single-translation-unit storage for the logSink ring (so the namespace
// state in logSink.h has exactly one definition). Header is otherwise
// header-only.

#include "logSink.h"

namespace logsink {

Slot         g_lines[RING_LINE_COUNT];
uint16_t     g_head = 0;
uint16_t     g_count = 0;
bool         g_truncationWarned = false;
portMUX_TYPE g_mux = portMUX_INITIALIZER_UNLOCKED;

}  // namespace logsink
