#pragma once

// Bluetooth A2DP sink for the original ESP32 CYD. Audio arrives from a phone,
// is mixed to mono, level-adjusted in software, and leaves through the same
// internal DAC GPIO26 / onboard SC8002B amplifier used by WebRadio.

#include <Arduino.h>

#ifdef SERIAL_DEBUG

// The serial-DUT image already fills the ESP32's internal DRAM with test
// instrumentation. Keep its player-mode/UI coverage, but leave the large
// Bluedroid/A2DP implementation to production and cyd2usb_bluetooth_test.
namespace btSpeaker {
inline void configureBootMemory(bool) {}
}

class BluetoothSpeakerApp : public App {
public:
    void init() override { _paint(); }
    void resume() override { _paint(); }
    void suspend() override { winampDisplay.resetDragState(); }
    void tick() override { winampDisplay.tickMarquee(); }

    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase == TouchPhase::Release && winampDisplay.hitTestEject(x, y)) {
            persistPlayerMode((uint8_t)PlayerMode::Spotify);
            switchApp(AppId::Spotify);
            return true;
        }
        return false;
    }

    bool dbgGet(const char* var, char* buf, int len) const {
        if (strcmp(var, "btState") != 0) return false;
        snprintf(buf, len,
                 "\"var\":\"btState\",\"ready\":false,\"connected\":false,"
                 "\"streaming\":false,\"rate\":0,\"volume\":%u,"
                 "\"drops\":0,\"stub\":true,\"last\":true",
                 (unsigned)g_settings.bluetoothVolumePct);
        return true;
    }

private:
    void _paint() {
        winampDisplay.repaintChrome();
        winampDisplay.setTitle("Bluetooth hardware test build required");
        winampDisplay.drawVolume(g_settings.bluetoothVolumePct);
    }
};

#else

#include <esp_a2dp_api.h>
#include <esp_avrc_api.h>
#include <esp_bt.h>
#include <esp_bt_device.h>
#include <esp_bt_main.h>
#include <esp_gap_bt_api.h>
#include <driver/i2s.h>
#include <freertos/ringbuf.h>

namespace btSpeaker {

static constexpr const char* DEVICE_NAME = "LlamaFi Speaker";
static constexpr i2s_port_t I2S_PORT = I2S_NUM_0;
// Wi-Fi is off in this mode, so a compact ~35 ms PCM queue is sufficient and
// leaves the Classic Bluetooth host enough heap for packets during playback.
static constexpr size_t PCM_RING_BYTES = 6 * 1024;
static constexpr size_t PCM_PREFETCH_BYTES = 1536;

static bool s_bootMemoryAvailable = false;
static bool s_memoryReleased = false;
static volatile bool s_running = false;
static volatile bool s_connected = false;
static volatile bool s_streaming = false;
static volatile bool s_avrcConnected = false;
static volatile bool s_a2dpProfileReady = false;
static volatile bool s_audioTaskStop = false;
static volatile bool s_i2sReady = false;
static volatile bool s_uiDirty = false;
static volatile uint32_t s_sampleRate = 44100;
static volatile uint8_t s_channels = 2;
static volatile uint8_t s_volumePct = 35;
static volatile uint32_t s_droppedPackets = 0;
static volatile unsigned long s_streamStartedMs = 0;
static TaskHandle_t s_audioTask = nullptr;
static RingbufHandle_t s_pcmRing = nullptr;
static esp_bd_addr_t s_peerBda = {};
static volatile esp_a2d_connection_state_t s_connectionState =
    ESP_A2D_CONNECTION_STATE_DISCONNECTED;
static portMUX_TYPE s_stateMux = portMUX_INITIALIZER_UNLOCKED;
static constexpr size_t TITLE_CAP = 96;
static constexpr size_t ARTIST_CAP = 64;
static char* s_title = nullptr;
static char* s_artist = nullptr;
static esp_avrc_rn_evt_cap_mask_t s_peerRnCaps = {};
static uint8_t s_transactionLabel = 8;

inline const char* errName(esp_err_t err) {
    return err == ESP_OK ? "ok" : esp_err_to_name(err);
}

inline bool beginFailed(const char* step, esp_err_t err) {
    Serial.printf("[bt] ERROR step=%s err=%s heap=%u max=%u\n", step,
                  errName(err), (unsigned)ESP.getFreeHeap(),
                  (unsigned)ESP.getMaxAllocHeap());
    return false;
}

// Must be called once, after SettingsStorage::load() and before any Bluetooth
// controller init. Non-Bluetooth boots return the controller's reserved memory
// to the heap; that decision is irreversible until reboot.
inline void configureBootMemory(bool bluetoothBoot) {
    if (bluetoothBoot) {
        esp_err_t err = esp_bt_controller_mem_release(ESP_BT_MODE_BLE);
        s_bootMemoryAvailable = (err == ESP_OK || err == ESP_ERR_INVALID_STATE);
        s_memoryReleased = false;
        Serial.printf("[bt] boot memory=classic ble-release=%s\n", errName(err));
    } else {
        esp_err_t err = esp_bt_controller_mem_release(ESP_BT_MODE_BTDM);
        s_bootMemoryAvailable = false;
        s_memoryReleased = (err == ESP_OK || err == ESP_ERR_INVALID_STATE);
        Serial.printf("[bt] boot memory=released btdm-release=%s\n", errName(err));
    }
}

inline bool bootMemoryAvailable() { return s_bootMemoryAvailable && !s_memoryReleased; }
inline bool connected() { return s_connected; }
inline bool streaming() { return s_streaming; }
inline bool running() { return s_running; }
inline uint32_t droppedPackets() { return s_droppedPackets; }
inline uint32_t sampleRate() { return s_sampleRate; }

inline void updateEnvelope(int16_t left, int16_t right) {
    int32_t l = left < 0 ? -(int32_t)left : left;
    int32_t r = right < 0 ? -(int32_t)right : right;
    float targetL = l / 32768.0f;
    float targetR = r / 32768.0f;
    float &lLvl = vu::lLevelRef();
    float &rLvl = vu::rLevelRef();
    if (targetL > lLvl) lLvl += (targetL - lLvl) * vu::ATTACK;
    if (targetR > rLvl) rLvl += (targetR - rLvl) * vu::ATTACK;
}

inline void audioTask(void*) {
    bool prefetched = false;
    while (!s_audioTaskStop) {
        if (!s_pcmRing || !s_i2sReady) {
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }
        const size_t used = PCM_RING_BYTES - xRingbufferGetCurFreeSize(s_pcmRing);
        if (!prefetched && used < PCM_PREFETCH_BYTES) {
            vTaskDelay(pdMS_TO_TICKS(2));
            continue;
        }
        prefetched = true;

        size_t bytes = 0;
        uint8_t* data = static_cast<uint8_t*>(
            xRingbufferReceiveUpTo(s_pcmRing, &bytes, pdMS_TO_TICKS(10), 2048));
        if (!data || bytes == 0) {
            prefetched = false;
            continue;
        }

        // Phone A2DP streams are normally 16-bit stereo SBC. Mix them to the
        // CYD's one amplified DAC channel, apply a squared level curve for
        // usable low-volume control, then bias signed PCM to the DAC midpoint.
        if (s_channels == 2) {
            uint32_t* out = reinterpret_cast<uint32_t*>(data);
            int16_t* pcm = reinterpret_cast<int16_t*>(data);
            const size_t frames = bytes / 4;
            const int32_t gain = (int32_t)s_volumePct * (int32_t)s_volumePct;
            int32_t peakL = 0, peakR = 0;
            for (size_t i = 0; i < frames; ++i) {
                int16_t left = pcm[i * 2];
                int16_t right = pcm[i * 2 + 1];
                int32_t al = left < 0 ? -(int32_t)left : left;
                int32_t ar = right < 0 ? -(int32_t)right : right;
                if (al > peakL) peakL = al;
                if (ar > peakR) peakR = ar;
                int32_t mono = ((int32_t)left + (int32_t)right) / 2;
                mono = (mono * gain) / 10000;
                uint16_t dac = (uint16_t)(mono + 32768);
                out[i] = ((uint32_t)dac << 16) | dac;
            }
            updateEnvelope((int16_t)peakL, (int16_t)peakR);
        } else {
            // Mono negotiation is rare for phone media. I2S mono duplicates
            // one word to both DAC lanes; convert signed samples in place.
            int16_t* pcm = reinterpret_cast<int16_t*>(data);
            const size_t samples = bytes / 2;
            const int32_t gain = (int32_t)s_volumePct * (int32_t)s_volumePct;
            for (size_t i = 0; i < samples; ++i) {
                int32_t sample = ((int32_t)pcm[i] * gain) / 10000;
                pcm[i] = (int16_t)(uint16_t)(sample + 32768);
            }
        }

        size_t written = 0;
        i2s_write(I2S_PORT, data, bytes, &written, pdMS_TO_TICKS(100));
        vRingbufferReturnItem(s_pcmRing, data);
    }
    s_audioTask = nullptr;
    vTaskDelete(nullptr);
}

inline void a2dpDataCallback(const uint8_t* data, uint32_t len) {
    if (!s_running || !s_pcmRing || !data || len == 0) return;
    if (xRingbufferSend(s_pcmRing, data, len, 0) != pdTRUE) ++s_droppedPackets;
}

inline void a2dpCallback(esp_a2d_cb_event_t event, esp_a2d_cb_param_t* param) {
    if (!param) return;
    switch (event) {
        case ESP_A2D_CONNECTION_STATE_EVT:
            s_connectionState = param->conn_stat.state;
            s_connected = param->conn_stat.state == ESP_A2D_CONNECTION_STATE_CONNECTED;
            if (s_connected) memcpy(s_peerBda, param->conn_stat.remote_bda, ESP_BD_ADDR_LEN);
            if (param->conn_stat.state == ESP_A2D_CONNECTION_STATE_DISCONNECTED && s_running)
                esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
            Serial.printf("[bt] connection state=%d peer=%02x:%02x:%02x:%02x:%02x:%02x\n",
                          (int)param->conn_stat.state,
                          param->conn_stat.remote_bda[0], param->conn_stat.remote_bda[1],
                          param->conn_stat.remote_bda[2], param->conn_stat.remote_bda[3],
                          param->conn_stat.remote_bda[4], param->conn_stat.remote_bda[5]);
            s_uiDirty = true;
            break;
        case ESP_A2D_AUDIO_STATE_EVT:
            s_streaming = param->audio_stat.state == ESP_A2D_AUDIO_STATE_STARTED;
            if (s_streaming) s_streamStartedMs = millis();
            Serial.printf("[bt] audio state=%d\n", (int)param->audio_stat.state);
            s_uiDirty = true;
            break;
        case ESP_A2D_AUDIO_CFG_EVT:
            if (param->audio_cfg.mcc.type == ESP_A2D_MCT_SBC) {
                uint8_t oct0 = param->audio_cfg.mcc.cie.sbc[0];
                uint32_t rate = (oct0 & (1 << 6)) ? 32000
                              : (oct0 & (1 << 5)) ? 44100
                              : (oct0 & (1 << 4)) ? 48000 : 16000;
                uint8_t channels = (oct0 & (1 << 3)) ? 1 : 2;
                s_sampleRate = rate;
                s_channels = channels;
                if (s_i2sReady)
                    i2s_set_clk(I2S_PORT, rate, I2S_BITS_PER_SAMPLE_16BIT,
                                channels == 1 ? I2S_CHANNEL_MONO : I2S_CHANNEL_STEREO);
                Serial.printf("[bt] stream format=%luHz channels=%u\n",
                              (unsigned long)rate, (unsigned)channels);
                s_uiDirty = true;
            }
            break;
        case ESP_A2D_PROF_STATE_EVT:
            s_a2dpProfileReady =
                param->a2d_prof_stat.init_state == ESP_A2D_INIT_SUCCESS;
            Serial.printf("[bt] a2dp profile=%s\n",
                          s_a2dpProfileReady ? "ready" : "stopped");
            break;
        default:
            break;
    }
}

inline void requestTrackMetadata() {
    if (!s_avrcConnected) return;
    esp_avrc_ct_send_metadata_cmd(1,
        ESP_AVRC_MD_ATTR_TITLE | ESP_AVRC_MD_ATTR_ARTIST);
}

inline void registerNotification(uint8_t eventId, uint8_t label) {
    if (esp_avrc_rn_evt_bit_mask_operation(ESP_AVRC_BIT_MASK_OP_TEST,
                                           &s_peerRnCaps,
                                           (esp_avrc_rn_event_ids_t)eventId)) {
        esp_avrc_ct_send_register_notification_cmd(label, eventId, 0);
    }
}

inline void avrcCallback(esp_avrc_ct_cb_event_t event, esp_avrc_ct_cb_param_t* param) {
    if (!param) return;
    switch (event) {
        case ESP_AVRC_CT_CONNECTION_STATE_EVT:
            s_avrcConnected = param->conn_stat.connected;
            Serial.printf("[bt] avrc connected=%d\n", s_avrcConnected ? 1 : 0);
            if (s_avrcConnected) {
                esp_avrc_ct_send_get_rn_capabilities_cmd(0);
                requestTrackMetadata();
            }
            s_uiDirty = true;
            break;
        case ESP_AVRC_CT_GET_RN_CAPABILITIES_RSP_EVT:
            s_peerRnCaps = param->get_rn_caps_rsp.evt_set;
            registerNotification(ESP_AVRC_RN_TRACK_CHANGE, 2);
            registerNotification(ESP_AVRC_RN_PLAY_STATUS_CHANGE, 3);
            break;
        case ESP_AVRC_CT_CHANGE_NOTIFY_EVT:
            if (param->change_ntf.event_id == ESP_AVRC_RN_TRACK_CHANGE) {
                requestTrackMetadata();
                registerNotification(ESP_AVRC_RN_TRACK_CHANGE, 2);
            } else if (param->change_ntf.event_id == ESP_AVRC_RN_PLAY_STATUS_CHANGE) {
                registerNotification(ESP_AVRC_RN_PLAY_STATUS_CHANGE, 3);
            }
            s_uiDirty = true;
            break;
        case ESP_AVRC_CT_METADATA_RSP_EVT: {
            char* dst = nullptr;
            size_t cap = 0;
            if (param->meta_rsp.attr_id == ESP_AVRC_MD_ATTR_TITLE) {
                dst = s_title; cap = TITLE_CAP;
            } else if (param->meta_rsp.attr_id == ESP_AVRC_MD_ATTR_ARTIST) {
                dst = s_artist; cap = ARTIST_CAP;
            }
            if (dst && cap) {
                size_t n = min((size_t)param->meta_rsp.attr_length, cap - 1);
                portENTER_CRITICAL(&s_stateMux);
                memcpy(dst, param->meta_rsp.attr_text, n);
                dst[n] = '\0';
                portEXIT_CRITICAL(&s_stateMux);
                s_uiDirty = true;
            }
            break;
        }
        case ESP_AVRC_CT_PASSTHROUGH_RSP_EVT:
            Serial.printf("[bt] avrc response key=%u state=%u\n",
                          (unsigned)param->psth_rsp.key_code,
                          (unsigned)param->psth_rsp.key_state);
            break;
        default:
            break;
    }
}

inline void gapCallback(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t* param) {
    if (!param) return;
    if (event == ESP_BT_GAP_CFM_REQ_EVT) {
        esp_bt_gap_ssp_confirm_reply(param->cfm_req.bda, true);
    } else if (event == ESP_BT_GAP_PIN_REQ_EVT) {
        esp_bt_pin_code_t pin = {'1', '2', '3', '4'};
        esp_bt_gap_pin_reply(param->pin_req.bda, true, 4, pin);
    }
}

inline esp_err_t installI2s() {
    i2s_config_t cfg = {};
    cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_DAC_BUILT_IN);
    cfg.sample_rate = 44100;
    cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
    cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
    cfg.communication_format = I2S_COMM_FORMAT_STAND_MSB;
    cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
    cfg.dma_buf_count = 6;
    cfg.dma_buf_len = 192;
    cfg.use_apll = false;
    // Built-in DAC silence is 0x8000, not literal zero; keeping the last
    // descriptor prevents rail pops if Bluetooth briefly underruns.
    cfg.tx_desc_auto_clear = false;
    cfg.fixed_mclk = 0;
    esp_err_t err = i2s_driver_install(I2S_PORT, &cfg, 0, nullptr);
    if (err != ESP_OK) return err;
    err = i2s_set_dac_mode(I2S_DAC_CHANNEL_LEFT_EN);
    if (err != ESP_OK) {
        i2s_driver_uninstall(I2S_PORT);
        return err;
    }
    // Do not call i2s_set_pin(..., nullptr) here. On the original ESP32 that
    // selects the built-in DAC pin route again and claims both DAC GPIOs;
    // GPIO25 is also the CYD touchscreen clock. i2s_set_dac_mode(LEFT) above
    // is sufficient and deliberately leaves GPIO25 under digital control.
    s_i2sReady = true;

    uint32_t silence[64];
    for (uint32_t &frame : silence) frame = 0x80008000UL;
    size_t written = 0;
    for (int i = 0; i < 8; ++i)
        i2s_write(I2S_PORT, silence, sizeof(silence), &written, pdMS_TO_TICKS(20));
    return ESP_OK;
}

inline bool begin() {
    if (s_running) return true;
    if (!bootMemoryAvailable()) return false;

    s_volumePct = g_settings.bluetoothVolumePct;
    s_connected = false;
    s_connectionState = ESP_A2D_CONNECTION_STATE_DISCONNECTED;
    s_streaming = false;
    s_avrcConnected = false;
    s_a2dpProfileReady = false;
    s_droppedPackets = 0;
    if (!s_title) s_title = static_cast<char*>(calloc(TITLE_CAP, 1));
    if (!s_artist) s_artist = static_cast<char*>(calloc(ARTIST_CAP, 1));
    if (s_title) s_title[0] = '\0';
    if (s_artist) s_artist[0] = '\0';
    memset(&s_peerRnCaps, 0, sizeof(s_peerRnCaps));

    esp_err_t err;
    esp_bt_controller_config_t btCfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    // BLE memory was released at boot, so the controller configuration must
    // describe a Classic-only instance. Leaving the generated BTDM default
    // here makes esp_bt_controller_enable(CLASSIC_BT) reject the config.
    btCfg.mode = ESP_BT_MODE_CLASSIC_BT;
    btCfg.ble_max_conn = 0;
    err = esp_bt_controller_init(&btCfg);
    if (err != ESP_OK) return beginFailed("controller-init", err);
    if ((err = esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT)) != ESP_OK)
        return beginFailed("controller-enable", err);
    if ((err = esp_bluedroid_init()) != ESP_OK) return beginFailed("bluedroid-init", err);
    if ((err = esp_bluedroid_enable()) != ESP_OK) return beginFailed("bluedroid-enable", err);

    esp_bt_gap_register_callback(gapCallback);
    esp_bt_dev_set_device_name(DEVICE_NAME);
    esp_bt_io_cap_t iocap = ESP_BT_IO_CAP_NONE;
    esp_bt_gap_set_security_param(ESP_BT_SP_IOCAP_MODE, &iocap, sizeof(iocap));

    esp_avrc_ct_register_callback(avrcCallback);
    if ((err = esp_avrc_ct_init()) != ESP_OK) return beginFailed("avrc-init", err);
    esp_a2d_register_callback(a2dpCallback);
    esp_a2d_sink_register_data_callback(a2dpDataCallback);
    if ((err = esp_a2d_sink_init()) != ESP_OK) return beginFailed("a2dp-init", err);
    {
        unsigned long deadline = millis() + 1000;
        while (!s_a2dpProfileReady && millis() < deadline) delay(5);
        if (!s_a2dpProfileReady) return beginFailed("a2dp-ready", ESP_ERR_TIMEOUT);
    }

    // Reserve Bluetooth/controller packet pools first, then allocate the
    // replaceable audio queue and DMA storage from the remaining heap. This
    // prevents display/audio allocations fragmenting the blocks Bluedroid
    // needs while its host task starts.
    if ((err = installI2s()) != ESP_OK) return beginFailed("i2s", err);
    s_pcmRing = xRingbufferCreate(PCM_RING_BYTES, RINGBUF_TYPE_BYTEBUF);
    if (!s_pcmRing) return beginFailed("ring", ESP_ERR_NO_MEM);
    s_audioTaskStop = false;
    if (xTaskCreatePinnedToCore(audioTask, "btAudio", 1536, nullptr,
                                configMAX_PRIORITIES - 3, &s_audioTask, 1) != pdPASS)
        return beginFailed("audio-task", ESP_ERR_NO_MEM);

    s_running = true;
    s_uiDirty = true;
    esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
    Serial.printf("[bt] ready name=\"%s\" heap=%u max=%u\n", DEVICE_NAME,
                  (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());
    return true;
}

inline void stopAndRelease() {
    if (!s_running && !s_bootMemoryAvailable) return;
    s_running = false;
    s_streaming = false;
    esp_bt_gap_set_scan_mode(ESP_BT_NON_CONNECTABLE, ESP_BT_NON_DISCOVERABLE);

    // Stop the PCM consumer before dismantling the callbacks that feed it.
    s_audioTaskStop = true;
    unsigned long deadline = millis() + 300;
    while (s_audioTask && millis() < deadline) delay(5);
    if (s_pcmRing) { vRingbufferDelete(s_pcmRing); s_pcmRing = nullptr; }
    if (s_i2sReady) {
        i2s_stop(I2S_PORT);
        i2s_driver_uninstall(I2S_PORT);
        s_i2sReady = false;
    }

    if (s_connectionState == ESP_A2D_CONNECTION_STATE_CONNECTED ||
        s_connectionState == ESP_A2D_CONNECTION_STATE_CONNECTING) {
        esp_a2d_sink_disconnect(s_peerBda);
    }
    // DISCONNECTING is not disconnected: deinitializing the state machine
    // while its final callback is queued leaves btc_av_cb.sm_handle null and
    // crashes btc_a2dp_cb_handler. Wait for the terminal event explicitly.
    deadline = millis() + 2000;
    while (s_connectionState != ESP_A2D_CONNECTION_STATE_DISCONNECTED &&
           millis() < deadline) delay(10);
    if (s_connectionState != ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
        Serial.printf("[bt] WARN disconnect timeout state=%d; restarting safely\n",
                      (int)s_connectionState);
        Serial.flush();
        ESP.restart();
        return;
    }

    if (s_a2dpProfileReady) {
        esp_a2d_sink_deinit();
        deadline = millis() + 1000;
        while (s_a2dpProfileReady && millis() < deadline) delay(5);
        if (s_a2dpProfileReady) {
            Serial.println("[bt] WARN profile deinit timeout; restarting safely");
            Serial.flush();
            ESP.restart();
            return;
        }
    }
    esp_avrc_ct_deinit();
    delay(30);
    if (esp_bluedroid_get_status() == ESP_BLUEDROID_STATUS_ENABLED)
        esp_bluedroid_disable();
    if (esp_bluedroid_get_status() == ESP_BLUEDROID_STATUS_INITIALIZED)
        esp_bluedroid_deinit();
    if (esp_bt_controller_get_status() == ESP_BT_CONTROLLER_STATUS_ENABLED)
        esp_bt_controller_disable();
    if (esp_bt_controller_get_status() == ESP_BT_CONTROLLER_STATUS_INITED)
        esp_bt_controller_deinit();

    free(s_title); s_title = nullptr;
    free(s_artist); s_artist = nullptr;

    esp_err_t releaseErr = esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT);
    s_bootMemoryAvailable = false;
    s_memoryReleased = true;
    Serial.printf("[bt] stopped classic-release=%s heap=%u max=%u\n",
                  errName(releaseErr), (unsigned)ESP.getFreeHeap(),
                  (unsigned)ESP.getMaxAllocHeap());
}

inline void setVolume(int pct) {
    s_volumePct = (uint8_t)constrain(pct, 0, 100);
    g_settings.bluetoothVolumePct = s_volumePct;
}

inline void sendPassthrough(esp_avrc_pt_cmd_t cmd) {
    if (!s_avrcConnected) {
        Serial.printf("[bt] control ignored key=%u avrc=disconnected\n", (unsigned)cmd);
        return;
    }
    uint8_t pressLabel = s_transactionLabel++ & 0x0F;
    esp_err_t pressErr = esp_avrc_ct_send_passthrough_cmd(
        pressLabel, cmd, ESP_AVRC_PT_CMD_STATE_PRESSED);
    // Press and release are separate AVRCP transactions. Give the peer time
    // to consume the press and use a fresh label so the second command cannot
    // collide with an outstanding response on slower phones.
    delay(35);
    uint8_t releaseLabel = s_transactionLabel++ & 0x0F;
    esp_err_t releaseErr = esp_avrc_ct_send_passthrough_cmd(
        releaseLabel, cmd, ESP_AVRC_PT_CMD_STATE_RELEASED);
    Serial.printf("[bt] control key=%u press=%s release=%s\n", (unsigned)cmd,
                  errName(pressErr), errName(releaseErr));
}

inline bool takeUiDirty() {
    bool dirty = s_uiDirty;
    s_uiDirty = false;
    return dirty;
}

inline void copyDisplayTitle(char* out, size_t cap) {
    if (!out || cap == 0) return;
    char title[TITLE_CAP];
    char artist[ARTIST_CAP];
    portENTER_CRITICAL(&s_stateMux);
    strlcpy(title, s_title ? s_title : "", sizeof(title));
    strlcpy(artist, s_artist ? s_artist : "", sizeof(artist));
    portEXIT_CRITICAL(&s_stateMux);
    if (title[0] && artist[0]) snprintf(out, cap, "%s - %s   ", artist, title);
    else if (title[0]) snprintf(out, cap, "%s   ", title);
    else if (s_connected) strlcpy(out, "Connected - play Spotify on phone", cap);
    else strlcpy(out, "Pair phone with LlamaFi Speaker", cap);
}

} // namespace btSpeaker

class BluetoothSpeakerApp : public App {
public:
    void init() override {
        winampDisplay.setVolumeSink(_volumeSink);
        if (!btSpeaker::bootMemoryAvailable()) {
            winampDisplay.setTitle("Restarting for Bluetooth...");
            delay(120);
            ESP.restart();
            return;
        }
        _failed = !btSpeaker::begin();
        _paintFull();
    }

    void resume() override {
        winampDisplay.setVolumeSink(_volumeSink);
        if (!btSpeaker::bootMemoryAvailable()) {
            winampDisplay.setTitle("Restarting for Bluetooth...");
            delay(120);
            ESP.restart();
            return;
        }
        if (!btSpeaker::running()) _failed = !btSpeaker::begin();
        _paintFull();
    }

    void suspend() override {
        winampDisplay.resetDragState();
        btSpeaker::stopAndRelease();
    }

    void tick() override {
        winampDisplay.tickMarquee();
        if (btSpeaker::takeUiDirty()) _paintDynamic();
        const bool playing = btSpeaker::streaming();
        const long elapsed = playing
            ? (long)(millis() - btSpeaker::s_streamStartedMs) : 0L;
        vu::tick(winampDisplay.chromeOriginX(), winampDisplay.chromeOriginY(),
                 SKIN_MAIN_BG, playing, elapsed, true);
        if (playing) winampDisplay.updateTimeDigits((int)((elapsed / 1000) % 6000));
    }

    bool handleInput(TouchPhase phase, int x, int y) override {
#ifdef BLUETOOTH_TEST_BOOT
        if (phase != TouchPhase::Move)
            Serial.printf("[bt] touch phase=%u x=%d y=%d\n",
                          (unsigned)phase, x, y);
#endif
        if (winampDisplay.handleVolumeGesturePublic(phase, x, y)) return true;
        if (phase != TouchPhase::Release) return false;
        if (winampDisplay.hitTestEject(x, y)) {
            g_settings.bluetoothVolumePct = btSpeaker::s_volumePct;
            persistPlayerMode((uint8_t)PlayerMode::Spotify);
            btSpeaker::stopAndRelease();
            delay(80);
            ESP.restart();
            return true;
        }
        int transport = winampDisplay.hitTestTransportPublic(x, y);
        if (transport == 0) btSpeaker::sendPassthrough(ESP_AVRC_PT_CMD_BACKWARD);
        else if (transport == 1 || transport == 2)
            btSpeaker::sendPassthrough(btSpeaker::streaming()
                ? ESP_AVRC_PT_CMD_PAUSE : ESP_AVRC_PT_CMD_PLAY);
        else if (transport == 3) btSpeaker::sendPassthrough(ESP_AVRC_PT_CMD_STOP);
        else if (transport == 4) btSpeaker::sendPassthrough(ESP_AVRC_PT_CMD_FORWARD);
        else return false;
        return true;
    }

    bool isConnecting() const override {
        return btSpeaker::running() && !btSpeaker::connected();
    }
    bool hasError() const override { return _failed; }

    bool dbgGet(const char* var, char* buf, int len) const {
        if (strcmp(var, "btState") != 0) return false;
        snprintf(buf, len,
                 "\"var\":\"btState\",\"ready\":%s,\"connected\":%s,"
                 "\"streaming\":%s,\"rate\":%u,\"volume\":%u,"
                 "\"drops\":%u,\"heap\":%u,\"maxAlloc\":%u,\"last\":true",
                 btSpeaker::running() ? "true" : "false",
                 btSpeaker::connected() ? "true" : "false",
                 btSpeaker::streaming() ? "true" : "false",
                 (unsigned)btSpeaker::sampleRate(),
                 (unsigned)g_settings.bluetoothVolumePct,
                 (unsigned)btSpeaker::droppedPackets(),
                 (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());
        return true;
    }

private:
    bool _failed = false;

    static void _volumeSink(int pct) {
        btSpeaker::setVolume(pct);
    }

    void _paintDynamic() {
        char title[180];
        btSpeaker::copyDisplayTitle(title, sizeof(title));
        winampDisplay.setTitle(_failed ? "Bluetooth failed - restart" : title);
        winampDisplay.setStatusIndicator(btSpeaker::streaming() ? PP_PLAY
                                         : (btSpeaker::connected() ? PP_PAUSE : PP_STOP));
        _drawInfo();
    }

    void _paintFull() {
        winampDisplay.repaintChrome();
        winampDisplay.drawVolume(g_settings.bluetoothVolumePct);
        winampDisplay.drawBufferBar(btSpeaker::connected() ? 100 : 0);
        _paintDynamic();
    }

    void _drawInfo() {
        winampDisplay.drawPleditFrame(0, 5);
        winampDisplay.drawEqPanelState(false);
        winampDisplay.drawPleditOverlayText("BT");
        static const char* kRows[] = {
            "BLUETOOTH SPEAKER",
            "PHONE: SETTINGS > BLUETOOTH",
            "PAIR: LLAMAFI SPEAKER",
            "OUTPUT: GPIO26 / ONBOARD AMP",
            "OTHER BT SPEAKER: SELECT ON PHONE",
        };
        for (int row = 0; row < 5; ++row) {
            int y = PLEDIT_ROWS_Y + row * PLEDIT_ROW_H;
            uint16_t bg = PLEDIT_BODY_BG;
            tft.fillRect(PLEDIT_CONTENT_X, y, PLEDIT_CONTENT_W, PLEDIT_ROW_H, bg);
            tft.setTextColor(row == 0 ? 0xFFFFU : (uint16_t)PLEDIT_FG_NORMAL, bg);
            tft.drawString(kRows[row], PLEDIT_CONTENT_X + 3, y + 2, 1);
        }
    }
};

#endif // SERIAL_DEBUG
