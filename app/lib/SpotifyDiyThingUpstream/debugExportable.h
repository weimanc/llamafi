#pragma once
// debugExportable.h — owner-dispatch interface for serial debug get/set.
// (ADR-021 Amendment A1 / TASK-056n). Compiled only in SERIAL_DEBUG builds.
// SpotifyDisplay provides default no-op implementations; WinampDisplay and
// spotifyTask override for their respective variable domains. cmdGet/cmdSet
// are dumb dispatchers — they never need to change as new variables are added.
#ifdef SERIAL_DEBUG

class IDebugExportable {
public:
    // Serialize var into buf as a JSON key-value fragment (no outer braces).
    // Returns false if var is unknown to this owner.
    // For multi-part payloads the owner emits Serial.printf lines directly
    // and sets buf[0]='\0'; cmdGet skips the wrapper print in that case.
    virtual bool dbgGet(const char* var, char* buf, int len) const = 0;

    // Write a debug variable. Returns false if var unknown or val invalid.
    virtual bool dbgSet(const char* var, const char* val) = 0;

protected:
    ~IDebugExportable() = default;
};

#endif // SERIAL_DEBUG
