#pragma once
#include <time.h>
#include "settingsSection.h"
#include "cities.h"
#include "../settingsStorage.h"

enum class TimeView : uint8_t { Main, CityPicker };

class TimeSection : public SettingsSection {
public:
    const char* title() const override {
        return (_view == TimeView::CityPicker) ? "Select city" : "Time & Location";
    }

    void enter() override {
        _view       = TimeView::Main;
        _cityOffset = 0;
        repaint();
    }

    void leave() override {}
    void tick()  override {}

    void repaint() override {
        drawHeader();
        clearContent();
        if (_view == TimeView::Main) _repaintMain();
        else                          _repaintPicker();
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return SectionResult::Continue;
        if (isBackTap(x, y)) {
            if (_view == TimeView::CityPicker) {
                _view = TimeView::Main;
                repaint();
                return SectionResult::Continue;
            }
            return SectionResult::GoBack;
        }
        if (_view == TimeView::Main) _handleMainTap(x, y);
        else                          _handlePickerTap(x, y);
        return SectionResult::Continue;
    }

private:
    TimeView _view       = TimeView::Main;
    uint8_t  _cityOffset = 0;

    static constexpr uint8_t  kPickerRows = 6;
    static constexpr int16_t  kSbX        = 257;
    static constexpr int16_t  kSbW        =  18;
    static constexpr int16_t  kRowW       = 256;
    static constexpr int16_t  kSbUpY0     = S_CONTENT_Y;
    static constexpr int16_t  kSbUpY1     = S_CONTENT_Y + 20;
    static constexpr int16_t  kSbDnY0     = 220;
    static constexpr int16_t  kSbDnY1     = 240;

    void _repaintMain() {
        int y = S_CONTENT_Y;

        // "Location" sub-header
        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(S_SUBHDR);
        tft.drawString("Location", S_COL_LABEL, y + 4, 2);
        tft.drawFastHLine(S_COL_LABEL, y + S_ROW_HDR_H - 1, S_CANVAS_W - S_COL_LABEL, S_SEP);
        y += S_ROW_HDR_H;

        // City row with chevron
        int cityRowY = y;
        drawChevronRow(y, "City");
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(S_VALUE);
        tft.drawString(g_settings.city[0] ? g_settings.city : "None",
                       S_COL_VALUE - 14, y + S_ROW_H / 2, 2);
        tft.setTextDatum(TL_DATUM);
        y += S_ROW_H;

        // Separator
        drawSep(y); y += 4;

        // "Clock & Date" sub-header
        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(S_SUBHDR);
        tft.drawString("Clock & Date", S_COL_LABEL, y + 4, 2);
        tft.drawFastHLine(S_COL_LABEL, y + S_ROW_HDR_H - 1, S_CANVAS_W - S_COL_LABEL, S_SEP);
        y += S_ROW_HDR_H;

        // Timezone (read-only)
        drawRow(y, { "Timezone",
                     g_settings.tzName[0] ? g_settings.tzName : "UTC",
                     S_LABEL, S_VALUE });
        y += S_ROW_H;

        // Clock format
        drawRow(y, { "Clock", g_settings.fmt24h ? "24h" : "12h",
                     S_LABEL, S_VALUE_ON });
        y += S_ROW_H;

        // Date format
        static const char* kFmt[] = { "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD" };
        uint8_t df = (uint8_t)g_settings.dateFmt % 3;
        drawRow(y, { "Date", kFmt[df], S_LABEL, S_VALUE_ON });
        (void)cityRowY;
    }

    void _handleMainTap(int /*x*/, int py) {
        // Row y positions (must mirror _repaintMain layout)
        int cityRowY = S_CONTENT_Y + S_ROW_HDR_H;
        int sepY     = cityRowY + S_ROW_H;
        int clockBase = sepY + 4 + S_ROW_HDR_H;  // after sep(4px) + subheader
        // clockBase = timezone row (read-only)
        // clockBase + S_ROW_H = Clock row
        // clockBase + 2*S_ROW_H = Date row

        if (py >= cityRowY && py < cityRowY + S_ROW_H) {
            _view = TimeView::CityPicker;
            repaint();
            return;
        }
        if (py >= clockBase + S_ROW_H && py < clockBase + 2 * S_ROW_H) {
            g_settings.fmt24h = !g_settings.fmt24h;
            saveSettings();
            repaint();
            return;
        }
        if (py >= clockBase + 2 * S_ROW_H && py < clockBase + 3 * S_ROW_H) {
            g_settings.dateFmt = (DateFmt)(((uint8_t)g_settings.dateFmt + 1) % 3);
            saveSettings();
            repaint();
        }
    }

    void _repaintPicker() {
        _drawScrollbar();
        int y = S_CONTENT_Y;
        uint8_t end = (uint8_t)min((int)_cityOffset + kPickerRows, (int)kCityCount);
        for (uint8_t i = _cityOffset; i < end; i++) {
            bool cur = (strncmp(kCities[i].city, g_settings.city,
                                sizeof(g_settings.city) - 1) == 0);
            int mid = y + S_ROW_H / 2;
            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(S_LABEL);
            tft.drawString(kCities[i].city, S_COL_LABEL, mid, 2);
            tft.setTextDatum(MR_DATUM);
            tft.setTextColor(cur ? S_VALUE_ON : S_VALUE_OFF);
            tft.drawString(kCities[i].country, kRowW - 4, mid, 2);
            tft.setTextDatum(TL_DATUM);
            y += S_ROW_H;
        }
    }

    void _handlePickerTap(int px, int py) {
        if (px >= kSbX) {
            if (py >= kSbUpY0 && py < kSbUpY1 && _cityOffset > 0) {
                _cityOffset--;
                repaint();
            } else if (py >= kSbDnY0 && py < kSbDnY1 &&
                       _cityOffset + kPickerRows < kCityCount) {
                _cityOffset++;
                repaint();
            }
            return;
        }
        int row = (py - S_CONTENT_Y) / S_ROW_H;
        if (row < 0 || row >= kPickerRows) return;
        uint8_t idx = _cityOffset + (uint8_t)row;
        if (idx >= kCityCount) return;
        _selectCity(idx);
    }

    void _selectCity(uint8_t idx) {
        strlcpy(g_settings.city,     kCities[idx].city,    sizeof(g_settings.city));
        strlcpy(g_settings.tzName,   kCities[idx].tzName,  sizeof(g_settings.tzName));
        strlcpy(g_settings.posixTz,  kCities[idx].posixTz, sizeof(g_settings.posixTz));
        g_settings.lat = kCities[idx].lat;
        g_settings.lon = kCities[idx].lon;
        configTzTime(g_settings.posixTz,
                     "pool.ntp.org", "time.google.com", "time.cloudflare.com");
        saveSettings();
        _view = TimeView::Main;
        repaint();
    }

    void _drawScrollbar() {
        tft.fillRect(kSbX, S_CONTENT_Y, kSbW, S_CONTENT_H, S_SEP);

        // ▲ button
        tft.fillRect(kSbX, kSbUpY0, kSbW, 20, S_BG);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_LABEL);
        tft.drawString("^", kSbX + kSbW / 2, kSbUpY0 + 10, 2);

        // ▼ button
        tft.fillRect(kSbX, kSbDnY0, kSbW, 20, S_BG);
        tft.drawString("v", kSbX + kSbW / 2, kSbDnY0 + 10, 2);
        tft.setTextDatum(TL_DATUM);

        // Thumb
        int trackY0 = kSbUpY1 + 2;
        int trackH  = kSbDnY0 - trackY0 - 2;
        if (kCityCount > kPickerRows && trackH > 0) {
            int thumbH = max(8, trackH * kPickerRows / (int)kCityCount);
            int thumbY = trackY0;
            if (kCityCount > kPickerRows)
                thumbY = trackY0 + (_cityOffset * (trackH - thumbH))
                         / (kCityCount - kPickerRows);
            tft.fillRect(kSbX + 3, thumbY, kSbW - 6, thumbH, S_VALUE);
        }
    }
};
