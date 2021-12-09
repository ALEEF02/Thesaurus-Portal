# Thesaurus-Portal

A small project for school that I whipped up that pulls random words from the dictionary and displays them on intervals. Very similar to a 'word of the day', but in batches and customizable intervals. Click the 'ear' button to get a pronunciation of the word. *Example runs can be found in [the media folder](media/)*

## Setup
### secrets.py
In the `secrets.py` file there are 4 fields which need to be updated for your own use.
##### ssid [REQUIRED]
The SSID of your WiFi. Make sure your wifi uses WPA or WPA2 for the PyPortal.
##### password [REQUIRED]
Password of your WiFi.
##### mw_key [REQUIRED]
Go to [Merriam-Webster](https://dictionaryapi.com/register/index) and sign up for a **Collegiate Dictionary** API key. Put your API key in this field.
##### voicerss_key [OPTIONAL]
Sometimes Merriam-Webster doesn't have WAV pronunciations, so [Voice RSS](http://www.voicerss.org/registration.aspx) can be used for pronunciations instead. If opting for MW pronunciations only, set flag `USE_VOICERSS` to `False`

### code.py
Several settings can be changed to alter the functionality of the program
##### WORDS_PER_BATCH
How many words to pull from the API for a 'batch'. These words are continuously rotated in order until it is time for a new batch.
##### TIME_PER_WORD
How many seconds to display a word on screen at once for. Repeated `BATCH_REPETITIONS` times
##### BATCH_REPETITIONS
Number of times to display the batch in order before fetching a new batch of words
##### USE_VOICERSS
Flag to tell the program whether to use Voice RSS as your pronunciation source. Has the benefit that it will *always* have a pronunciation for a word, no matter how strange that word is.