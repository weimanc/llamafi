#pragma once
#include "settingsSection.h"

class AppsSection : public SettingsSection {
public:
    const char* title() const override {
        static const char* kNames[] = { "Stock","Crypto","Aquarium","Matrix","Life" };
        return (_sub < 0) ? "Applications" : kNames[_sub];
    }

    void enter() override { _sub = -1; repaint(); }
    void leave() override { _sub = -1; }

    void repaint() override {
        drawHeader();
        clearContent();
        if (_sub < 0) _repaintAppList();
        else          _repaintAppRows();
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return SectionResult::Continue;
        if (isBackTap(x, y)) {
            if (_sub >= 0) { _sub = -1; repaint(); return SectionResult::Continue; }
            return SectionResult::GoBack;
        }
        if (_sub < 0) {
            int row = tapToRow(y);
            if (row >= 0 && row < 5) { _sub = (int8_t)row; repaint(); }
        } else {
            _handleAppTap(tapToRow(y));
        }
        return SectionResult::Continue;
    }

private:
    int8_t _sub = -1;

    void _repaintAppList() {
        static const char* kNames[] = { "Stock","Crypto","Aquarium","Matrix","Life" };
        int y = S_CONTENT_Y;
        for (int i = 0; i < 5; i++) { drawChevronRow(y, kNames[i]); y += S_ROW_H; }
    }

    void _repaintAppRows() {
        switch (_sub) {
            case 0: _repaintStock();    break;
            case 1: _repaintCrypto();   break;
            case 2: _repaintAquarium(); break;
            case 3: _repaintMatrix();   break;
            case 4: _repaintLife();     break;
        }
    }

    void _repaintStock() {
        int y = S_CONTENT_Y;
        for (int i = 0; i < 7; i++) {
            char lbl[12]; snprintf(lbl, sizeof(lbl), "Ticker %d", i + 1);
            drawRow(y, { lbl, settings().stockTickers[i], S_LABEL, S_VALUE });
            y += S_ROW_H;
        }
        static const char* kV[] = { "list","chart","heatmap" };
        uint8_t m = (uint8_t)settings().stockMode % 3;
        drawRow(y, { "Default view", kV[m], S_LABEL, S_VALUE });
    }

    void _repaintCrypto() {
        int y = S_CONTENT_Y;
        for (int i = 0; i < 6; i++) {
            char lbl[8]; snprintf(lbl, sizeof(lbl), "Coin %d", i + 1);
            drawRow(y, { lbl, settings().cryptoCoins[i], S_LABEL, S_VALUE });
            y += S_ROW_H;
        }
        drawRow(y, { "Currency", settings().cryptoCcy, S_LABEL, S_VALUE });
    }

    void _repaintAquarium() {
        int y = S_CONTENT_Y;
        char fbuf[4]; snprintf(fbuf, sizeof(fbuf), "%d", (int)settings().aquariumFish);
        drawRow(y, { "Fish count", fbuf, S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Speed", _speedStr(settings().aquariumSpeed), S_LABEL, S_VALUE });
    }

    void _repaintMatrix() {
        int y = S_CONTENT_Y;
        static const char* kC[] = { "green","white","amber" };
        uint8_t mc = (uint8_t)settings().matrixColor % 3;
        drawRow(y, { "Color", kC[mc], S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Speed", _speedStr(settings().matrixSpeed), S_LABEL, S_VALUE });
    }

    void _repaintLife() {
        int y = S_CONTENT_Y;
        drawRow(y, { "Speed", _speedStr(settings().lifeSpeed), S_LABEL, S_VALUE }); y += S_ROW_H;
        static const char* kSc[] = { "rainbow","mono" };
        uint8_t lc = (uint8_t)settings().lifeColors % 2;
        drawRow(y, { "Colors", kSc[lc], S_LABEL, S_VALUE });
    }

    void _handleAppTap(int row) {
        if (row < 0) return;
        switch (_sub) {
            case 0: _cycleStock(row);    break;
            case 1: _cycleCrypto(row);   break;
            case 2: _cycleAquarium(row); break;
            case 3: _cycleMatrix(row);   break;
            case 4: _cycleLife(row);     break;
        }
    }

    void _cycleStock(int row) {
        static const char* kPool[] = {
            "AAPL","AMD","AMZN","ARM","AVGO","GOOG","META","MSFT",
            "NVDA","NFLX","TSLA","SPY","QQQ","JPM","V","MA","DIS","INTC","UBER","SPOT"
        };
        static const uint8_t kSz = 20;
        if (row < 7) {
            const char* cur = settings().stockTickers[row];
            int idx = 0;
            for (uint8_t i = 0; i < kSz; i++) if (strcmp(kPool[i], cur) == 0) { idx = i; break; }
            strlcpy(settings().stockTickers[row], kPool[(idx + 1) % kSz], 8);
        } else if (row == 7) {
            settings().stockMode = (StockViewMode)(((uint8_t)settings().stockMode + 1) % 3);
        } else return;
        saveSettings(); repaint();
    }

    void _cycleCrypto(int row) {
        static const char* kPool[] = {
            "BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","MATIC","LINK","DOT","LTC"
        };
        static const uint8_t kSz = 12;
        if (row < 6) {
            const char* cur = settings().cryptoCoins[row];
            int idx = 0;
            for (uint8_t i = 0; i < kSz; i++) if (strcmp(kPool[i], cur) == 0) { idx = i; break; }
            strlcpy(settings().cryptoCoins[row], kPool[(idx + 1) % kSz], 8);
        } else if (row == 6) {
            if (strcmp(settings().cryptoCcy, "USD") == 0) strlcpy(settings().cryptoCcy, "EUR", 4);
            else strlcpy(settings().cryptoCcy, "USD", 4);
        } else return;
        saveSettings(); repaint();
    }

    void _cycleAquarium(int row) {
        static const uint8_t kFish[] = { 4, 8, 12, 16 };
        if (row == 0) {
            uint8_t cur = settings().aquariumFish; uint8_t next = kFish[0];
            for (int i = 0; i < 4; i++) if (kFish[i] == cur) { next = kFish[(i+1)%4]; break; }
            settings().aquariumFish = next;
        } else if (row == 1) {
            settings().aquariumSpeed = _cycleSpeed(settings().aquariumSpeed);
        } else return;
        saveSettings(); repaint();
    }

    void _cycleMatrix(int row) {
        if (row == 0) settings().matrixColor = (MatrixColor)(((uint8_t)settings().matrixColor + 1) % 3);
        else if (row == 1) settings().matrixSpeed = _cycleSpeed(settings().matrixSpeed);
        else return;
        saveSettings(); repaint();
    }

    void _cycleLife(int row) {
        if (row == 0) settings().lifeSpeed = _cycleSpeed(settings().lifeSpeed);
        else if (row == 1) settings().lifeColors = (LifeColors)(((uint8_t)settings().lifeColors + 1) % 2);
        else return;
        saveSettings(); repaint();
    }

    static AppSpeed _cycleSpeed(AppSpeed s) {
        return (AppSpeed)(((uint8_t)s + 1) % 3);
    }

    static const char* _speedStr(AppSpeed s) {
        switch (s) {
            case AppSpeed::Slow: return "slow";
            case AppSpeed::Fast: return "fast";
            default:             return "normal";
        }
    }
};
