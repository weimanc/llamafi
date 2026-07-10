// pr_parse_trial — M-PLANERADAR phase 0: host heap-bound trial for ADS-B parse.
// Design: docs/architecture/designs/M-PLANERADAR/phase0-parse-heap.md
//
// Measures peak JsonDocument allocation for:
//   leg A  — reference approach: whole body buffered + full-document parse
//   leg B  — filtered stream parse into fixed PrAircraft records (D1(b) lean)
// against a fixture file, using ArduinoJson 6.21.3 (device-pinned version).
//
// Build: make && ./pr_parse_trial <fixture.json> [--leg A|B] [--cap N]

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <string>
#include <vector>

#include "ArduinoJson-v6.21.3.h"

// ---------------------------------------------------------------- allocator
// NOTE (phase0-parse-heap.md §Instrumentation): v6's BasicJsonDocument calls the
// allocator ONCE per document, sized to the requested capacity — so g_peak
// reports the pool grab, NOT bytes the parse used. Actual usage comes from
// doc.memoryUsage() after the parse; minimum viable capacity from the legBmin
// binary search. The allocator stays only to verify the single-pool-alloc
// assumption and account total heap traffic.
static size_t g_live = 0, g_peak = 0, g_allocs = 0;

struct TrackingAllocator {
  // ArduinoJson v6 BasicJsonDocument allocator concept: allocate/deallocate/reallocate.
  // Book-keep size in a header word so deallocate() can subtract.
  void* allocate(size_t n) {
    auto* p = static_cast<size_t*>(std::malloc(n + sizeof(size_t)));
    if (!p) return nullptr;
    *p = n;
    g_live += n;
    ++g_allocs;
    if (g_live > g_peak) g_peak = g_live;
    return p + 1;
  }
  void deallocate(void* q) {
    if (!q) return;
    auto* p = static_cast<size_t*>(q) - 1;
    g_live -= *p;
    std::free(p);
  }
  void* reallocate(void* q, size_t n) {
    if (!q) return allocate(n);
    auto* p = static_cast<size_t*>(q) - 1;
    size_t old = *p;
    auto* np = static_cast<size_t*>(std::realloc(p, n + sizeof(size_t)));
    if (!np) return nullptr;
    *np = n;
    g_live += n - old;
    ++g_allocs;
    if (g_live > g_peak) g_peak = g_live;
    return np + 1;
  }
};
using TrackedDoc = ArduinoJson::BasicJsonDocument<TrackingAllocator>;

static void resetStats() { g_live = g_peak = g_allocs = 0; }

// ---------------------------------------------------------------- stream shim
// Chunked byte source over a memory buffer — mimics WiFiClientSecure reads
// (512-byte chunks) so leg B is a true incremental parse, not a buffer parse.
class ChunkedReader {
 public:
  ChunkedReader(const char* data, size_t len) : _d(data), _len(len) {}
  int read() {  // single-byte read, the interface ArduinoJson uses on Stream
    if (_pos >= _len) return -1;
    return static_cast<unsigned char>(_d[_pos++]);
  }
  size_t readBytes(char* buf, size_t n) {
    size_t chunk = n < 512 ? n : 512;
    size_t avail = _len - _pos;
    if (chunk > avail) chunk = avail;
    std::memcpy(buf, _d + _pos, chunk);
    _pos += chunk;
    return chunk;
  }
 private:
  const char* _d;
  size_t _len, _pos = 0;
};

// One-char pushback wrapper: leg C's scanner consumes the '{' that opens each
// aircraft object before handing the stream to deserializeJson.
class PrependReader {
 public:
  PrependReader(char c, ChunkedReader& inner) : _c(c), _inner(inner) {}
  int read() {
    if (_has) { _has = false; return static_cast<unsigned char>(_c); }
    return _inner.read();
  }
  size_t readBytes(char* buf, size_t n) {
    size_t off = 0;
    if (_has && n > 0) { buf[0] = _c; _has = false; off = 1; }
    return off + _inner.readBytes(buf + off, n - off);
  }
 private:
  char _c;
  bool _has = true;
  ChunkedReader& _inner;
};

// ---------------------------------------------------------------- output record
struct PrAircraft {          // firmware result-record candidate (~40 B)
  float lat, lon;
  float distNm;              // server 'dst' (NM); truncation sort key
  int16_t noseDeg, trackDeg;
  int16_t gsKnots;
  int32_t altFt;             // INT32_MIN = GND, INT32_MAX = unknown
  char callsign[9];
  char type[5];
};

static float pickF(ArduinoJson::JsonObjectConst o, std::initializer_list<const char*> keys,
                   float dflt) {
  for (const char* k : keys) {
    auto v = o[k];
    if (v.is<float>() || v.is<int>()) return v.as<float>();
  }
  return dflt;
}

static void copyTrimmed(ArduinoJson::JsonObjectConst o, const char* key, char* out,
                        size_t cap) {
  out[0] = '\0';
  const char* s = o[key].as<const char*>();
  if (!s) return;
  size_t n = strnlen(s, cap - 1);
  while (n > 0 && s[n - 1] == ' ') --n;
  std::memcpy(out, s, n);
  out[n] = '\0';
}

static bool fillRecord(ArduinoJson::JsonObjectConst plane, PrAircraft* ac,
                       bool showGround) {
  if (!plane["lat"].is<float>() || !plane["lon"].is<float>()) return false;
  const char* ab = plane["alt_baro"].as<const char*>();
  bool ground = ab && std::strcmp(ab, "ground") == 0;
  if (ground && !showGround) return false;

  ac->lat = plane["lat"].as<float>();
  ac->lon = plane["lon"].as<float>();
  ac->distNm = pickF(plane, {"dst"}, 1e9f);
  ac->noseDeg = (int16_t)lroundf(pickF(plane, {"true_heading", "mag_heading", "track", "dir"}, 0));
  ac->trackDeg = (int16_t)lroundf(pickF(plane, {"track", "true_heading", "mag_heading", "dir"}, 0));
  ac->gsKnots = (int16_t)lroundf(pickF(plane, {"gs", "tas", "ias"}, 0));
  if (ground) ac->altFt = INT32_MIN;
  else {
    float alt;
    if (plane["alt_baro"].is<float>() || plane["alt_baro"].is<int>()) alt = plane["alt_baro"].as<float>();
    else if (plane["alt_geom"].is<float>() || plane["alt_geom"].is<int>()) alt = plane["alt_geom"].as<float>();
    else { ac->altFt = INT32_MAX; goto tags; }
    ac->altFt = (int32_t)lroundf(alt);
  }
tags:
  copyTrimmed(plane, "flight", ac->callsign, sizeof(ac->callsign));
  if (!ac->callsign[0]) copyTrimmed(plane, "hex", ac->callsign, sizeof(ac->callsign));
  copyTrimmed(plane, "t", ac->type, sizeof(ac->type));
  return true;
}

// Nearest-first replace-farthest insertion (policy (ii)).
static void insertNearest(std::vector<PrAircraft>& kept, size_t cap, const PrAircraft& ac) {
  if (kept.size() < cap) { kept.push_back(ac); return; }
  size_t far = 0;
  for (size_t i = 1; i < kept.size(); ++i)
    if (kept[i].distNm > kept[far].distNm) far = i;
  if (ac.distNm < kept[far].distNm) kept[far] = ac;
}

// ---------------------------------------------------------------- filter
static void buildFilter(ArduinoJson::JsonDocument& filter, bool nested) {
  // Definitive 15-field set — phase0-parse-heap.md / phase0-api-probe.md Goal 2.
  for (const char* k : {"lat", "lon", "dst", "dir", "track", "true_heading",
                        "mag_heading", "gs", "tas", "ias", "alt_baro",
                        "alt_geom", "flight", "hex", "t"}) {
    if (nested) filter["ac"][0][k] = true;
    else filter[k] = true;
  }
}

// ---------------------------------------------------------------- legs
static int legA(const std::string& body, size_t cap, bool quiet) {
  // Reference approach: body already buffered (String equivalent) + full parse.
  // v6 needs an upfront capacity; sweep doubling until the parse fits, like a
  // developer would after the first NoMemory.
  resetStats();
  size_t capacity = body.size() * 2;
  TrackedDoc doc(capacity);
  auto err = ArduinoJson::deserializeJson(doc, body);
  while (err == ArduinoJson::DeserializationError::NoMemory &&
         capacity < (1u << 22)) {
    capacity *= 2;
    doc = TrackedDoc(capacity);
    err = ArduinoJson::deserializeJson(doc, body);
  }
  if (err) { std::printf("legA: parse error: %s\n", err.c_str()); return 2; }
  size_t n = 0;
  std::vector<PrAircraft> kept;
  for (ArduinoJson::JsonObjectConst plane : doc["ac"].as<ArduinoJson::JsonArrayConst>()) {
    PrAircraft ac{};
    if (fillRecord(plane, &ac, false)) { insertNearest(kept, cap, ac); ++n; }
  }
  if (!quiet)
    std::printf("legA: body=%zu poolGrab=%zu memoryUsage=%zu allocs=%zu "
                "peakTotal(body+used)=%zu parsed=%zu kept=%zu\n",
                body.size(), g_peak, doc.memoryUsage(), g_allocs,
                body.size() + doc.memoryUsage(), n, kept.size());
  return 0;
}

static int legB(const std::string& body, size_t filterCap, size_t cap, bool quiet,
                std::vector<PrAircraft>* keptOut = nullptr) {
  // D1(b): filtered stream parse. No body buffer counted — bytes come off the
  // (chunked) stream. Filter keeps only the fields the app reads.
  resetStats();
  ArduinoJson::StaticJsonDocument<768> filter;
  buildFilter(filter, true);

  ChunkedReader reader(body.data(), body.size());
  TrackedDoc doc(filterCap);
  auto err = ArduinoJson::deserializeJson(
      doc, reader, ArduinoJson::DeserializationOption::Filter(filter));
  if (err) {
    std::printf("legB: parse error: %s (docPeak=%zu)\n", err.c_str(), g_peak);
    return 2;
  }
  size_t n = 0;
  std::vector<PrAircraft> kept;
  for (ArduinoJson::JsonObjectConst plane : doc["ac"].as<ArduinoJson::JsonArrayConst>()) {
    PrAircraft ac{};
    if (fillRecord(plane, &ac, false)) { insertNearest(kept, cap, ac); ++n; }
  }
  if (!quiet)
    std::printf("legB: filterCap=%zu poolGrab=%zu memoryUsage=%zu allocs=%zu "
                "parsed=%zu kept=%zu recBytes=%zu\n",
                filterCap, g_peak, doc.memoryUsage(), g_allocs, n, kept.size(),
                cap * sizeof(PrAircraft));
  if (keptOut) *keptOut = kept;
  return 0;
}

// Find minimum filter-doc capacity that parses without NoMemory (binary search).
static void legBmin(const std::string& body) {
  auto attempt = [&](size_t capacity) {
    ChunkedReader r(body.data(), body.size());
    ArduinoJson::StaticJsonDocument<768> filter;
    buildFilter(filter, true);
    TrackedDoc doc(capacity);
    auto err = ArduinoJson::deserializeJson(
        doc, r, ArduinoJson::DeserializationOption::Filter(filter));
    return std::make_pair(err, doc.memoryUsage());
  };
  size_t lo = 256, hi = 1 << 20;
  if (attempt(hi).first) {
    std::printf("legBmin: even hi capacity fails; fixture bad?\n");
    return;
  }
  while (lo < hi) {
    size_t mid = (lo + hi) / 2;
    if (attempt(mid).first == ArduinoJson::DeserializationError::NoMemory)
      lo = mid + 1;
    else
      hi = mid;
  }
  std::printf("legBmin: minimum filter-doc capacity = %zu bytes "
              "(memoryUsage at min = %zu)\n", lo, attempt(lo).second);
}

// Leg C — chunked per-object parse: scan to the "ac" array, then parse ONE
// aircraft object at a time into a small reused doc. Peak heap is bounded by
// the largest single aircraft object, independent of aircraft count — the
// candidate firmware approach if leg B's whole-response doc scales too hard.
static int legC(const std::string& body, size_t docCap, size_t cap, bool quiet,
                std::vector<PrAircraft>* keptOut = nullptr) {
  resetStats();
  ChunkedReader reader(body.data(), body.size());
  // scan for "ac" key then its '['
  const char* pat = "\"ac\"";
  int pi = 0, c;
  while ((c = reader.read()) != -1) {
    if (c == pat[pi]) { if (!pat[++pi]) break; }
    else pi = (c == pat[0]) ? 1 : 0;
  }
  if (c == -1) { std::printf("legC: no \"ac\" key\n"); return 2; }
  while ((c = reader.read()) != -1 && c != '[') {
    if (!std::isspace(c) && c != ':') { std::printf("legC: bad ac value\n"); return 2; }
  }
  if (c == -1) { std::printf("legC: truncated before array\n"); return 2; }

  ArduinoJson::StaticJsonDocument<768> filter;
  buildFilter(filter, false);
  TrackedDoc doc(docCap);
  std::vector<PrAircraft> kept;
  size_t n = 0, peakUsage = 0;
  for (;;) {
    do { c = reader.read(); } while (c != -1 && (std::isspace(c) || c == ','));
    if (c == ']') break;
    if (c == -1) { std::printf("legC: truncated mid-array\n"); return 2; }
    if (c != '{') { std::printf("legC: unexpected byte 0x%02x\n", c); return 2; }
    PrependReader pr('{', reader);
    auto err = ArduinoJson::deserializeJson(
        doc, pr, ArduinoJson::DeserializationOption::Filter(filter));
    if (err) { std::printf("legC: parse error at object %zu: %s\n", n, err.c_str()); return 2; }
    if (doc.memoryUsage() > peakUsage) peakUsage = doc.memoryUsage();
    PrAircraft ac{};
    if (fillRecord(doc.as<ArduinoJson::JsonObjectConst>(), &ac, false))
      insertNearest(kept, cap, ac);
    ++n;
  }
  if (!quiet)
    std::printf("legC: docCap=%zu peakPerObjectUsage=%zu poolGrab=%zu allocs=%zu "
                "parsed=%zu kept=%zu recBytes=%zu\n",
                docCap, peakUsage, g_peak, g_allocs, n, kept.size(),
                cap * sizeof(PrAircraft));
  if (keptOut) *keptOut = kept;
  return 0;
}

// Emit kept set as JSON lines for the Python oracle diff (exit criterion 3).
static void dumpKept(const std::vector<PrAircraft>& kept) {
  for (const auto& a : kept)
    std::printf("KEPT {\"callsign\":\"%s\",\"dst\":%.3f,\"lat\":%.6f,\"lon\":%.6f}\n",
                a.callsign, a.distNm, a.lat, a.lon);
}

int main(int argc, char** argv) {
  if (argc < 2) {
    std::fprintf(stderr, "usage: %s <fixture.json> [--leg A|B|C|min|all] [--cap N] [--dump-kept]\n",
                 argv[0]);
    return 1;
  }
  const char* leg = "all";
  size_t cap = 24;
  bool dump = false;
  for (int i = 2; i < argc; ++i) {
    if (!std::strcmp(argv[i], "--leg") && i + 1 < argc) leg = argv[++i];
    else if (!std::strcmp(argv[i], "--cap") && i + 1 < argc) cap = std::atoi(argv[++i]);
    else if (!std::strcmp(argv[i], "--dump-kept")) dump = true;
  }

  FILE* f = std::fopen(argv[1], "rb");
  if (!f) { std::perror("fopen"); return 1; }
  std::string body;
  char buf[4096];
  size_t r;
  while ((r = std::fread(buf, 1, sizeof(buf), f)) > 0) body.append(buf, r);
  std::fclose(f);

  int rc = 0;
  if (!std::strcmp(leg, "A") || !std::strcmp(leg, "all")) rc |= legA(body, cap, false);
  if (!std::strcmp(leg, "B") || !std::strcmp(leg, "all")) {
    std::vector<PrAircraft> kept;
    rc |= legB(body, 1 << 17, cap, false, &kept);
    if (dump && !std::strcmp(leg, "B")) dumpKept(kept);
  }
  if (!std::strcmp(leg, "C") || !std::strcmp(leg, "all")) {
    std::vector<PrAircraft> kept;
    rc |= legC(body, 4096, cap, false, &kept);
    if (dump && !std::strcmp(leg, "C")) dumpKept(kept);
  }
  if (!std::strcmp(leg, "min")) legBmin(body);
  return rc;
}
