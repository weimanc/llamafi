# pr_parse_trial — M-PLANERADAR phase 0 (docs/architecture/designs/M-PLANERADAR/phase0-parse-heap.md)
# ArduinoJson single header is vendored, pinned to the device version (platformio.ini: ^6.21.3).
# Fetch once:  make ArduinoJson-v6.21.3.h
# Header sha256 recorded below after first fetch — verify on re-fetch.
AJ_URL = https://github.com/bblanchon/ArduinoJson/releases/download/v6.21.3/ArduinoJson-v6.21.3.h

pr_parse_trial: main.cpp ArduinoJson-v6.21.3.h
	g++ -std=c++17 -O2 -Wall -Wextra -o $@ main.cpp

ArduinoJson-v6.21.3.h:
	curl -fsSL -o $@ $(AJ_URL)
	sha256sum $@

clean:
	rm -f pr_parse_trial

.PHONY: clean
