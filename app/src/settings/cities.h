#pragma once
// cities.h — city/timezone picker data for TimeSection.
//
// Source: /usr/share/zoneinfo/zone1970.tab (tzdata); POSIX strings extracted
// from TZif v2 file footers on this host. Coordinates WGS84 decimal degrees.
//
// Order: UTC+ east to west, then UTC- east to west (top of picker = UTC+12).
// Within each UTC offset: sorted by population / global recognition.
// Multiple cities share a tzName when the POSIX rule is identical.

#include <Arduino.h>

struct CityEntry {
    const char* city;
    const char* country;   // ISO 3166-1 alpha-2
    float       lat;
    float       lon;
    const char* posixTz;   // POSIX tz rule — passed to configTzTime()
    const char* tzName;    // display name, e.g. "Asia/Tokyo"
    int8_t      utcHours;  // signed whole-hours offset, e.g. +9, -5, 0
    uint8_t     utcMins;   // fractional minutes: 0, 30, or 45
    bool        groupBreak;// true = first city in a new UTC offset group
};

static const CityEntry kCities[] = {
    // UTC+12
    { "Auckland",      "NZ", -36.8667f,  174.7667f, "NZST-12NZDT,M9.5.0,M4.1.0/3",      "Pacific/Auckland",               +12,  0, true  },
    { "Suva",          "FJ", -18.1333f,  178.4167f, "<+12>-12",                           "Pacific/Fiji",                   +12,  0, false },
    // UTC+11
    { "Noumea",        "NC", -22.2667f,  166.4500f, "<+11>-11",                           "Pacific/Noumea",                 +11,  0, true  },
    // UTC+10
    { "Sydney",        "AU", -33.8667f,  151.2167f, "AEST-10AEDT,M10.1.0,M4.1.0/3",      "Australia/Sydney",               +10,  0, true  },
    { "Melbourne",     "AU", -37.8167f,  144.9667f, "AEST-10AEDT,M10.1.0,M4.1.0/3",      "Australia/Melbourne",            +10,  0, false },
    { "Brisbane",      "AU", -27.4667f,  153.0333f, "AEST-10",                            "Australia/Brisbane",             +10,  0, false },
    // UTC+9:30
    { "Adelaide",      "AU", -34.9333f,  138.6000f, "ACST-9:30ACDT,M10.1.0,M4.1.0/3",    "Australia/Adelaide",              +9, 30, true  },
    // UTC+9
    { "Tokyo",         "JP",  35.6544f,  139.7447f, "JST-9",                              "Asia/Tokyo",                      +9,  0, true  },
    { "Seoul",         "KR",  37.5500f,  126.9667f, "KST-9",                              "Asia/Seoul",                      +9,  0, false },
    { "Osaka",         "JP",  34.6939f,  135.5022f, "JST-9",                              "Asia/Tokyo",                      +9,  0, false },
    // UTC+8
    { "Shanghai",      "CN",  31.2333f,  121.4667f, "CST-8",                              "Asia/Shanghai",                   +8,  0, true  },
    { "Beijing",       "CN",  39.9167f,  116.3833f, "CST-8",                              "Asia/Shanghai",                   +8,  0, false },
    { "Singapore",     "SG",   1.2833f,  103.8500f, "<+08>-8",                            "Asia/Singapore",                  +8,  0, false },
    { "Hong Kong",     "HK",  22.2855f,  114.1577f, "HKT-8",                              "Asia/Hong_Kong",                  +8,  0, false },
    { "Kuala Lumpur",  "MY",   3.1667f,  101.7000f, "<+08>-8",                            "Asia/Kuala_Lumpur",               +8,  0, false },
    { "Taipei",        "TW",  25.0500f,  121.5000f, "CST-8",                              "Asia/Taipei",                     +8,  0, false },
    { "Manila",        "PH",  14.5867f,  120.9678f, "PST-8",                              "Asia/Manila",                     +8,  0, false },
    { "Perth",         "AU", -31.9500f,  115.8500f, "AWST-8",                             "Australia/Perth",                 +8,  0, false },
    // UTC+7
    { "Bangkok",       "TH",  13.7500f,  100.5167f, "<+07>-7",                            "Asia/Bangkok",                    +7,  0, true  },
    { "Jakarta",       "ID",  -6.1667f,  106.8000f, "WIB-7",                              "Asia/Jakarta",                    +7,  0, false },
    { "Ho Chi Minh",   "VN",  10.8167f,  106.6333f, "<+07>-7",                            "Asia/Ho_Chi_Minh",                +7,  0, false },
    { "Hanoi",         "VN",  21.0333f,  105.8500f, "<+07>-7",                            "Asia/Ho_Chi_Minh",                +7,  0, false },
    // UTC+6:30
    { "Yangon",        "MM",  16.7833f,   96.1667f, "<+0630>-6:30",                       "Asia/Yangon",                     +6, 30, true  },
    // UTC+6
    { "Dhaka",         "BD",  23.7167f,   90.4167f, "<+06>-6",                            "Asia/Dhaka",                      +6,  0, true  },
    // UTC+5:45
    { "Kathmandu",     "NP",  27.7167f,   85.3167f, "<+0545>-5:45",                       "Asia/Kathmandu",                  +5, 45, true  },
    // UTC+5:30
    { "Mumbai",        "IN",  19.0758f,   72.8775f, "IST-5:30",                           "Asia/Kolkata",                    +5, 30, true  },
    { "Kolkata",       "IN",  22.5333f,   88.3667f, "IST-5:30",                           "Asia/Kolkata",                    +5, 30, false },
    { "Colombo",       "LK",   6.9333f,   79.8500f, "<+0530>-5:30",                       "Asia/Colombo",                    +5, 30, false },
    // UTC+5
    { "Karachi",       "PK",  24.8667f,   67.0500f, "PKT-5",                              "Asia/Karachi",                    +5,  0, true  },
    { "Tashkent",      "UZ",  41.2667f,   69.2167f, "<+05>-5",                            "Asia/Tashkent",                   +5,  0, false },
    { "Almaty",        "KZ",  43.2500f,   76.9500f, "<+05>-5",                            "Asia/Almaty",                     +5,  0, false },
    // UTC+4
    { "Dubai",         "AE",  25.3000f,   55.3000f, "<+04>-4",                            "Asia/Dubai",                      +4,  0, true  },
    { "Baku",          "AZ",  40.3667f,   49.8352f, "<+04>-4",                            "Asia/Baku",                       +4,  0, false },
    // UTC+3:30
    { "Tehran",        "IR",  35.6667f,   51.4333f, "<+0330>-3:30",                       "Asia/Tehran",                     +3, 30, true  },
    // UTC+3
    { "Moscow",        "RU",  55.7558f,   37.6178f, "MSK-3",                              "Europe/Moscow",                   +3,  0, true  },
    { "Istanbul",      "TR",  41.0167f,   28.9667f, "<+03>-3",                            "Europe/Istanbul",                 +3,  0, false },
    { "Riyadh",        "SA",  24.6333f,   46.7167f, "<+03>-3",                            "Asia/Riyadh",                     +3,  0, false },
    { "Baghdad",       "IQ",  33.3500f,   44.4167f, "<+03>-3",                            "Asia/Baghdad",                    +3,  0, false },
    { "Nairobi",       "KE",  -1.2833f,   36.8167f, "EAT-3",                              "Africa/Nairobi",                  +3,  0, false },
    // UTC+2
    { "Cairo",         "EG",  30.0500f,   31.2500f, "EET-2EEST,M4.5.5/0,M10.5.4/24",     "Africa/Cairo",                    +2,  0, true  },
    { "Johannesburg",  "ZA", -26.2500f,   28.0000f, "SAST-2",                             "Africa/Johannesburg",             +2,  0, false },
    { "Athens",        "GR",  37.9667f,   23.7167f, "EET-2EEST,M3.5.0/3,M10.5.0/4",      "Europe/Athens",                   +2,  0, false },
    { "Kyiv",          "UA",  50.4333f,   30.5167f, "EET-2EEST,M3.5.0/3,M10.5.0/4",      "Europe/Kiev",                     +2,  0, false },
    { "Bucharest",     "RO",  44.4333f,   26.1000f, "EET-2EEST,M3.5.0/3,M10.5.0/4",      "Europe/Bucharest",                +2,  0, false },
    { "Helsinki",      "FI",  60.1667f,   24.9667f, "EET-2EEST,M3.5.0/3,M10.5.0/4",      "Europe/Helsinki",                 +2,  0, false },
    // UTC+1
    { "Paris",         "FR",  48.8667f,    2.3333f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Paris",                    +1,  0, true  },
    { "Lagos",         "NG",   6.4500f,    3.4000f, "WAT-1",                              "Africa/Lagos",                    +1,  0, false },
    { "Berlin",        "DE",  52.5000f,   13.3667f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Berlin",                   +1,  0, false },
    { "Rome",          "IT",  41.9000f,   12.4833f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Rome",                     +1,  0, false },
    { "Madrid",        "ES",  40.4000f,   -3.6833f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Madrid",                   +1,  0, false },
    { "Warsaw",        "PL",  52.2500f,   21.0000f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Warsaw",                   +1,  0, false },
    { "Amsterdam",     "NL",  52.3667f,    4.9000f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Amsterdam",                +1,  0, false },
    { "Brussels",      "BE",  50.8333f,    4.3333f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Brussels",                 +1,  0, false },
    { "Stockholm",     "SE",  59.3333f,   18.0500f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Stockholm",                +1,  0, false },
    { "Vienna",        "AT",  48.2083f,   16.3731f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Vienna",                   +1,  0, false },
    { "Zurich",        "CH",  47.3833f,    8.5333f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Zurich",                   +1,  0, false },
    { "Prague",        "CZ",  50.0833f,   14.4333f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Prague",                   +1,  0, false },
    { "Budapest",      "HU",  47.5000f,   19.0833f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Budapest",                 +1,  0, false },
    { "Oslo",          "NO",  59.9167f,   10.7500f, "CET-1CEST,M3.5.0,M10.5.0/3",        "Europe/Oslo",                     +1,  0, false },
    // UTC+0
    { "London",        "GB",  51.5083f,   -0.1253f, "GMT0BST,M3.5.0/1,M10.5.0",          "Europe/London",                    0,  0, true  },
    { "Casablanca",    "MA",  33.6500f,   -7.5833f, "<+01>-1",                            "Africa/Casablanca",                0,  0, false },
    { "Lisbon",        "PT",  38.7167f,   -9.1333f, "WET0WEST,M3.5.0/1,M10.5.0",         "Europe/Lisbon",                    0,  0, false },
    { "Dublin",        "IE",  53.3331f,   -6.2489f, "IST-1GMT0,M10.5.0,M3.5.0/1",        "Europe/Dublin",                    0,  0, false },
    { "Accra",         "GH",   5.5500f,   -0.2167f, "GMT0",                               "Africa/Accra",                     0,  0, false },
    { "UTC",           "",     0.0000f,    0.0000f,  "UTC0",                               "UTC",                              0,  0, false },
    // UTC-3
    { "Sao Paulo",     "BR", -23.5333f,  -46.6167f, "<-03>3",                             "America/Sao_Paulo",               -3,  0, true  },
    { "Buenos Aires",  "AR", -34.6000f,  -58.4500f, "<-03>3",                             "America/Argentina/Buenos_Aires",  -3,  0, false },
    // UTC-4 (Santiago standard; DST brings it to -3)
    { "Santiago",      "CL", -33.4500f,  -70.6667f, "<-04>4<-03>,M9.1.6/24,M4.1.6/24",   "America/Santiago",                -4,  0, true  },
    { "Caracas",       "VE",  10.5000f,  -66.9333f, "<-04>4",                             "America/Caracas",                 -4,  0, false },
    // UTC-5
    { "New York",      "US",  40.7142f,  -74.0064f, "EST5EDT,M3.2.0,M11.1.0",            "America/New_York",                -5,  0, true  },
    { "Toronto",       "CA",  43.6500f,  -79.3833f, "EST5EDT,M3.2.0,M11.1.0",            "America/Toronto",                 -5,  0, false },
    { "Bogota",        "CO",   4.6000f,  -74.0833f, "<-05>5",                             "America/Bogota",                  -5,  0, false },
    { "Lima",          "PE", -12.0500f,  -77.0500f, "<-05>5",                             "America/Lima",                    -5,  0, false },
    // UTC-6
    { "Chicago",       "US",  41.8500f,  -87.6500f, "CST6CDT,M3.2.0,M11.1.0",            "America/Chicago",                 -6,  0, true  },
    { "Mexico City",   "MX",  19.4000f,  -99.1500f, "CST6",                               "America/Mexico_City",             -6,  0, false },
    // UTC-7
    { "Denver",        "US",  39.7392f, -104.9842f, "MST7MDT,M3.2.0,M11.1.0",            "America/Denver",                  -7,  0, true  },
    { "Phoenix",       "US",  33.4483f, -112.0733f, "MST7",                               "America/Phoenix",                 -7,  0, false },
    // UTC-8
    { "Los Angeles",   "US",  34.0522f, -118.2428f, "PST8PDT,M3.2.0,M11.1.0",            "America/Los_Angeles",             -8,  0, true  },
    { "Vancouver",     "CA",  49.2667f, -123.1167f, "PST8PDT,M3.2.0,M11.1.0",            "America/Vancouver",               -8,  0, false },
    // UTC-9
    { "Anchorage",     "US",  61.2181f, -149.9003f, "AKST9AKDT,M3.2.0,M11.1.0",          "America/Anchorage",               -9,  0, true  },
    // UTC-10
    { "Honolulu",      "US",  21.3069f, -157.8583f, "HST10",                              "Pacific/Honolulu",               -10,  0, true  },
};

static const uint8_t kCityCount = sizeof(kCities) / sizeof(kCities[0]);
