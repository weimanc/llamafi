// appRegistry.h — canonical app list.  One row per app.
// Comment out a row to disable that app at build time.
//
// AFTER EDITING: re-run the codegen script to keep generated files in sync:
//   ~/proj/esp/venv/bin/python3 app/tools/gen_app_registry.py
// Then run check_build.sh — step [5/5] enforces staleness.
//
// NEW APP? Run the integration checklist before closing the milestone:
//   docs/architecture/designs/NEW-APP-CHECKLIST.md
// Key checks: hasPendingAsync(), tlsYield/tlsResume, dbgGet/dbgSet, cmdTap busy propagation.
//
// Columns:  Name       icon  configurable (1 = appears in Settings > Applications)  display-name
// display-name (col 4): the label shown in Settings > Applications. Usually the same
// as Name; differs for the player slot — AppId stays Spotify, but the slot hosts both
// Spotify and WebRadio modes (M-PLAYER-STATE / TASK-260), so it shows as "Winamp".
APP_X( Spotify,   'S',   1, "Winamp"   )
APP_X( Clock,     'C',   1, "Clock"    )
APP_X( Weather,   'W',   0, "Weather"  )
APP_X( Crypto,    '$',   1, "Crypto"   )
APP_X( Matrix,    'M',   1, "Matrix"   )
APP_X( Life,      'G',   1, "Life"     )
APP_X( Settings,  '=',   0, "Settings" )
APP_X( Stock,     'K',   1, "Stock"    )
APP_X( Aquarium,  '~',   1, "Aquarium" )
APP_X( Teletext,  'T',   1, "Teletext" )
APP_X( PlaneRadar,'P',   1, "PlaneRadar" )
APP_X( WebRadio,  'R',   0, "WebRadio" )
