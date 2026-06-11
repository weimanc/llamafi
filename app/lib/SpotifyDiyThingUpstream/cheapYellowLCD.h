#pragma once
#include "spotifyDisplay.h"

#include "touchScreen.h"

#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();

#ifndef WINAMP_DISPLAY
#include <JPEGDEC.h>
// Library for decoding Jpegs from the API responses
//
// Can be installed from the library manager (Search for "JPEGDEC")
// https://github.com/bitbank2/JPEGDEC

// -------------------------------
// Putting this stuff outside the class because
// I can't easily pass member functions in as callbacks for jpegdec

// -------------------------------

JPEGDEC jpeg;

const char *ALBUM_ART = "/album.jpg";

// This next function will be called during decoding of the jpeg file to
// render each block to the Matrix.  If you use a different display
// you will need to adapt this function to suit.
int JPEGDraw(JPEGDRAW *pDraw)
{
  // Stop further decoding as image is running off bottom of screen
  if (pDraw->y >= tft.height())
    return 0;

  tft.pushImage(pDraw->x, pDraw->y, pDraw->iWidth, pDraw->iHeight, pDraw->pPixels);
  return 1;
}

fs::File myfile;

void *myOpen(const char *filename, int32_t *size)
{
  myfile = SPIFFS.open(filename);
  *size = myfile.size();
  return &myfile;
}
void myClose(void *handle)
{
  if (myfile)
    myfile.close();
}
int32_t myRead(JPEGFILE *handle, uint8_t *buffer, int32_t length)
{
  if (!myfile)
    return 0;
  return myfile.read(buffer, length);
}
int32_t mySeek(JPEGFILE *handle, int32_t position)
{
  if (!myfile)
    return 0;
  return myfile.seek(position);
}
#endif  // !WINAMP_DISPLAY

class CheapYellowDisplay : public SpotifyDisplay
{
public:
  void displaySetup(SpotifyArduino *spotifyObj)
  {

    spotify_display = spotifyObj;

    touchSetup(spotifyObj);

    Serial.println("cyd display setup");
    setWidth(320);
    setHeight(240);

    setImageHeight(150);
    setImageWidth(150);

    // Start the tft display and set it to black
    tft.init();
    tft.setRotation(1);
    tft.fillScreen(TFT_BLACK);
  }

  void showDefaultScreen()
  {
    tft.fillScreen(TFT_BLACK);

    drawTouchButtons(false, false);
  }

  void displayTrackProgress(long progress, long duration)
  {
    if (duration <= 0) return;

    int barXWidth = map((int)((progress * 100) / duration), 0, 100, 0, screenWidth - 40);
    if (barXWidth == lastBarXWidth) return;  // poll-002: skip identical-pixel redraws

    int progressStartY = 150 + 5;
    if (lastBarXWidth < 0) {
      // First draw of this session: outer rectangle only needed once.
      tft.drawRect(19, progressStartY, screenWidth - 38, 20, TFT_WHITE);
    }

    if (barXWidth > lastBarXWidth) {
      // Extend white fill rightward.
      int x = lastBarXWidth < 0 ? 20 : 20 + lastBarXWidth;
      tft.fillRect(x, progressStartY + 1, barXWidth - (lastBarXWidth < 0 ? 0 : lastBarXWidth), 18, TFT_WHITE);
    } else {
      // Bar shrank (track changed / seek backward) — repaint full state.
      tft.fillRect(20, progressStartY + 1, barXWidth, 18, TFT_WHITE);
      tft.fillRect(20 + barXWidth, progressStartY + 1, (screenWidth - 40) - barXWidth, 18, TFT_BLACK);
    }
    lastBarXWidth = barXWidth;
  }

  void printCurrentlyPlayingToScreen(CurrentlyPlaying currentlyPlaying)
  {
    // Clear the text
    int textStartY = 150 + 30;
    tft.fillRect(0, textStartY, screenWidth, screenHeight - textStartY, TFT_BLACK);

    tft.drawCentreString(currentlyPlaying.trackName, screenCenterX, textStartY, 2);
    tft.drawCentreString(currentlyPlaying.artists[0].artistName, screenCenterX, textStartY + 18, 2);
    tft.drawCentreString(currentlyPlaying.albumName, screenCenterX, textStartY + 36, 2);
  }

  void checkForInput()
  {
    // Legacy (CYD non-Winamp) touch path. Still calls SpotifyArduino
    // synchronously here — pre-031c behaviour. The Winamp backend
    // (winampDisplay.h) uses the async enqueue path. If you ship the
    // legacy backend in production, migrate this to spotifyTask::enqueue
    // for the same safety reasons (ADR-012 race).
    if (millis() > touchScreenCoolDownTime && handleTouched())
    {
      drawTouchButtons(previousTrackStatus, nextTrackStatus);
      if (previousTrackStatus)
      {
        spotify_display->previousTrack();
      }
      else if (nextTrackStatus)
      {
        spotify_display->nextTrack();
      }
      drawTouchButtons(false, false);
      touchScreenCoolDownTime = millis() + touchScreenCoolDownInterval;
    }
  }

  // Image Related
  void clearImage()
  {
    int imagePosition = screenCenterX - (imageWidth / 2);
    tft.fillRect(imagePosition, 0, imageWidth, imageHeight, TFT_BLACK);
  }

  boolean processImageInfo(CurrentlyPlaying currentlyPlaying)
  {
#ifdef WINAMP_DISPLAY
    return false;
#else
    SpotifyImage currentlyPlayingMedImage = currentlyPlaying.albumImages[currentlyPlaying.numImages - 2];
    if (!albumDisplayed || !isSameAlbum(currentlyPlayingMedImage.url))
    {
      // We have a differenent album than we currently have displayed
      albumDisplayed = false;
      setImageHeight(currentlyPlayingMedImage.height / 2); // medium image is 300, we are going to scale it to half
      setImageWidth(currentlyPlayingMedImage.width / 2);
      setAlbumArtUrl(currentlyPlayingMedImage.url);
      return true;
    }

    return false;
#endif
  }

  int displayImage()
  {
#ifdef WINAMP_DISPLAY
    return 0;
#else
    int imageStatus = displayImageUsingFile(_albumArtUrl);
    Serial.print("imageStatus: ");
    Serial.println(imageStatus);
    if (imageStatus == 1)
    {
      albumDisplayed = true;
      return imageStatus;
    }

    return imageStatus;
#endif
  }

  // NFC tag messages
  void markDisplayAsTagRead()
  {
    int imagePosition = screenCenterX - (imageWidth / 2);
    tft.drawRect(imagePosition, 0, imageWidth, imageHeight, TFT_BLUE);
    tft.drawRect(imagePosition + 2, 2, imageWidth - 4, imageHeight - 4, TFT_RED);
  }
  void markDisplayAsTagWritten()
  {
    int imagePosition = screenCenterX - (imageWidth / 2);
    tft.drawRect(imagePosition, 0, imageWidth, imageHeight, TFT_RED);
    tft.drawRect(imagePosition + 2, 2, imageWidth - 4, imageHeight - 4, TFT_GREEN);
  }

  void drawRefreshTokenMessage()
  {
    Serial.println("Refresh Token Mode");
    tft.fillScreen(TFT_BLACK);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawCentreString("Refresh Token Mode:", screenCenterX, 5, 2);
    tft.drawString("You need to authorize this device to use", 5, 28, 2);
    tft.drawString("your spotify account.", 5, 46, 2);

    tft.drawString("Visit the following address and follow", 5, 82, 2);
    tft.drawString("the instrucitons:", 5, 100, 2);
    tft.setTextColor(TFT_BLUE, TFT_BLACK);
    tft.drawString(WiFi.localIP().toString(), 10, 128, 2);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

private:
  unsigned long touchScreenCoolDownInterval = 200; // How long after a touch press do we accept another (0.2 seconds). There is also an APi request inbetween
  unsigned long touchScreenCoolDownTime;           // time when cool down has expired
  int lastBarXWidth = -1;                          // poll-002: cached bar width for idempotent redraw

#ifndef WINAMP_DISPLAY
  int displayImageUsingFile(char *albumArtUrl)
  {

    // In this example I reuse the same filename
    // over and over, maybe saving the art using
    // the album URI as the name would be better
    // as you could save having to download them each
    // time, but this seems to work fine.
    if (SPIFFS.exists(ALBUM_ART) == true)
    {
      Serial.println("Removing existing image");
      SPIFFS.remove(ALBUM_ART);
    }

    fs::File f = SPIFFS.open(ALBUM_ART, "w+");
    if (!f)
    {
      Serial.println("file open failed");
      return -1;
    }

    // Spotify uses a different cert for the Image server, so we need to swap to that for the call
    client.setCACert(spotify_image_server_cert);
    bool gotImage = spotify_display->getImage(albumArtUrl, &f);

    // Swapping back to the main spotify cert
    client.setCACert(spotify_server_cert);

    // Make sure to close the file!
    f.close();

    if (gotImage)
    {
      return drawImagefromFile(ALBUM_ART);
    }
    else
    {
      return -2;
    }
  }

  int drawImagefromFile(const char *imageFileUri)
  {
    unsigned long lTime = millis();
    lTime = millis();
    jpeg.open((const char *)imageFileUri, myOpen, myClose, myRead, mySeek, JPEGDraw);
    jpeg.setPixelType(1);
    int imagePosition = screenCenterX - (imageWidth / 2);
    // decode will return 1 on sucess and 0 on a failure
    int decodeStatus = jpeg.decode(imagePosition, 0, JPEG_SCALE_HALF);
    // jpeg.decode(45, 0, 0);
    jpeg.close();
    Serial.print("Time taken to decode and display Image (ms): ");
    Serial.println(millis() - lTime);

    return decodeStatus;
  }
#endif  // !WINAMP_DISPLAY

  void drawTouchButtons(bool backStatus, bool forwardStatus)
  {

    int buttonCenterY = 75;
    int leftButtonCenterX = 40;
    int rightButtonCenterX = screenWidth - leftButtonCenterX;

    // Draw back Button
    tft.fillCircle(leftButtonCenterX, buttonCenterY, 16, TFT_BLACK);
    tft.drawCircle(leftButtonCenterX, buttonCenterY, 16, TFT_WHITE);
    if (backStatus)
    {
      tft.fillCircle(leftButtonCenterX, buttonCenterY, 15, TFT_GREEN);
    }
    else
    {
      tft.drawCircle(leftButtonCenterX, buttonCenterY, 15, TFT_WHITE);
    }

    tft.fillTriangle(leftButtonCenterX - 4, buttonCenterY, leftButtonCenterX + 6, buttonCenterY - 10, leftButtonCenterX + 6, buttonCenterY + 10, TFT_WHITE);
    tft.drawRect(leftButtonCenterX - 6, buttonCenterY - 10, 2, 20, TFT_WHITE);

    // Draw forward Button
    tft.fillCircle(rightButtonCenterX, buttonCenterY, 16, TFT_BLACK);
    tft.drawCircle(rightButtonCenterX, buttonCenterY, 16, TFT_WHITE);
    if (forwardStatus)
    {
      tft.fillCircle(rightButtonCenterX, buttonCenterY, 15, TFT_GREEN);
    }
    else
    {
      tft.drawCircle(rightButtonCenterX, buttonCenterY, 15, TFT_WHITE);
    }

    tft.fillTriangle(rightButtonCenterX + 4, buttonCenterY, rightButtonCenterX - 6, buttonCenterY - 10, rightButtonCenterX - 6, buttonCenterY + 10, TFT_WHITE);
    tft.drawRect(rightButtonCenterX + 6, buttonCenterY - 10, 2, 20, TFT_WHITE);
  }
};
