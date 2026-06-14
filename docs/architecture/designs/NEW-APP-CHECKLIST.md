# New-App Integration Checklist

> Owner: Developer / Architect  
> Status: active  
> Date: 2026-06-14  
> Ref: BP-036 (LL-076) — cross-cutting shell integrations must be audited at every new-app registration

---

## When to use

Run through this checklist every time a new `AppId` row is added to `appRegistry.h`.  
A failing item is a silent compile-time success with a runtime bug — nothing breaks visibly until a test
or user interaction reveals it.

---

## Checklist

### 1. `hasPendingAsync()` — shell busy indicator (touch-004)

**Required if**: the app enqueues any async work from `handleInput()` (network fetch, task signal, timer arm).  
**Default**: `App::hasPendingAsync()` returns `false`. A missing override compiles cleanly and silently
blocks the shell busy indicator.

- [ ] Does this app's `handleInput()` trigger async work? If yes → override `hasPendingAsync() const override { return ...; }`.
- [ ] Verify the field is set to `true` from the moment async work is enqueued until it completes.
- [ ] Add a `cross_feature_matrix.yaml` entry pairing the new app feature with `touch-004`.

Precedents: `StockApp::_pendingAsync`, `TeletextApp::_pendingFetch`, `SettingsApp` (WiFi scan).

---

### 2. `tlsYield()` / `tlsResume()` — TLS heap anti-contention (BP-031)

**Required if**: the app spawns or reuses a `dataTask` HTTPS fetcher.  
**Symptom of omission**: intermittent HTTPS failures under concurrent Spotify task socket calls (same heap).

- [ ] Does this app make HTTPS calls? If yes → call `tlsYield()` before the fetch and `tlsResume()` after.
- [ ] The yield/resume pair must bracket every HTTPS call site, not just the first.
- [ ] Add a T-series TLS heap contention test (see T272 as the reference test pattern).

Precedents: `TeletextApp::pollTeletext()`, `StockApp::fetchQuote()`.

---

### 3. Serial debug surface — `dbgGet` / `dbgSet` (BP implicit from LL-060)

**Required**: all apps must expose a `dbgGet`/`dbgSet` surface for VE testability.  
**Minimum**: `dbgGet` returning the app's key state variable(s) (e.g. last action, pending flag, current page).  
`dbgSet` required for any state the VE needs to inject (e.g. subpage targets, cooldown override).

- [ ] App class implements `bool dbgGet(const char* var, char* buf, int len) const`.
- [ ] Register it in the `handleSerialCommands()` dispatch table in `main.cpp` (alongside the existing per-app blocks).
- [ ] If any state needs injection for synthetic tests: implement `bool dbgSet(const char* var, const char* val)` and register it.
- [ ] Add `get <appName>LastAction` (or equivalent state key) as a minimum VE hook.

Precedents: all existing apps in `main.cpp` lines ~1619–1634.

---

### 4. `cmdTap` busy propagation

**Required if**: item 1 above applies (app has `hasPendingAsync()`).  
**Symptom of omission**: `get shellBusy` returns `false` immediately after a tap that enqueues async work, causing
VE `_wait_shell_not_busy` to exit before the work completes.

- [ ] In `main.cpp`, the `cmdTap` branch for this app must call:
  ```cpp
  if (!g_shellBusy && g_apps[(int)AppId::NewApp]->hasPendingAsync())
      shell::setBusy(true);
  ```
  after `handleInput()` dispatches.

Precedents: Stock (line ~2195), Teletext (line ~2209), Spotify (line ~2221).

---

### 5. `cross_feature_matrix.yaml` entries

- [ ] For each cross-cutting feature the app participates in (touch-004, tls-yield, app-interface-001, etc.),
  add a matrix entry documenting the relationship and wiring date.

---

## Deferral policy

If a checklist item is explicitly deferred (e.g. no async work planned for v1), note the deferral in the
app's feature entry in `feature_inventory.yaml` with a `deferred:` key and rationale.  
QM audits the deferred list at each milestone retrospective.
