esp_sync

Script (dirty) to track local file changes in dir and uploads files to the device with micropython
tracks only *.py. one level of dirs

read more: https://koscis.wordpress.com/2024/01/20/esp_sync/

requires: pip install adafruit-ampy

.espignore - patterns to ignore

.espcache - cache with local files, name, size and last modification time

class EspFile - interaction with board and files, upload, download

class EspOutput(Thread) - serial port printer

class FileWatcher - track local files



run example:
    python .\esp_sync.py -pCOM3 -d. -arun

    python .\esp_sync.py -pCOM3

    python3 esp_sync.py -p/dev/ttyUSB0 -afilelist


Use any IDE you want, it just sync files.

esp_sync.py -p <port> -d <work dir> -a <action>

<port>: COM port

<action>:
      filelist - print files on device
      get - download all files from device
      cache - updates local cache
      run - default, start listeners

<dir>: absolute path or . for current dir or nothing for current dir
only <port> is required


