#pragma once
// debug/casRetry.h — TASK-704: single source of truth for the TASK-426 A/B
// cookie value shared by boot.cpp, cmdSet.cpp and armedInjectors.h.
//
// The cookie guards an RTC_NOINIT_ATTR word (g_casRetryCookie) that must
// survive a SOFTWARE reset — see boot.cpp's casRetryDisabled() for the full
// "why". SERIAL_DEBUG-only, same convention as every other file under
// debug/. Deliberately just this one constant, no other decls — boot.cpp's
// own header comment says it wants to resolve standalone with the fewest,
// lightest #includes it needs, so this stays a single-line header rather
// than pulling boot.cpp into armedInjectors.h's much heavier include set.
#ifdef SERIAL_DEBUG

static constexpr uint32_t kCasRetryCookie = 0x426AB1FEu;

#endif  // SERIAL_DEBUG
