// appRegistry.h — canonical app list.  One row per app.
// Comment out a row to disable that app at build time.
//
// AFTER EDITING: re-run the codegen script to keep generated files in sync:
//   ~/proj/esp/venv/bin/python3 app/tools/gen_app_registry.py
// Then run check_build.sh — step [5/5] enforces staleness.
//
// Columns:  Name       icon  configurable (1 = appears in Settings > Applications)
APP_X( Spotify,   'S',   0 )
APP_X( Clock,     'C',   0 )
APP_X( Weather,   'W',   0 )
APP_X( Crypto,    '$',   1 )
APP_X( Matrix,    'M',   1 )
APP_X( Life,      'G',   1 )
APP_X( Settings,  '=',   0 )
APP_X( Stock,     'K',   1 )
APP_X( Aquarium,  '~',   1 )
APP_X( Teletext,  'T',   1 )
