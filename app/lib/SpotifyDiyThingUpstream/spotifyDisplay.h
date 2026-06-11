#ifndef SPOTIFYDISPLAY_H
#define SPOTIFYDISPLAY_H

#include <stdint.h>

class SpotifyDisplay {
  public:
    virtual void displaySetup(SpotifyArduino *spotifyObj) = 0;

    virtual void showDefaultScreen() = 0;

    // Track related
    virtual void displayTrackProgress(long progress, long duration) = 0;
    virtual void printCurrentlyPlayingToScreen(CurrentlyPlaying currentlyPlaying) = 0;

    //Probably Touch screen related
    virtual void checkForInput() =0;

    //Image Related
    virtual void clearImage()= 0;
    virtual boolean processImageInfo (CurrentlyPlaying currentlyPlaying)=0;
    virtual int displayImage() = 0;

    //NFC tag messages
    virtual void markDisplayAsTagRead() = 0;
    virtual void markDisplayAsTagWritten() = 0;

    virtual void drawRefreshTokenMessage() = 0;

    // chrome-001 / TASK-041 — VOLUME slider (Winamp renderer only).
    // Default no-op for displays without volume chrome (CYD legacy,
    // matrix). Negative percent = sentinel ("no active device").
    // -2 sentinel from getLastVolumeRendered() = "never rendered".
    virtual void drawVolume(int /*percent*/) {}
    virtual int8_t getLastVolumeRendered() const { return -2; }

    // chrome-001 / TASK-045 — optimistic-UI freeze (ADR-016 §10).
    // While a volume drag is in progress (or recently ended), the
    // touch path wants to suppress snap-driven drawVolume calls so
    // the next regular poll's stale volumePercent doesn't re-anchor
    // the slider over the user's chosen position. Returns the
    // millis() deadline; spotifyLogic checks `now < deadline` to
    // skip the dedup gate. Default 0 = never freeze.
    virtual unsigned long getOptimisticVolumeUntil() const { return 0; }

    // chrome-001 final — shuffle / repeat indicators (Winamp renderer
    // only). Default no-op for displays without these toggles.
    // shuffleState: 0/1; repeatState: RepeatOptions encoding
    // (0=track, 1=context, 2=off). Sentinel -1 / 3 in the cache means
    // "never rendered" so the first repaint always fires.
    virtual void drawShuffle(int /*on*/) {}
    virtual void drawRepeat(int /*state*/) {}
    virtual int8_t getLastShuffleRendered() const { return -1; }
    virtual int8_t getLastRepeatRendered()  const { return  3; }
    virtual unsigned long getOptimisticShufRepUntil() const { return 0; }

    // serialdbg-001 / TASK-056n (ADR-021 A1) — debug owner-dispatch.
    // Compiled only in SERIAL_DEBUG builds. Default no-ops so non-Winamp
    // backends compile unchanged. WinampDisplay overrides both.
#ifdef SERIAL_DEBUG
#include "debugExportable.h"
    virtual bool dbgGet(const char* var, char* buf, int len) const {
      (void)var; (void)buf; (void)len; return false;
    }
    virtual bool dbgSet(const char* var, const char* val) {
      (void)var; (void)val; return false;
    }
    // Touch injection points (ADR-021 AC-2 resolution). Skips ts.touched()
    // / ts.getPointScaled(); called from drainInjectionQueue / cmdTap.
    // Must be called from the loop task only. WinampDisplay overrides both.
    virtual void injectTouch(int /*sx*/, int /*sy*/) {}
    virtual void injectRelease() {}
#endif

    void setAlbumArtUrl(const char* albumArtUrl){
      strcpy(_albumArtUrl, albumArtUrl);
    }

    char* getAlbumArtUrl(){
      return _albumArtUrl;
    }

    bool isSameAlbum(const char* albumArtUrl){
      return strcmp(_albumArtUrl, albumArtUrl) == 0;
    }

    void setWidth(int w) {
      screenWidth = w;
      screenCenterX = screenWidth / 2;
    }

    void setHeight(int h) {
      screenHeight = h;
    }

    void setImageHeight(int h) {
      imageHeight = h;
    }

    void setImageWidth(int w) {
      imageWidth = w;
    }

  protected:
    int screenWidth;
    int screenHeight;
    int screenCenterX;
    int imageWidth;
    int imageHeight;
    SpotifyArduino *spotify_display;
    char _albumArtUrl[200];
    boolean albumDisplayed = false;
};
#endif
