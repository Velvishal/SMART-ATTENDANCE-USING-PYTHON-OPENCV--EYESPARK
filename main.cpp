#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <U8g2lib.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ====== CAMERA CONFIGURATION ======
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"

// ====== PIN DEFINITIONS ======
#define FLASH_PIN 4
#define BUZZER_PIN 13
#define I2C_SDA 14
#define I2C_SCL 15
#define RED_LED_PIN 2
#define GREEN_LED_PIN 12

// ====== TIMER DEFINITIONS ======
#define SCAN_INTERVAL_MS 20000  // 20 seconds
#define WIFI_TIMEOUT_MS 60000   // 1 minute (60,000 ms)
#define SLEEP_SERVER_DOWN_SEC 30 // 30 seconds
#define SLEEP_WIFI_DOWN_SEC 60   // 60 seconds

// ====== WiFi Configuration ======
const char* ssid = "VELVISHAL REDMI";
const char* password = "Latha203";
// This is your correct STATIC IP address
const char* upload_url = "http://10.13.180.140:5000/upload"; 

// ====== OLED Setup ======
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, I2C_SCL, I2C_SDA);

// ====== Helper: Display Message ======
void showMessage(const char* line1, const char* line2 = "") {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_7x13B_tr);
  u8g2.drawStr(0, 25, line1);
  u8g2.drawStr(0, 45, line2);
  u8g2.sendBuffer();
}

// ====== Tone Functions ======
void playTone(int f, int d) { tone(BUZZER_PIN, f, d); delay(d); noTone(BUZZER_PIN); }
void playSuccessTone() { playTone(1500, 100); playTone(1800, 150); }
void playErrorTone() { playTone(400, 200); playTone(200, 300); }
void playWakeTone() { playTone(1200, 150); playTone(1600, 150); playTone(2000, 200); }

// ====== CAMERA SETUP FUNCTION ======
bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 10;
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;
  
  return (esp_camera_init(&config) == ESP_OK);
}

// ====== GO TO DEEP SLEEP ======
void goToSleep(int sleepSeconds, const char* sleepMsg) {
  showMessage(sleepMsg, "Sleeping...");
  delay(1000);
  
  // Configure the timer to wake us up
  esp_sleep_enable_timer_wakeup(sleepSeconds * 1000000);
  Serial.printf("Going to sleep for %d seconds...\n", sleepSeconds);
  esp_deep_sleep_start();
}

// ====== ATTENDANCE CAPTURE (Called in a loop) ======
bool runAttendanceScan() {
  // Re-initialize the camera to ensure it's awake
  esp_camera_deinit();
  delay(100);
  if (!initCamera()) {
    showMessage("Cam Re-Init Fail");
    playErrorTone();
    delay(2000);
    return true; // Return true to continue the loop, don't sleep
  }
  delay(100); // Give sensor time to stabilize

  showMessage("Scanning...");
  
  digitalWrite(FLASH_PIN, HIGH);
  delay(300);
  camera_fb_t *fb = esp_camera_fb_get();
  digitalWrite(FLASH_PIN, LOW);

  if (!fb) {
    showMessage("Capture Failed");
    playErrorTone();
    return true; // Continue the loop
  }

  showMessage("Uploading...");
  HTTPClient http;
  http.begin(upload_url);
  http.addHeader("Content-Type", "image/jpeg");
  int code = http.POST(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  if (code > 0) {
    String payload = http.getString();
    Serial.println(payload);
    showMessage("Result:", payload.c_str()); 
    
    if (payload == "UNKNOWN") {
      playErrorTone();
      for (int i = 0; i < 3; i++) { // Blink Red LED
        digitalWrite(RED_LED_PIN, HIGH); delay(100);
        digitalWrite(RED_LED_PIN, LOW); delay(100);
      }
    } else if (payload == "TIME LIMIT REACHED") {
      // Server is on, but time is up. Just display.
      playErrorTone();
    } else {
      // This is a known person
      playSuccessTone();
      for (int i = 0; i < 3; i++) { // Blink Green LED
        digitalWrite(GREEN_LED_PIN, HIGH); delay(100);
        digitalWrite(GREEN_LED_PIN, LOW); delay(100);
      }
    }
  } else {
    // This is the CRITICAL failure case
    Serial.print("HTTP Error code: ");
    Serial.println(code);
    showMessage("SERVER ENDED"); // Display "SERVER ENDED"
    playErrorTone();
    http.end();
    return false; // Return false to signal a server failure
  }
  
  http.end();
  delay(2000); // Show result on OLED
  return true; // Return true to signal success
}

// ====== SETUP ======
void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Disable brownout
  Serial.begin(115200);
  
  pinMode(FLASH_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  
  u8g2.begin();
  playWakeTone();
  
  // Show the splash screen on every wake up
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_7x13B_tr);
  u8g2.drawStr(14, 28, "MSEC SMART");
  u8g2.drawStr(18, 48, "ATTENDANCE");
  u8g2.sendBuffer();
  delay(3000);

  showMessage("Connecting WiFi...");
  WiFi.begin(ssid, password);
  
  // --- NEW: 1-Minute WiFi Timeout ---
  unsigned long startAttemptTime = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < WIFI_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nWiFi connection FAILED.");
    showMessage("WIFI OFFLINE");
    playErrorTone();
    // Go to sleep for 60 seconds
    goToSleep(SLEEP_WIFI_DOWN_SEC, "WIFI OFFLINE");
  }
  // --- END of Timeout ---

  Serial.println("\nWiFi Connected!");
  
  if (!initCamera()) {
    showMessage("Camera Init FAILED");
  } else {
    showMessage("WiFi OK", "Starting Scan...");
  }
}

// ====== LOOP (AUTOMATED) ======
void loop() {
  
  // 1. Run the attendance scan
  bool serverIsOnline = runAttendanceScan(); 

  if (serverIsOnline) {
    // 2. If scan was successful, display waiting message
    showMessage("Waiting 20s...");
    Serial.println("Waiting 20 seconds...");
    delay(SCAN_INTERVAL_MS);
  } 
  else {
    // 3. If scan FAILED (server is down), go to 30-second sleep
    Serial.println("Server is offline. Going to sleep for 30 sec...");
    goToSleep(SLEEP_SERVER_DOWN_SEC, "SERVER ENDED");
  }
}