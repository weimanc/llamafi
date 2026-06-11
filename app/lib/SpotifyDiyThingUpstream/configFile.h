#include "secret.h"

#define SPOTIFY_CONFIG_JSON "/spotify_diy_config.json"

#define REFRESH_TOKEN_LABEL "refreshToken"
#define CLIENT_ID_LABEL "clientId"
#define CLIENT_SECRET_LABEL "clientSecret"

bool fetchConfigFile(char *refreshToken, char *clientId, char *clientSecret) {
  if (SPIFFS.exists(SPOTIFY_CONFIG_JSON)) {
    //file exists, reading and loading
    Serial.println("reading config file");
    File configFile = SPIFFS.open(SPOTIFY_CONFIG_JSON, "r");
    if (configFile) {
      Serial.println("opened config file");
      StaticJsonDocument<512> json;
      DeserializationError error = deserializeJson(json, configFile);
      // Do NOT serialize the parsed JSON to Serial — it contains the refresh
      // token and client secret. ADR-010 / TASK-016b. Print redacted summaries
      // after extraction instead.
      if (!error) {
        Serial.println("parsed json");

        if (json.containsKey(REFRESH_TOKEN_LABEL)) {
          strcpy(refreshToken, json[REFRESH_TOKEN_LABEL]);
        }

        if (json.containsKey(CLIENT_ID_LABEL) && json.containsKey(CLIENT_SECRET_LABEL)) {
          strcpy(clientId, json[CLIENT_ID_LABEL]);
          strcpy(clientSecret, json[CLIENT_SECRET_LABEL]);
        } else {
          Serial.println("Config missing client ID or Secret");
          return false;
        }

        Serial.printf("config loaded: clientId=%s clientSecret=%s refreshToken=%s\n",
                      redact(clientId), redact(clientSecret), redact(refreshToken));
        return true;

      } else {
        Serial.println("failed to load json config");
        return false;
      }
    } else {
      Serial.println("Failed to open config file");
      return false;
    }
  } else {
    Serial.println("Config file does not exist");
    return false;
  }
}

void saveConfigFile(char *refreshToken, char *clientId, char *clientSecret) {
  Serial.println(F("Saving config"));
  StaticJsonDocument<512> json;
  json[REFRESH_TOKEN_LABEL] = refreshToken;
  json[CLIENT_ID_LABEL] = clientId;
  json[CLIENT_SECRET_LABEL] = clientSecret;

  File configFile = SPIFFS.open(SPOTIFY_CONFIG_JSON, "w");
  if (!configFile) {
    Serial.println("failed to open config file for writing");
  }

  // Do NOT serialize JSON to Serial here either — same reason as fetchConfigFile.
  if (serializeJson(json, configFile) == 0) {
    Serial.println(F("Failed to write to file"));
  } else {
    Serial.printf("config saved: clientId=%s clientSecret=%s refreshToken=%s\n",
                  redact(clientId), redact(clientSecret), redact(refreshToken));
  }
  configFile.close();
}
