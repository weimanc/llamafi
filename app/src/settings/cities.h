#pragma once
// cities.h — city/timezone picker data for TimeSection.
//
// Source: /usr/share/zoneinfo/zone1970.tab (tzdata); POSIX strings extracted
// from TZif v2 file footers. Coordinates in decimal degrees (WGS84).
// Sorted alphabetically by city name.

#include <Arduino.h>

struct CityEntry {
    const char* city;
    const char* country;   // ISO 3166-1 alpha-2
    float       lat;
    float       lon;
    const char* posixTz;   // POSIX tz rule — passed to configTzTime()
    const char* tzName;    // display name, e.g. "Europe/London"
};

static const CityEntry kCities[] = {
    { "Anchorage",    "US", 61.2181f, -149.9003f, "AKST9AKDT,M3.2.0,M11.1.0",            "America/Anchorage"               },
    { "Amsterdam",    "NL", 52.3667f,    4.9000f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Amsterdam"                },
    { "Athens",       "GR", 37.9667f,   23.7167f, "EET-2EEST,M3.5.0/3,M10.5.0/4",        "Europe/Athens"                   },
    { "Auckland",     "NZ",-36.8667f,  174.7667f, "NZST-12NZDT,M9.5.0,M4.1.0/3",         "Pacific/Auckland"                },
    { "Baghdad",      "IQ", 33.3500f,   44.4167f, "<+03>-3",                              "Asia/Baghdad"                    },
    { "Bangkok",      "TH", 13.7500f,  100.5167f, "<+07>-7",                              "Asia/Bangkok"                    },
    { "Berlin",       "DE", 52.5000f,   13.3667f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Berlin"                   },
    { "Bogota",       "CO",  4.6000f,  -74.0833f, "<-05>5",                               "America/Bogota"                  },
    { "Brisbane",     "AU",-27.4667f,  153.0333f, "AEST-10",                              "Australia/Brisbane"              },
    { "Brussels",     "BE", 50.8333f,    4.3333f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Brussels"                 },
    { "Bucharest",    "RO", 44.4333f,   26.1000f, "EET-2EEST,M3.5.0/3,M10.5.0/4",        "Europe/Bucharest"                },
    { "Budapest",     "HU", 47.5000f,   19.0833f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Budapest"                 },
    { "Buenos Aires", "AR",-34.6000f,  -58.4500f, "<-03>3",                               "America/Argentina/Buenos_Aires"  },
    { "Cairo",        "EG", 30.0500f,   31.2500f, "EET-2EEST,M4.5.5/0,M10.5.4/24",       "Africa/Cairo"                    },
    { "Caracas",      "VE", 10.5000f,  -66.9333f, "<-04>4",                               "America/Caracas"                 },
    { "Casablanca",   "MA", 33.6500f,   -7.5833f, "<+01>-1",                              "Africa/Casablanca"               },
    { "Chicago",      "US", 41.8500f,  -87.6500f, "CST6CDT,M3.2.0,M11.1.0",              "America/Chicago"                 },
    { "Colombo",      "LK",  6.9333f,   79.8500f, "<+0530>-5:30",                         "Asia/Colombo"                    },
    { "Denver",       "US", 39.7392f, -104.9842f, "MST7MDT,M3.2.0,M11.1.0",              "America/Denver"                  },
    { "Dhaka",        "BD", 23.7167f,   90.4167f, "<+06>-6",                              "Asia/Dhaka"                      },
    { "Dubai",        "AE", 25.3000f,   55.3000f, "<+04>-4",                              "Asia/Dubai"                      },
    { "Helsinki",     "FI", 60.1667f,   24.9667f, "EET-2EEST,M3.5.0/3,M10.5.0/4",        "Europe/Helsinki"                 },
    { "Honolulu",     "US", 21.3069f, -157.8583f, "HST10",                                "Pacific/Honolulu"                },
    { "Istanbul",     "TR", 41.0167f,   28.9667f, "<+03>-3",                              "Europe/Istanbul"                 },
    { "Jakarta",      "ID", -6.1667f,  106.8000f, "WIB-7",                                "Asia/Jakarta"                    },
    { "Johannesburg", "ZA",-26.2500f,   28.0000f, "SAST-2",                               "Africa/Johannesburg"             },
    { "Karachi",      "PK", 24.8667f,   67.0500f, "PKT-5",                                "Asia/Karachi"                    },
    { "Kathmandu",    "NP", 27.7167f,   85.3167f, "<+0545>-5:45",                         "Asia/Kathmandu"                  },
    { "Kolkata",      "IN", 22.5333f,   88.3667f, "IST-5:30",                             "Asia/Kolkata"                    },
    { "Kuala Lumpur", "MY",  3.1667f,  101.7000f, "<+08>-8",                              "Asia/Kuala_Lumpur"               },
    { "Kyiv",         "UA", 50.4333f,   30.5167f, "EET-2EEST,M3.5.0/3,M10.5.0/4",        "Europe/Kiev"                     },
    { "Lagos",        "NG",  6.4500f,    3.4000f, "WAT-1",                                "Africa/Lagos"                    },
    { "Lima",         "PE",-12.0500f,  -77.0500f, "<-05>5",                               "America/Lima"                    },
    { "Lisbon",       "PT", 38.7167f,   -9.1333f, "WET0WEST,M3.5.0/1,M10.5.0",           "Europe/Lisbon"                   },
    { "London",       "GB", 51.5083f,   -0.1253f, "GMT0BST,M3.5.0/1,M10.5.0",            "Europe/London"                   },
    { "Los Angeles",  "US", 34.0522f, -118.2428f, "PST8PDT,M3.2.0,M11.1.0",              "America/Los_Angeles"             },
    { "Madrid",       "ES", 40.4000f,   -3.6833f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Madrid"                   },
    { "Manila",       "PH", 14.5867f,  120.9678f, "PST-8",                                "Asia/Manila"                     },
    { "Mexico City",  "MX", 19.4000f,  -99.1500f, "CST6",                                 "America/Mexico_City"             },
    { "Moscow",       "RU", 55.7558f,   37.6178f, "MSK-3",                                "Europe/Moscow"                   },
    { "Nairobi",      "KE", -1.2833f,   36.8167f, "EAT-3",                                "Africa/Nairobi"                  },
    { "New York",     "US", 40.7142f,  -74.0064f, "EST5EDT,M3.2.0,M11.1.0",              "America/New_York"                },
    { "Oslo",         "NO", 59.9167f,   10.7500f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Oslo"                     },
    { "Paris",        "FR", 48.8667f,    2.3333f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Paris"                    },
    { "Perth",        "AU",-31.9500f,  115.8500f, "AWST-8",                               "Australia/Perth"                 },
    { "Phoenix",      "US", 33.4483f, -112.0733f, "MST7",                                 "America/Phoenix"                 },
    { "Prague",       "CZ", 50.0833f,   14.4333f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Prague"                   },
    { "Riyadh",       "SA", 24.6333f,   46.7167f, "<+03>-3",                              "Asia/Riyadh"                     },
    { "Rome",         "IT", 41.9000f,   12.4833f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Rome"                     },
    { "Santiago",     "CL",-33.4500f,  -70.6667f, "<-04>4<-03>,M9.1.6/24,M4.1.6/24",     "America/Santiago"                },
    { "Sao Paulo",    "BR",-23.5333f,  -46.6167f, "<-03>3",                               "America/Sao_Paulo"               },
    { "Seoul",        "KR", 37.5500f,  126.9667f, "KST-9",                                "Asia/Seoul"                      },
    { "Shanghai",     "CN", 31.2333f,  121.4667f, "CST-8",                                "Asia/Shanghai"                   },
    { "Singapore",    "SG",  1.2833f,  103.8500f, "<+08>-8",                              "Asia/Singapore"                  },
    { "Stockholm",    "SE", 59.3333f,   18.0500f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Stockholm"                },
    { "Suva",         "FJ",-18.1333f,  178.4167f, "<+12>-12",                             "Pacific/Fiji"                    },
    { "Sydney",       "AU",-33.8667f,  151.2167f, "AEST-10AEDT,M10.1.0,M4.1.0/3",        "Australia/Sydney"                },
    { "Taipei",       "TW", 25.0500f,  121.5000f, "CST-8",                                "Asia/Taipei"                     },
    { "Tehran",       "IR", 35.6667f,   51.4333f, "<+0330>-3:30",                         "Asia/Tehran"                     },
    { "Tokyo",        "JP", 35.6544f,  139.7447f, "JST-9",                                "Asia/Tokyo"                      },
    { "Toronto",      "CA", 43.6500f,  -79.3833f, "EST5EDT,M3.2.0,M11.1.0",              "America/Toronto"                 },
    { "UTC",          "",    0.0000f,    0.0000f, "UTC0",                                  "UTC"                             },
    { "Vancouver",    "CA", 49.2667f, -123.1167f, "PST8PDT,M3.2.0,M11.1.0",              "America/Vancouver"               },
    { "Vladivostok",  "RU", 43.1667f,  131.9333f, "<+10>-10",                             "Asia/Vladivostok"                },
    { "Warsaw",       "PL", 52.2500f,   21.0000f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Warsaw"                   },
    { "Yangon",       "MM", 16.7833f,   96.1667f, "<+0630>-6:30",                         "Asia/Yangon"                     },
    { "Zurich",       "CH", 47.3833f,    8.5333f, "CET-1CEST,M3.5.0,M10.5.0/3",          "Europe/Zurich"                   },
};

static const uint8_t kCityCount = sizeof(kCities) / sizeof(kCities[0]);
