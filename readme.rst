esp_sync

Script (dirty) to track local file changes in dir and uploads files to the device with micropython
tracks only *.py. one level of dirs

[more]

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


Use any IDE you want

'esp_sync.py -p <port> -d <work dir> -a <action>\n'
'<port>: \n COM port\n'
'<action>:\n '
      'filelist - print files on device \n'
      ' get - download all files from device \n'
      ' cache - updates local cache \n'
      ' run - default, start listeners\n'

'<dir>: \n absolute path or . for current dir or nothing for current dir'
"\n\nonly <port> is required"


