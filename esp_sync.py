
import time
from ampy.pyboard import Pyboard
from ampy.files import Files, DirectoryExistsError
import os
import sys
import getopt
from threading import Thread
import serial
import serial.tools.miniterm
import pathlib
import logging

# pip install adafruit-ampy
# https://github.com/scientifichackers/ampy/blob/master/ampy/cli.py

# windows: pip install LnkParse3

# Script (dirty) to track local file changes in dir and uploads files to the device with micropython
# tracks all files. follows windows lnk (directory)
# one level of dirs
#
# .espignore - patterns to ignore
# .espcache - cache with local files, name, size and last modification time
#
# class EspFile - interaction with board and files, upload, download
# class EspOutput(Thread) - serial port printer
# class FileWatcher - track local files
#
# run example:
# python .\esp_sync.py -pCOM3 -d. -arun
# python .\esp_sync.py -pCOM3
# python3 esp_sync.py -p/dev/ttyUSB0 -afilelist


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

ACTION = None
PORT = None
DIR = None
FILE = None
LNK = False
STATIC_IGNORE = ['.git', '.gitignore', '.espcache', '.espignore', 'LICENSE', 'readme.rst', 'readme.txt', 'readme.md', 'venv', '.idea']

if os.name == "nt":
    import LnkParse3
    LNK = True


def console_help():
    print('esp_sync.py -p <port> -d <work dir> -a <action>\n')
    print('<port>: \n COM port\n')
    print('<action>:\n '
          'filelist - print files on device \n'
          ' get - download all files from device \n'
          ' cache - updates local cache \n'
          ' run - default, start listeners\n'
          ' delete - deletes file from remote, works with -fFilename\n'
          )
    print('<dir>: \n absolute path or . for current dir or nothing for current dir')
    print("\n\nonly <port> is required")


class ProjectFile:
    def __init__(self, name, changed, size, dir):
        self.name = name
        self.changed = changed
        self.size = size
        self.dir = dir

    def __str__(self):
        return self.name + " : " + str(self.changed) + " : " + str(self.size) + " : " + str(self.dir)

    def __eq__(self, other):
        return self.name == other.name and self.changed == other.changed and self.size == other.size

    def get_target(self):
        return self.dir


class FileWatcher:
    def __init__(self, local_path):
        self.ignore = []
        self.local_path = local_path
        self.ignorefile = ".espignore"
        self.cachefile = ".espcache"
        self.cached_files = {}
        self.load_ignore()
        self.load_cachefile()

    def load_cachefile(self):
        espcache = self.local_path + os.sep + self.cachefile
        if os.path.isfile(espcache):
            with open(espcache) as file:
                lines = [line.strip().split(" : ") for line in file]
            for line in lines:
                if len(line) > 1:
                    self.cached_files[line[0]] = ProjectFile(line[0], float(line[1]), int(line[2]), line[3])

    def save_cachefile(self):
        espcache = self.local_path + os.sep + self.cachefile
        cache = self.get_cached_files()
        f = open(espcache, "w")
        for filename in cache:
            f.write(str(cache[filename]))
            f.write('\n')

        f.close()

    def load_ignore(self):
        espignore = self.local_path + os.sep + self.ignorefile
        if os.path.isfile(espignore):
            with open(espignore) as file:
                self.ignore = [line.rstrip() for line in file]
        self.ignore.extend(STATIC_IGNORE)

    def _get_files(self, path, base_dir=""):
        project_files = {}
        for item in path.rglob("*"):
            if set(item.parts).isdisjoint(self.ignore):
                if str(item).endswith(".lnk") and LNK:
                    with open(str(item), 'rb') as indata:
                        lnk = LnkParse3.lnk_file(indata)
                        subdir = lnk.get_json()['link_info']['local_base_path']
                        dir = str(item).replace(str(path.resolve()), "")
                        dir = dir.replace("\\", "/")
                        a = self._get_files(pathlib.Path(subdir), base_dir + dir[:-4])
                        project_files.update(a)
                else:
                    if os.path.isfile(item):
                        name = str(item)
                        dir = str(item).replace(str(path.resolve()), "")
                        dir = dir.replace("\\", "/")
                        dir = base_dir + dir
                        project_files[name] = ProjectFile(name, item.lstat().st_mtime, item.lstat().st_size, dir)

        return project_files

    def get_files(self):
        p = pathlib.Path(self.local_path)
        return self._get_files(p)

    def get_cached_files(self):
        return self.cached_files

    def update_cached_files(self, project_files):
        for project_file in project_files:
            name = project_file.name
            self.cached_files[name] = project_file

        self.save_cachefile()

    def get_files_diff(self):
        diff = []
        project_files = self.get_files()
        cache = self.get_cached_files()
        for file_name in project_files:
            file_name = file_name.lstrip("\\")
            if file_name not in cache or cache[file_name] != project_files[file_name]:
                diff.append(project_files[file_name])

        self.update_cached_files(diff)

        return diff


class EspOutput(Thread):
    def __init__(self, port, baudrate=115200, parity='N'):
        Thread.__init__(self)
        self.baudrate = baudrate
        self.parity = parity
        self.port = port
        self.serial = None
        self.work = True

    def run(self):
        self.serial = serial.Serial(self.port, self.baudrate, parity=self.parity, rtscts=False, xonxoff=False)
        # self.serial.write(b'\x04')
        # self.serial.write(b'\x03')
        logger.debug("listening")
        self.serial.write(b'\x02')
        while self.work:
            line = str(self.serial.readline().decode("utf8"))
            print(line.rstrip())

    def stop(self):
        self.serial.write(b'\x03')
        # self.serial.write(b'\x01')
        self.serial.write(b'\x01')

        time.sleep(1)
        self.work = False
        if self.serial:
            self.serial.close()


class EspFile:
    def __init__(self, port, local_path):
        self.port = port
        self.local_path = local_path
        self.board = None

    def connect_board(self):
        if self.board is None:
            self.board = Pyboard(self.port)
            self.reset()

    def disconnect_board(self):
        if self.board:
            self.board.close()
            time.sleep(1)
            self.board = None

    def create_local_dirs(self, path):
        os.mkdir(path)

    def stop_repl(self):
        pass
        # self.board.serial.write(b'\x04')

    def get_file(self, remote_filename):
        self.reset()
        files = Files(self.board)
        contents = files.get(remote_filename)
        local_filename = self.local_path + os.sep + remote_filename
        local_dir = os.path.dirname(local_filename)
        logger.debug("-> Copy from remote, %s to %s" % (remote_filename, local_dir))
        if not os.path.isdir(local_dir):
            logger.debug("--> Create local dir %s" % (local_dir))
            self.create_local_dirs(local_dir)

        local = open(local_filename, "wb")
        local.write(contents)
        local.close()
        logger.debug("-> DONE")

    def get_file_list(self, path="/"):
        self.reset()
        ret = []
        files = Files(self.board)
        for file in files.ls(path, True, True):
            ret.append(file)

        return ret

    def reset(self):
        self.board.serial.write(b'\x03')
        time.sleep(0.5)
        self.board.serial.write(b'\x01')
        time.sleep(0.5)

    def put_file(self, local_filename, remote_filename):
        self.reset()
        files = Files(self.board)

        logger.debug("-> Copy from local, %s to %s" % (local_filename, remote_filename))
        remote_dir = os.path.dirname(remote_filename)
        remote_dir = remote_dir.lstrip("\\")
        if remote_dir:
            try:
                files.mkdir(remote_dir)
                logger.debug("--> Create remote dir %s" % (remote_dir))
            except DirectoryExistsError:
                pass

        with open(local_filename, "rb") as local:
            data = local.read()
            files.put(remote_filename.replace("\\", "/"), data)
        logger.debug("-> DONE")

    def remove_file(self, remote_filename):
        self.reset()
        files = Files(self.board)
        logger.debug("-> Deleting remote file: %s" % (remote_filename))
        files.rm(remote_filename)


if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hp:d:a:f:", ["port=", "dir=", "action=", "file="])
    except getopt.GetoptError:
        console_help()
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            console_help()
            sys.exit()
        elif opt in ("-p", "--port"):
            PORT = arg
        elif opt in ("-d", "--dir"):
            DIR = arg
        elif opt in ("-a", "--action"):
            ACTION = arg
        elif opt in ("-f", "--file"):
            FILE = arg

    if not ACTION:
        ACTION = "run"
    if DIR == "." or not DIR:
        DIR = os.getcwd() + os.sep

    if not PORT:
        console_help()
        sys.exit(2)

    logger.info('Port ' + PORT)
    logger.info('Dir ' + DIR)
    logger.info('Action ' + ACTION)

    if ACTION == "filelist":
        esp = EspFile(PORT, DIR)
        esp.connect_board()
        files = esp.get_file_list()
        for file in files:
            print(file)
    if ACTION == "delete":
        logger.info("Removing %s " % FILE)
        esp = EspFile(PORT, DIR)
        esp.connect_board()
        esp.remove_file(FILE)

    if ACTION == "get":
        esp = EspFile(PORT, DIR)
        esp.connect_board()
        files = esp.get_file_list()
        for file in files:
            file = (file.split("-", 1)[0]).strip()
            print(file)
            esp.get_file(file)

    if ACTION == "cache":
        filewatch = FileWatcher(DIR)
        project_files = filewatch.get_files_diff()

    if ACTION == "debug":
        pass

    if ACTION == "run":
        serial.tools.miniterm.EXITCHARCTER = b'\x1d'
        esp = EspFile(PORT, DIR)
        filewatch = FileWatcher(DIR)
        output = None
        cnt = 0
        try:
            while True:
                if cnt > 10:
                    logger.info("[still alive]")
                    cnt = 0
                project_files = filewatch.get_files_diff()
                if project_files:
                    if output:
                        output.stop()
                        output = None
                    time.sleep(1)
                    logger.debug("[Uploading files]")
                    esp.connect_board()
                    for file in project_files:
                        logger.info("[Uploading : %s ]" % file)
                        esp.put_file(file.name, file.get_target())
                    esp.disconnect_board()
                    logger.info("[Upload OK]")
                    logger.debug("[Starting debuger]")

                if output is None:
                    output = EspOutput(PORT)
                    output.start()

                time.sleep(2)
                cnt += 1
        except KeyboardInterrupt:
            logger.info("[Stopping debuger]")
            if output:
                output.stop()
