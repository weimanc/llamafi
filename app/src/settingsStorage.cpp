#include "settingsStorage.h"
#include <SPIFFS.h>
#include <ArduinoJson.h>

AppSettings g_settings;

// ---- Defaults --------------------------------------------------------------

static void applyDefaults() {
    // Time & Location
    strlcpy(g_settings.posixTz, "UTC0", sizeof(g_settings.posixTz));
    strlcpy(g_settings.tzName,  "UTC",  sizeof(g_settings.tzName));
    g_settings.city[0] = '\0';
    g_settings.lat     = 0.0f;
    g_settings.lon     = 0.0f;
    g_settings.fmt24h  = true;
    g_settings.dateFmt = DateFmt::DMY;

    // Display
    g_settings.dispAuto  = false;
    g_settings.dispLevel = 7;
    g_settings.ldrLow    =   0;    // this hardware: ambient ≈ 0 ADC
    g_settings.ldrHigh   = 120;   // this hardware: fully covered ≈ 140 ADC

    // LED
    g_settings.ledMode = LedMode::Off;
    g_settings.ledHue  = 85;    // hue 120° ≈ green (prior default colour)
    g_settings.ledSat  = 255;
    g_settings.ledVal  = 200;

    // Stock
    static const char* kDefTickers[8] = {
        "AAPL","AMD","AMZN","ARM","GOOG","META","MSFT","NVDA"
    };
    for (int i = 0; i < 8; i++)
        strlcpy(g_settings.stockTickers[i], kDefTickers[i], 8);
    g_settings.stockMode = StockViewMode::List;

    // Crypto
    static const char* kDefCoins[6] = {
        "bitcoin","ethereum","solana","binancecoin","ripple","cardano"
    };
    for (int i = 0; i < 6; i++)
        strlcpy(g_settings.cryptoCoins[i], kDefCoins[i], 16);
    strlcpy(g_settings.cryptoCcy, "usd", sizeof(g_settings.cryptoCcy));

    // Aquarium
    g_settings.aquariumFish  = 8;
    g_settings.aquariumSpeed = AppSpeed::Normal;

    // Matrix
    g_settings.matrixColor = MatrixColor::Green;
    g_settings.matrixSpeed = AppSpeed::Normal;

    // Life
    g_settings.lifeSpeed  = AppSpeed::Normal;
    g_settings.lifeColors = LifeColors::Rainbow;

    // Clock
    g_settings.clockStyle = ClockStyle::Digital;

    // Player slot (M-PLAYER-STATE / TASK-260)
    g_settings.playerMode = (uint8_t)PlayerMode::Spotify;

    // Teletext
    g_settings.teletextPage        = 101;
    g_settings.teletextPollSecs    = 60;
    g_settings.teletextCountry     = 0;
    g_settings.teletextAutoAdvance = false;

    // Web Radio
    strlcpy(g_settings.webRadioCountry, "NL", sizeof(g_settings.webRadioCountry));
    g_settings.webRadioAutoplay      = false;
    g_settings.webRadioBitrateCap    = 96;
    g_settings.webRadioAutoSkip      = true;   // TASK-234/ADR-045: default ON
    g_settings.webRadioHwMod         = false;
    // TASK-209 / §HW Mod: stock default 10 (soft-capped to 12 at playback); the
    // HW-mod default of 18 is applied in load() when hwMod is set with no explicit
    // maxVolume. webRadioApp::wrEffectiveVolume() enforces the hardware ceiling.
    g_settings.webRadioMaxVolume     = 10;
    g_settings.webRadioLastStation   = 0;

    // Plane Radar (matches planeRadarApp.h's PR_DEFAULT_LAT/LON)
    g_settings.prLat            = 52.3676f;
    g_settings.prLon            = 4.9041f;
    g_settings.prUnits          = 0;
    g_settings.prRunwayOverlay  = true;
    g_settings.prRangeIdx       = 1;   // 10 km
    g_settings.prTagRule        = PrTagRule::C;
    g_settings.prStaleStyle     = PrStaleStyle::Ring;

    // M-PR-LOCATIONS: slot 0 seeded from the compile-time default above
    // (matches prLat/prLon); slots 1..3 start empty.
    strlcpy(g_settings.prLocs[0].label, "HOME", sizeof(g_settings.prLocs[0].label));
    g_settings.prLocs[0].lat = g_settings.prLat;
    g_settings.prLocs[0].lon = g_settings.prLon;
    for (int i = 1; i < PR_NUM_LOCS; i++) {
        g_settings.prLocs[i].label[0] = '\0';
        g_settings.prLocs[i].lat      = 0.0f;
        g_settings.prLocs[i].lon      = 0.0f;
    }
    g_settings.prActiveLoc = 0;
}

// ---- Enum string tables (order must match enum values) --------------------

static const char* kDateFmtStr[]     = {"DMY","MDY","YMD"};
static const char* kLedModeStr[]     = {"off","static","pulse","clock"};
static const char* kSpeedStr[]       = {"slow","normal","fast"};
static const char* kStockModeStr[]   = {"list","chart","heatmap"};
static const char* kMatrixColorStr[] = {"green","white","amber"};
static const char* kLifeColorsStr[]  = {"rainbow","mono"};
static const char* kClockStyleStr[]  = {"digital","flip","nixie","vfd"};
static const char* kPrTagRuleStr[]   = {"a","b","c"};
static const char* kPrStaleStyleStr[]= {"ring","text","dim"};

template<typename E, int N>
static E strToEnum(const char* s, const char* (&table)[N], E def) {
    for (int i = 0; i < N; i++)
        if (strcmp(s, table[i]) == 0) return (E)i;
    return def;
}

// ---- Load ------------------------------------------------------------------

void SettingsStorage::load() {
    applyDefaults();

    if (!SPIFFS.exists(SETTINGS_JSON)) return;

    File f = SPIFFS.open(SETTINGS_JSON, "r");
    if (!f) return;

    DynamicJsonDocument doc(3072);
    if (deserializeJson(doc, f) != DeserializationError::Ok) {
        f.close();
        Serial.println("SettingsStorage: parse error — using defaults");
        return;
    }
    f.close();

    // Time & Location
    if (doc.containsKey("time")) {
        auto t = doc["time"];
        if (t.containsKey("posixTz")) strlcpy(g_settings.posixTz, t["posixTz"] | "UTC0", sizeof(g_settings.posixTz));
        if (t.containsKey("tzName"))  strlcpy(g_settings.tzName,  t["tzName"]  | "UTC",  sizeof(g_settings.tzName));
        if (t.containsKey("city"))    strlcpy(g_settings.city,    t["city"]    | "",      sizeof(g_settings.city));
        if (t.containsKey("lat"))     g_settings.lat    = t["lat"]    | 0.0f;
        if (t.containsKey("lon"))     g_settings.lon    = t["lon"]    | 0.0f;
        if (t.containsKey("fmt24h"))  g_settings.fmt24h = t["fmt24h"] | true;
        if (t.containsKey("dateFmt")) g_settings.dateFmt = strToEnum<DateFmt>(t["dateFmt"] | "DMY", kDateFmtStr, DateFmt::DMY);
    }

    // Display
    if (doc.containsKey("disp")) {
        auto d = doc["disp"];
        if (d.containsKey("auto"))    g_settings.dispAuto  = d["auto"]    | false;
        if (d.containsKey("level"))   g_settings.dispLevel = d["level"]   | 7;
        if (d.containsKey("ldrLow"))  g_settings.ldrLow    = d["ldrLow"]  | 200;
        if (d.containsKey("ldrHigh")) g_settings.ldrHigh   = d["ldrHigh"] | 3800;
    }

    // LED
    if (doc.containsKey("led")) {
        auto l = doc["led"];
        if (l.containsKey("mode")) g_settings.ledMode = strToEnum<LedMode>(l["mode"] | "off", kLedModeStr, LedMode::Off);
        if (l.containsKey("hue"))  g_settings.ledHue  = l["hue"]  | 85;
        if (l.containsKey("sat"))  g_settings.ledSat  = l["sat"]  | 255;
        if (l.containsKey("val"))  g_settings.ledVal  = l["val"]  | 200;
    }

    // Stock
    if (doc.containsKey("stock")) {
        auto s = doc["stock"];
        if (s.containsKey("tickers")) {
            int i = 0;
            for (JsonVariantConst v : s["tickers"].as<JsonArrayConst>()) {
                if (i >= 8) break;
                const char* t = v | "";
                if (t[0]) strlcpy(g_settings.stockTickers[i], t, 8);
                i++;
            }
        }
        if (s.containsKey("mode")) g_settings.stockMode = strToEnum<StockViewMode>(s["mode"] | "list", kStockModeStr, StockViewMode::List);
    }

    // Crypto
    if (doc.containsKey("crypto")) {
        auto c = doc["crypto"];
        if (c.containsKey("coins")) {
            int i = 0;
            for (JsonVariantConst v : c["coins"].as<JsonArrayConst>()) {
                if (i >= 6) break;
                const char* coin = v | "";
                if (coin[0]) strlcpy(g_settings.cryptoCoins[i], coin, 16);
                i++;
            }
        }
        if (c.containsKey("ccy")) {
            const char* ccy = c["ccy"] | "";
            if (ccy[0]) strlcpy(g_settings.cryptoCcy, ccy, sizeof(g_settings.cryptoCcy));
        }
    }

    // Aquarium
    if (doc.containsKey("aquarium")) {
        auto a = doc["aquarium"];
        if (a.containsKey("fish"))  { uint8_t f = a["fish"] | 8; if (f) g_settings.aquariumFish = f; }
        if (a.containsKey("speed")) g_settings.aquariumSpeed = strToEnum<AppSpeed>(a["speed"] | "normal", kSpeedStr, AppSpeed::Normal);
    }

    // Matrix
    if (doc.containsKey("matrix")) {
        auto m = doc["matrix"];
        if (m.containsKey("color")) g_settings.matrixColor = strToEnum<MatrixColor>(m["color"] | "green", kMatrixColorStr, MatrixColor::Green);
        if (m.containsKey("speed")) g_settings.matrixSpeed = strToEnum<AppSpeed>(m["speed"] | "normal", kSpeedStr, AppSpeed::Normal);
    }

    // Life
    if (doc.containsKey("life")) {
        auto l = doc["life"];
        if (l.containsKey("speed"))  g_settings.lifeSpeed  = strToEnum<AppSpeed>(l["speed"] | "normal", kSpeedStr, AppSpeed::Normal);
        if (l.containsKey("colors")) g_settings.lifeColors = strToEnum<LifeColors>(l["colors"] | "rainbow", kLifeColorsStr, LifeColors::Rainbow);
    }

    // Clock
    if (doc.containsKey("clock")) {
        auto ck = doc["clock"];
        if (ck.containsKey("style")) g_settings.clockStyle = strToEnum<ClockStyle>(ck["style"] | "digital", kClockStyleStr, ClockStyle::Digital);
    }

    // Player slot (M-PLAYER-STATE / TASK-260): top-level object — the mode spans both
    // Spotify and WebRadio, so it is not nested under "webRadio". Clamp to {0,1}.
    if (doc.containsKey("player")) {
        uint8_t pm = doc["player"]["mode"] | 0;
        g_settings.playerMode = (pm > (uint8_t)PlayerMode::WebRadio) ? (uint8_t)PlayerMode::Spotify : pm;
    }

    // Teletext
    if (doc.containsKey("teletext")) {
        auto tt = doc["teletext"];
        if (tt.containsKey("page"))        g_settings.teletextPage        = tt["page"]        | 101;
        if (tt.containsKey("pollSecs"))    g_settings.teletextPollSecs    = tt["pollSecs"]    | 60;
        if (tt.containsKey("country"))     g_settings.teletextCountry     = tt["country"]     | 0;
        if (tt.containsKey("autoAdvance")) g_settings.teletextAutoAdvance = tt["autoAdvance"] | false;
    }

    // Web Radio
    if (doc.containsKey("webRadio")) {
        auto wr = doc["webRadio"];
        if (wr.containsKey("country"))     strlcpy(g_settings.webRadioCountry, wr["country"] | "NL", sizeof(g_settings.webRadioCountry));
        if (wr.containsKey("autoplay"))    g_settings.webRadioAutoplay    = wr["autoplay"]    | false;
        if (wr.containsKey("bitrateCap"))  g_settings.webRadioBitrateCap  = wr["bitrateCap"]  | 96;
        if (wr.containsKey("autoSkip"))    g_settings.webRadioAutoSkip    = wr["autoSkip"]    | true;
        if (wr.containsKey("hwMod"))       g_settings.webRadioHwMod       = wr["hwMod"]       | false;
        // TASK-209 / §HW Mod: explicit maxVolume wins; otherwise default 18 with the
        // HW mod, 10 stock (hwMod is parsed just above, so it's current here). The
        // playback clamp (wrEffectiveVolume) still bounds whatever value lands.
        g_settings.webRadioMaxVolume = wr["maxVolume"] | (uint8_t)(g_settings.webRadioHwMod ? 18 : 10);
        if (wr.containsKey("lastStation")) g_settings.webRadioLastStation = wr["lastStation"] | 0;
    }

    // Plane Radar
    if (doc.containsKey("planeRadar")) {
        auto pr = doc["planeRadar"];
        if (pr.containsKey("lat"))      g_settings.prLat           = pr["lat"]      | 52.3676f;
        if (pr.containsKey("lon"))      g_settings.prLon           = pr["lon"]      | 4.9041f;
        if (pr.containsKey("units"))    g_settings.prUnits         = pr["units"]    | 0;
        if (pr.containsKey("runways"))  g_settings.prRunwayOverlay = pr["runways"]  | true;
        if (pr.containsKey("rangeIdx")) g_settings.prRangeIdx      = pr["rangeIdx"] | 1;
        if (pr.containsKey("tagRule"))
            g_settings.prTagRule = strToEnum<PrTagRule>(pr["tagRule"] | "c", kPrTagRuleStr, PrTagRule::C);
        if (pr.containsKey("staleStyle"))
            g_settings.prStaleStyle = strToEnum<PrStaleStyle>(pr["staleStyle"] | "ring", kPrStaleStyleStr, PrStaleStyle::Ring);

        // M-PR-LOCATIONS (DEV-PRL-6): this MUST run after the lat/lon parsing
        // above, not before — the migration branch seeds prLocs[0] from
        // g_settings.prLat/prLon *as already resolved this call* (the file's
        // value if present, else applyDefaults()'s compile default). Moving
        // this ahead of the lat/lon block would silently discard a real
        // pre-upgrade user location in favour of the Amsterdam default.
        if (pr.containsKey("locs")) {
            int i = 0;
            for (JsonVariantConst v : pr["locs"].as<JsonArrayConst>()) {
                if (i >= PR_NUM_LOCS) break;
                strlcpy(g_settings.prLocs[i].label, v["label"] | "", sizeof(g_settings.prLocs[i].label));
                g_settings.prLocs[i].lat = v["lat"] | 0.0f;
                g_settings.prLocs[i].lon = v["lon"] | 0.0f;
                i++;
            }
            if (pr.containsKey("activeLoc")) g_settings.prActiveLoc = pr["activeLoc"] | 0;
        } else {
            // Migration: pre-upgrade settings.json has no "locs" key yet.
            strlcpy(g_settings.prLocs[0].label, "HOME", sizeof(g_settings.prLocs[0].label));
            g_settings.prLocs[0].lat = g_settings.prLat;
            g_settings.prLocs[0].lon = g_settings.prLon;
            for (int i = 1; i < PR_NUM_LOCS; i++) g_settings.prLocs[i].label[0] = '\0';
            g_settings.prActiveLoc = 0;
        }
    }
    if (g_settings.prRangeIdx > 3) g_settings.prRangeIdx = 1;   // corrupt/out-of-range guard

    // M-PR-LOCATIONS invariants (covers the loaded-array branch, the migration
    // branch, and a corrupt file alike):
    if (g_settings.prLocs[0].label[0] == '\0') {
        // Slot 0 must never be empty (prActiveLoc validity depends on it).
        strlcpy(g_settings.prLocs[0].label, "HOME", sizeof(g_settings.prLocs[0].label));
        g_settings.prLocs[0].lat = g_settings.prLat;
        g_settings.prLocs[0].lon = g_settings.prLon;
    }
    if (g_settings.prActiveLoc >= PR_NUM_LOCS ||
        g_settings.prLocs[g_settings.prActiveLoc].label[0] == '\0')
        g_settings.prActiveLoc = 0;
    // Write-through mirror (design "Settings storage"): prLat/prLon are now
    // derived FROM the active slot, every load, so every existing consumer
    // that only reads prLat/prLon stays correct without modification.
    g_settings.prLat = g_settings.prLocs[g_settings.prActiveLoc].lat;
    g_settings.prLon = g_settings.prLocs[g_settings.prActiveLoc].lon;

    // Migrate: ldrHigh==0 means uncalibrated (old save or user wiped it).
    if (g_settings.ldrHigh == 0)
        g_settings.ldrHigh = 120;

    Serial.println("SettingsStorage: loaded");
}

// ---- Save ------------------------------------------------------------------

void SettingsStorage::save() {
    DynamicJsonDocument doc(3072);

    auto t = doc.createNestedObject("time");
    t["posixTz"] = g_settings.posixTz;
    t["tzName"]  = g_settings.tzName;
    t["city"]    = g_settings.city;
    t["lat"]     = g_settings.lat;
    t["lon"]     = g_settings.lon;
    t["fmt24h"]  = g_settings.fmt24h;
    t["dateFmt"] = kDateFmtStr[(uint8_t)g_settings.dateFmt];

    auto d = doc.createNestedObject("disp");
    d["auto"]    = g_settings.dispAuto;
    d["level"]   = g_settings.dispLevel;
    d["ldrLow"]  = g_settings.ldrLow;
    d["ldrHigh"] = g_settings.ldrHigh;

    auto l = doc.createNestedObject("led");
    l["mode"] = kLedModeStr[(uint8_t)g_settings.ledMode];
    l["hue"]  = g_settings.ledHue;
    l["sat"]  = g_settings.ledSat;
    l["val"]  = g_settings.ledVal;

    auto s = doc.createNestedObject("stock");
    auto tickers = s.createNestedArray("tickers");
    for (int i = 0; i < 8; i++) tickers.add(g_settings.stockTickers[i]);
    s["mode"] = kStockModeStr[(uint8_t)g_settings.stockMode];

    auto c = doc.createNestedObject("crypto");
    auto coins = c.createNestedArray("coins");
    for (int i = 0; i < 6; i++) coins.add(g_settings.cryptoCoins[i]);
    c["ccy"] = g_settings.cryptoCcy;

    auto aq = doc.createNestedObject("aquarium");
    aq["fish"]  = g_settings.aquariumFish;
    aq["speed"] = kSpeedStr[(uint8_t)g_settings.aquariumSpeed];

    auto mx = doc.createNestedObject("matrix");
    mx["color"] = kMatrixColorStr[(uint8_t)g_settings.matrixColor];
    mx["speed"] = kSpeedStr[(uint8_t)g_settings.matrixSpeed];

    auto lf = doc.createNestedObject("life");
    lf["speed"]  = kSpeedStr[(uint8_t)g_settings.lifeSpeed];
    lf["colors"] = kLifeColorsStr[(uint8_t)g_settings.lifeColors];

    auto ck = doc.createNestedObject("clock");
    ck["style"] = kClockStyleStr[(uint8_t)g_settings.clockStyle];

    // Player slot (M-PLAYER-STATE / TASK-260)
    doc.createNestedObject("player")["mode"] = g_settings.playerMode;

    auto tt = doc.createNestedObject("teletext");
    tt["page"]        = g_settings.teletextPage;
    tt["pollSecs"]    = g_settings.teletextPollSecs;
    tt["country"]     = g_settings.teletextCountry;
    tt["autoAdvance"] = g_settings.teletextAutoAdvance;

    auto wr = doc.createNestedObject("webRadio");
    wr["country"]     = g_settings.webRadioCountry;
    wr["autoplay"]    = g_settings.webRadioAutoplay;
    wr["bitrateCap"]  = g_settings.webRadioBitrateCap;
    wr["autoSkip"]    = g_settings.webRadioAutoSkip;
    wr["hwMod"]       = g_settings.webRadioHwMod;
    wr["maxVolume"]   = g_settings.webRadioMaxVolume;
    wr["lastStation"] = g_settings.webRadioLastStation;

    auto pr = doc.createNestedObject("planeRadar");
    pr["lat"]        = g_settings.prLat;
    pr["lon"]        = g_settings.prLon;
    pr["units"]      = g_settings.prUnits;
    pr["runways"]    = g_settings.prRunwayOverlay;
    pr["rangeIdx"]   = g_settings.prRangeIdx;
    pr["tagRule"]    = kPrTagRuleStr[(uint8_t)g_settings.prTagRule];
    pr["staleStyle"] = kPrStaleStyleStr[(uint8_t)g_settings.prStaleStyle];
    auto locs = pr.createNestedArray("locs");
    for (int i = 0; i < PR_NUM_LOCS; i++) {
        auto loc = locs.createNestedObject();
        loc["label"] = g_settings.prLocs[i].label;
        loc["lat"]   = g_settings.prLocs[i].lat;
        loc["lon"]   = g_settings.prLocs[i].lon;
    }
    pr["activeLoc"] = g_settings.prActiveLoc;

    File f = SPIFFS.open(SETTINGS_JSON, "w");
    if (!f) { Serial.println("SettingsStorage: failed to open for write"); return; }
    if (serializeJson(doc, f) == 0) Serial.println("SettingsStorage: write failed");
    f.close();
    Serial.println("SettingsStorage: saved");
}
