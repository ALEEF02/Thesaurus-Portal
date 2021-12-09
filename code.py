import board
import busio
import time
import os
from digitalio import DigitalInOut
import adafruit_requests as requests
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_pyportal import PyPortal
from adafruit_button import Button
import adafruit_touchscreen
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
#import adafruit_sdcard

# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise

# LOGGING DEFS
CRIT = 1
WARNINGS = 2
INFO = 3
VERBOSE = 4

LOGGING_LEVEL = INFO # Set logging level

cwd = ("/"+__file__).rsplit('/', 1)[0]

# Using random word API https://github.com/mskian/vue-random-words
RANDOM_WORD_URL = "https://san-random-words.vercel.app/"
RANDOM_WORD_URL_BACKUP = "https://random-words-api.vercel.app/word"
W_LOCATION = [0, 'word']
P_LOCATION = [0, 'pronunciation']
D_LOCATION = [0, 'definition']

# CONSTANTS
# Settings
WORDS_PER_BATCH = 5 # How many words to pull for each batch
TIME_PER_WORD = 30 # Seconds that a word should be on screen before continuing to next word. Repeated BATCH_REPETITIONS times
BATCH_REPETITIONS = 9 # How many times to re-show the current batch of words before pulling a new batch
# Each word is shown for TIME_PER_WORD * BATCH_REPETITIONS seconds. Default is 270 seconds, or 4 and a half minutes

AUDIO_DIR = "/sd/audio" # Directory on the MicroSD where we'll store pronunciations
AUDIO_CLEANUP = False   # Save space on audio files where possible. Shouldn't be necessary. Most WAVs of pronunciations from MW are ~10 KB, so on a 32 GB MicroSD, that's 3.2 million before you run out of space.
EMPTY_AUDIO_DIR = False # Set to True to empty the contents of the AUDIO_DIR on boot. Debug only
USE_VOICERSS = True     # Use VoiceRSS instead of MW

ERROR_DELAY = 10 # Seconds to wait until retry after an error
# End Settings

STRING_PUNCT = "!"#$%&'()*+, -./:;<=>?@[\]^_`{|}~"
ALL_PRONUNCIATION_LOCATIONS = ['hwi','uros','ahws','cats','dros','ins','ri','sdsense','sen','sense','vrs']

if LOGGING_LEVEL >= INFO: print("ESP32 SPI webclient boot")

# If you are using a board with pre-defined ESP32 Pins (PyPortal, etc.):
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

# If you have an AirLift Shield:
# esp32_cs = DigitalInOut(board.D10)
# esp32_ready = DigitalInOut(board.D7)
# esp32_reset = DigitalInOut(board.D5)

# If you have an AirLift Featherwing or ItsyBitsy Airlift:
# esp32_cs = DigitalInOut(board.D13)
# esp32_ready = DigitalInOut(board.D11)
# esp32_reset = DigitalInOut(board.D12)

# If you have an externally connected ESP32:
# NOTE: You may need to change the pins to reflect your wiring
# esp32_cs = DigitalInOut(board.D9)
# esp32_ready = DigitalInOut(board.D10)
# esp32_reset = DigitalInOut(board.D5)

spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

requests.set_socket(socket, esp)

if esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
    if LOGGING_LEVEL >= INFO: print("ESP32 found and in idle mode")
else:
    print("ESP32 not found!!")
    raise
if LOGGING_LEVEL >= INFO: print("Firmware vers.", esp.firmware_version)
if LOGGING_LEVEL >= VERBOSE: print("MAC addr:", [hex(i) for i in esp.MAC_address_actual])

for ap in esp.scan_networks():
    if LOGGING_LEVEL >= VERBOSE:
        print("%s\n(%s) RSSI: %d  Ch: %d  Enc: %s" % (str(ap["ssid"], "utf-8"), [hex(i) for i in ap["bssid"]], ap["rssi"], ap["channel"], ap["encryption"]))
    elif LOGGING_LEVEL >= INFO:
        print("%s RSSI: %d" % (str(ap["ssid"], "utf-8"), ap["rssi"]))

if LOGGING_LEVEL >= INFO: print("Connecting to AP...")
# esp._debug = True
while not esp.is_connected:
    try:
        esp.connect_AP(secrets["ssid"], secrets["password"], 15)
    except RuntimeError as e:
        if LOGGING_LEVEL >= WARNINGS: print("Could not connect to AP, retrying: ", e)
        continue
if LOGGING_LEVEL >= INFO: print("Connected to", str(esp.ssid, "utf-8"), "\tRSSI:", esp.rssi)
if LOGGING_LEVEL >= INFO: print("My IP address is", esp.pretty_ip(esp.ip_address))
if LOGGING_LEVEL >= INFO: 
    print(
        "IP lookup adafruit.com: %s" % esp.pretty_ip(esp.get_host_by_name("adafruit.com"))
    )
if LOGGING_LEVEL >= INFO: print("Ping google.com: %d ms" % esp.ping("google.com"))

# Backlight function
# Value between 0 and 1 where 0 is OFF, 0.5 is 50% and 1 is 100% brightness.
def set_backlight(val):
    val = max(0, min(1.0, val))  # Smart way of confining a value to bounds!
    board.DISPLAY.auto_brightness = False
    board.DISPLAY.brightness = val

# Set the Backlight Manually
#set_backlight(0.3)

# Define the TouchScreen
ts = adafruit_touchscreen.Touchscreen(board.TOUCH_XL, board.TOUCH_XR,
                                      board.TOUCH_YD, board.TOUCH_YU,
                                      calibration=((5200, 59000), (5800, 57000)),
                                      size=(320, 240))

# Define FONTS and COLORS
LARGE_FONT = bitmap_font.load_font("/fonts/Helvetica-Bold-100.bdf")
SMALL_FONT = bitmap_font.load_font("/fonts/HelveticaNeue-24.bdf")
TINY_FONT = bitmap_font.load_font("/fonts/Arial-ItalicMT-17.bdf")
WHITE = 0xFFFFFF

# Create labels
word_position = (25, 50)
word_text_area = label.Label(SMALL_FONT, x=word_position[0], y=word_position[1],
                          color=WHITE, line_spacing = 1, scale = 2)

pron_position = (25, 100)
pron_text_area = label.Label(SMALL_FONT, x=pron_position[0], y=pron_position[1],
                          color=WHITE, line_spacing = 1)

def_position = (25, 120)
def_text_area = label.Label(SMALL_FONT, x=def_position[0], y=def_position[1],
                          color=WHITE, line_spacing = 1)

# Create pronunciation button
BUTTON_HEIGHT = 40
BUTTON_WIDTH = 40
button_sound = Button(x=int(310-BUTTON_WIDTH), y=int(pron_position[1] - (BUTTON_HEIGHT / 2)), # Places button inline with pronunciation with a 10 pixel margin from the right
                      width=BUTTON_WIDTH, height=BUTTON_HEIGHT,
                      label="I3", label_font=SMALL_FONT, label_color=0x000000,
                      fill_color=0xFFFF00, outline_color=WHITE,
                      selected_fill=0x5a5a5a, selected_outline=0xff6600,
                      selected_label=0x525252, style=Button.ROUNDRECT)

pyportal = PyPortal(url=RANDOM_WORD_URL,
                    esp=esp,
                    external_spi=spi,
                    json_path=(W_LOCATION, P_LOCATION, D_LOCATION),
                    status_neopixel=board.NEOPIXEL,
                    default_bg=cwd+"/media/back2.bmp")
                    
# Check to see if we have an SD inserted AND that we've made the directory for audio
if pyportal.sd_check():
    try:
        os.listdir(AUDIO_DIR)
        if LOGGING_LEVEL >= INFO: print("SD with AUDIO_DIR found")
        if LOGGING_LEVEL >= VERBOSE: print(os.listdir(AUDIO_DIR))
        if EMPTY_AUDIO_DIR:
            if LOGGING_LEVEL >= INFO: print("FLAG SET TO EMPTY AUDIO_DIR!")
            for file in os.listdir(AUDIO_DIR):
                os.remove(AUDIO_DIR + "/" + file)
            if LOGGING_LEVEL >= INFO: print(os.listdir(AUDIO_DIR))
    except OSError as error:
        if LOGGING_LEVEL >= INFO: print("SD with no AUDIO_DIR inserted, making directory")
        os.mkdir(AUDIO_DIR) # Make the directory for storing audio

text_hight = label.Label(SMALL_FONT, text="M", color=0x03AD31)
# Return a reformatted string with word wrapping using PyPortal.wrap_nicely
def text_box(target, top, string_orig, max_chars):
    text = pyportal.wrap_nicely(string_orig, max_chars)
    new_text = ""
    test = ""
    for w in text:
        new_text += '\n'+w
        test += 'M\n'
    text_hight.text = test  # Odd things happen without this
    glyph_box = text_hight.bounding_box
    target.text = ""  # Odd things happen without this
    target.y = top
    target.text = new_text

pyportal.preload_font() # speed things up by preloading font

# Add UI objects to PyPortal
pyportal.splash.append(word_text_area)
pyportal.splash.append(pron_text_area)
pyportal.splash.append(def_text_area)
pyportal.splash.append(button_sound)

lastRotate = time.time()
    
def make_vrss_audio_url(word):
    return "https://api.voicerss.org/?key=" + secrets["voicerss_key"] + "&hl=en-us&src=" + word

def make_mw_info_url(word):  # In accordance to https://www.dictionaryapi.com/products/api-collegiate-dictionary
    return "https://www.dictionaryapi.com/api/v3/references/collegiate/json/" + word + "?key=" + secrets["mw_key"]
    
def make_mw_audio_url(audio):  # In accordance to https://www.dictionaryapi.com/products/json#sec-2.prs
    subdir = audio[0]
    if LOGGING_LEVEL >= VERBOSE: print("Making audio url... subdir to start:", subdir)
    if audio.startswith('bix'):
        subdir = 'bix'
    if audio.startswith('gg'):
        subdir = 'gg'
    if (audio[0].isdigit() or audio[0] in STRING_PUNCT):
        subdir = 'number'
    if LOGGING_LEVEL >= VERBOSE: print("subdir to send:", subdir)
    return "https://media.merriam-webster.com/audio/prons/en/us/wav/" + subdir + "/" + audio + ".wav"

while True:
    words = []
    if LOGGING_LEVEL >= INFO: print("Getting next batch...")
    for wordnum in range(WORDS_PER_BATCH):
        while True:
            try:
                down = pyportal.fetch()
                if LOGGING_LEVEL >= INFO: print(down)
                words.append(down)
                break
            except RuntimeError as e:
                print("Some error occured, retrying! -", e)
                continue
            except ValueError as e:
                if LOGGING_LEVEL >= WARNINGS: print("ValueError occured, retrying! -", e)
                text_box(def_text_area, def_position[1], "Error getting words - API failiure...", 25)
                TEMP_URL = RANDOM_WORD_URL
                RANDOM_WORD_URL = RANDOM_WORD_URL_BACKUP
                RANDOM_WORD_URL_BACKUP = TEMP_URL
                pyportal.url=RANDOM_WORD_URL
                time.sleep(ERROR_DELAY)
                continue
        
    if LOGGING_LEVEL >= INFO: print("Done recieving batch!")
    
    """ OLD, but still a good reference, so leaving here in the mean time.
    print("Fetching json from", RANDOM_WORD_URL)
    r = requests.get(RANDOM_WORD_URL)
    print("-" * 40)
    print(r.json())
    print("-" * 40)
    r.close()
    """
    
    for i in range(BATCH_REPETITIONS):
        for value in words:
            lastRotate = time.time()
            word_text_area.font = SMALL_FONT
            word_text_area.scale = 2
            if button_sound.label != "I3":
                button_sound.label = "I3"
                button_sound.fill_color = 0xFFFF00
            if (len(value[0]) > 10):
                word_text_area.font = TINY_FONT
                word_text_area.scale = 2
            elif (len(value[0]) > 14):
                word_text_area.font = SMALL_FONT
                word_text_area.scale = 1
            word_text_area.text = value[0]
            pron_text_area.text = value[1]
            text_box(def_text_area, def_position[1], value[2], 25)
            #def_text_area.text = value[2]
            
            while (time.time() < lastRotate + TIME_PER_WORD):
                touch = ts.touch_point
                if touch:
                    if button_sound.contains(touch):
                        if LOGGING_LEVEL >= VERBOSE: print("Sound button pressed")
                        if not pyportal.sd_check(): # Check for MicroSD for storing WAVs
                            if button_sound.label != "X":
                                if LOGGING_LEVEL >= WARNINGS: print("No SD inserted, not going to get sound!") # Print first time as a warning
                                button_sound.label = "X"
                                button_sound.fill_color = 0xFF0000
                            elif LOGGING_LEVEL >= VERBOSE: print("No SD inserted, not going to get sound!") # Print afterwards as verbose
                            continue
                        try:
                            tmp = open(AUDIO_DIR + "/" + value[0] + ".wav", "r") # Check to see if we haven't downloaded this pronunciation in the past
                            tmp.close()
                            if LOGGING_LEVEL >= INFO: print("We already have the pronunciation for", value[0], ", playing it")
                        except OSError as error:
                            button_sound.label = "..."
                            MW_WORD_URL = make_mw_info_url(value[0])
                            AUDIO_URL = "NONE"
                            if not USE_VOICERSS:
                                if LOGGING_LEVEL >= INFO: print("Fetching MW info from", MW_WORD_URL)
                                r = requests.get(MW_WORD_URL)
                                if LOGGING_LEVEL >= INFO:
                                    print("-" * 40)
                                    print(r.json())
                                    print("-" * 40)
                                
                                try:
                                    r.json()[0]['hwi']
                                except Exception as e:
                                    if LOGGING_LEVEL >= WARNINGS: print("MW doesn't have info on '", value[0], "'! Going with '", r.json()[0], "' instead - ", e)
                                    MW_WORD_URL = make_mw_info_url(r.json()[0])
                                    if LOGGING_LEVEL >= INFO: print("Fetching MW info from", MW_WORD_URL)
                                    r = requests.get(MW_WORD_URL)
                                    if LOGGING_LEVEL >= INFO:
                                        print("-" * 40)
                                        print(r.json())
                                        print("-" * 40)
                                        
                                if LOGGING_LEVEL >= VERBOSE:
                                    print(len(r.json()))
                                    print(range(len(r.json())))
                                for ind in range(len(ALL_PRONUNCIATION_LOCATIONS)):
                                    for word in range(len(r.json())):
                                        try:
                                            if LOGGING_LEVEL >= VERBOSE: print('ind', ind, 'word', word, 'pronun lookup', ALL_PRONUNCIATION_LOCATIONS[ind])
                                            AUDIO_URL = make_mw_audio_url(r.json()[word][ALL_PRONUNCIATION_LOCATIONS[ind]]['prs'][0]['sound']['audio'])
                                            if LOGGING_LEVEL >= VERBOSE: print("Pronunciation found under", ALL_PRONUNCIATION_LOCATIONS[ind])
                                            break
                                        except KeyError as e:
                                            if LOGGING_LEVEL >= VERBOSE: print("No pronunciation found under", ALL_PRONUNCIATION_LOCATIONS[ind])
                                    if AUDIO_URL != "NONE":
                                        break
                                
                                r.close()
                                if AUDIO_URL == "NONE":
                                    if button_sound.label != "X":
                                        if LOGGING_LEVEL >= WARNINGS: print("No pronunciation for", value[0], "!")
                                        button_sound.label = "X"
                                        button_sound.fill_color = 0xFF0000
                                    continue
                            else:
                                AUDIO_URL = make_vrss_audio_url(value[0])
                                
                            if LOGGING_LEVEL >= INFO: print("Fetching WAV from", AUDIO_URL)
                            r = requests.get(AUDIO_URL)
                            """
                            if LOGGING_LEVEL >= INFO:
                                length_rt = 0
                                for chunk in r.iter_content(1024):
                                    # Prevent filling of the RAM with our WAV file
                                    length_rt += len(chunk)
                                print("Recieved", length_rt, "byte response")
                            """
                            writer = open(AUDIO_DIR + "/" + value[0] + '.wav', 'wb')
                            for chunk in r.iter_content(1024):
                                writer.write(chunk)
                            writer.close()
                            r.close()
                        
                        button_sound.label = "o))"
                        try:
                            pyportal.play_file(AUDIO_DIR + "/" + value[0] + ".wav")
                            button_sound.label = "I3"
                            if AUDIO_CLEANUP: os.remove(AUDIO_DIR + "/" + value[0] + '.wav')
                        except ValueError as e: # PyPortal just doesn't like this file for some reason... nothing we can do about it besides free up the space it was taking :/
                            print("Error playing file!\n\n", e)
                            button_sound.label = "?"
                            button_sound.fill_color = 0xFF0000
                            if AUDIO_CLEANUP: os.remove(AUDIO_DIR + "/" + value[0] + ".wav")