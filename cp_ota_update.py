import os
import gc
import board
import microcontroller
import busio
from digitalio import DigitalInOut
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_requests as requests

class CPprojectOTA:

    def __init__(self, github_repo, module='', main_dir='main', headers={}):
        self.http_client = HttpClient(headers=headers)
        self.github_repo = github_repo.rstrip('/').replace('https://github.com', 'https://api.github.com/repos')
        self.main_dir = main_dir
        self.module = module.rstrip('/')

    @staticmethod
    def using_network(ssid, password):
        #import network
        esp32_cs = DigitalInOut(board.ESP_CS)
        esp32_ready = DigitalInOut(board.ESP_BUSY)
        esp32_reset = DigitalInOut(board.ESP_RESET)

        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

        print("Connecting to AP...")
        while not esp.is_connected:
            try:
                esp.connect_AP(ssid, password)
            except RuntimeError as e:
                print("could not connect to AP, retrying: ", e)
                continue
        print("Connected to", str(esp.ssid, "utf-8"), "\tRSSI:", esp.rssi)
        requests.set_socket(socket, esp)

    def check_for_update_to_install_during_next_reboot(self):
        current_version = self.get_version(self.modulepath(self.main_dir))
        latest_version = self.get_latest_version()

        print('Checking version... ')
        print('\tCurrent version: ', current_version)
        print('\tLatest version: ', latest_version)
        if latest_version > current_version:
            print('New version available, will download and install on next reboot')
            #if 'next' not in os.listdir(self.module):
                #print("Creating NEXT directory at {}".format(self.modulepath('next')))
            os.mkdir(self.modulepath('next'))
            with open(self.modulepath('next/.version_on_reboot'), 'w') as versionfile:
                versionfile.write(latest_version)
                versionfile.close()

    def download_and_install_update_if_available(self):  # , ssid, password):
        if 'next' in os.listdir(self.module):
            if '.version_on_reboot' in os.listdir(self.modulepath('next')):
                latest_version = self.get_version(self.modulepath('next'), '.version_on_reboot')
                print('New update found: ', latest_version)
                self._download_and_install_update(latest_version)  #, ssid, password)
        else:
            print('No new updates found...')

    def _download_and_install_update(self, latest_version):   #, ssid, password):
        #CPprojectOTA.using_network(ssid, password)

        self.download_all_files(self.github_repo + '/contents/' + self.main_dir, latest_version)
        if self.modulepath(self.main_dir)  in os.listdir("/"):
            self.rmtree(self.modulepath(self.main_dir))
        os.rename(self.modulepath('next/.version_on_reboot'), self.modulepath('next/.version'))
        os.rename(self.modulepath('next'), self.modulepath(self.main_dir))
        print('Update installed (', latest_version, '), will reboot now')
        microcontroller.reset()

    def apply_pending_updates_if_available(self):
        if 'next' in os.listdir(self.module):
            if '.version' in os.listdir(self.modulepath('next')):
                pending_update_version = self.get_version(self.modulepath('next'))
                print('Pending update found: ', pending_update_version)
                self.rmtree(self.modulepath(self.main_dir))
                os.rename(self.modulepath('next'), self.modulepath(self.main_dir))
                print('Update applied (', pending_update_version, '), ready to rock and roll')
            else:
                print('Corrupt pending update found, discarding...')
                self.rmtree(self.modulepath('next'))
        else:
            print('No pending update found')

    def download_updates_if_available(self):
        current_version = self.get_version(self.modulepath(self.main_dir))
        latest_version = self.get_latest_version()

        print('Checking version... ')
        print('\tCurrent version: ', current_version)
        print('\tLatest version: ', latest_version)
        if latest_version > current_version:
            print('Updating...')

            os.mkdir(self.modulepath('next'))
            self.download_all_files(self.github_repo + '/contents/' + self.main_dir, latest_version)
            with open(self.modulepath('next/.version'), 'w') as versionfile:
                versionfile.write(latest_version)
                versionfile.close()

            return True
        return False

    def rmtree(self, directory):
        for entry in os.listdir(directory):
            is_dir = os.stat(directory + '/' + entry)[0] == 0x4000
            if is_dir:
                self.rmtree(directory + '/' + entry)
            else:
                print("removing {}".format(directory + '/' + entry))
                os.remove(directory + '/' + entry)
        print("RMDIR {}".format(directory))
        os.rmdir(directory)

    def get_version(self, directory, version_file_name='.version'):
        try:
            if version_file_name in os.listdir(directory):
                f = open(directory + '/' + version_file_name)
                version = f.read()
                f.close()
                return version
        except:
            return '0.0'

    def get_latest_version(self):
        print("Getting Latest Version)")
        latest_release = self.http_client.get(self.github_repo + '/releases/latest')
        version = latest_release.json()['tag_name']
        latest_release.close()
        return version

    def download_all_files(self, root_url, version):
        file_list = self.http_client.get(root_url + '?ref=refs/tags/' + version)
        for file in file_list.json():
            if file['type'] == 'file':
                download_url = file['download_url']
                download_path = self.modulepath('next/' + file['path'].replace(self.main_dir + '/', ''))
                self.download_file(download_url.replace('refs/tags/', ''), download_path)
            elif file['type'] == 'dir':
                path = self.modulepath('next/' + file['path'].replace(self.main_dir + '/', ''))
                try:
                    os.mkdir(path)
                except:
                    print("Unable to create {}".format(path))
                self.download_all_files(root_url + '/' + file['name'], version)

        file_list.close()

    def download_file(self, url, path):
        print('\tDownloading: ', path)
        with open(path, 'w') as outfile:
            try:
                response = self.http_client.get(url)
                outfile.write(response.text)
            finally:
                response.close()
                outfile.close()
                gc.collect()

    def modulepath(self, path):
        return self.module + '/' + path if self.module else path








class HttpClient:

    def __init__(self, headers={}):
        self._headers = headers

    # def request(self, method, url, data=None, json=None, headers={}, stream=None):
    #     def _write_headers(sock, _headers):
    #         for k in _headers:
    #             sock.write(b'{}: {}\r\n'.format(k, _headers[k]))
    #
    #     try:
    #         proto, dummy, host, path = url.split('/', 3)
    #     except ValueError:
    #         proto, dummy, host = url.split('/', 2)
    #         path = ''
    #     if proto == 'http:':
    #         port = 80
    #     elif proto == 'https:':
    #         import ussl
    #         port = 443
    #     else:
    #         raise ValueError('Unsupported protocol: ' + proto)
    #
    #     if ':' in host:
    #         host, port = host.split(':', 1)
    #         port = int(port)
    #
    #     ai = usocket.getaddrinfo(host, port, 0, usocket.SOCK_STREAM)
    #     ai = ai[0]
    #
    #     s = usocket.socket(ai[0], ai[1], ai[2])
    #     try:
    #         s.connect(ai[-1])
    #         if proto == 'https:':
    #             s = ussl.wrap_socket(s, server_hostname=host)
    #         s.write(b'%s /%s HTTP/1.0\r\n' % (method, path))
    #         if not 'Host' in headers:
    #             s.write(b'Host: %s\r\n' % host)
    #         # Iterate over keys to avoid tuple alloc
    #         _write_headers(s, self._headers)
    #         _write_headers(s, headers)
    #
    #         # add user agent
    #         s.write('User-Agent')
    #         s.write(b': ')
    #         s.write('MicroPython OTAUpdater')
    #         s.write(b'\r\n')
    #         if json is not None:
    #             assert data is None
    #             import ujson
    #             data = ujson.dumps(json)
    #             s.write(b'Content-Type: application/json\r\n')
    #         if data:
    #             s.write(b'Content-Length: %d\r\n' % len(data))
    #         s.write(b'\r\n')
    #         if data:
    #             s.write(data)
    #
    #         l = s.readline()
    #         # print(l)
    #         l = l.split(None, 2)
    #         status = int(l[1])
    #         reason = ''
    #         if len(l) > 2:
    #             reason = l[2].rstrip()
    #         while True:
    #             l = s.readline()
    #             if not l or l == b'\r\n':
    #                 break
    #             # print(l)
    #             if l.startswith(b'Transfer-Encoding:'):
    #                 if b'chunked' in l:
    #                     raise ValueError('Unsupported ' + l)
    #             elif l.startswith(b'Location:') and not 200 <= status <= 299:
    #                 raise NotImplementedError('Redirects not yet supported')
    #     except OSError:
    #         s.close()
    #         raise
    #
    #     resp = Response(s)
    #     resp.status_code = status
    #     resp.reason = reason
    #     return resp

    def head(self, url, **kw):
        return self.request('HEAD', url, **kw)

    def get(self, url, **kw):
        #return requests.get(url, self._headers )
        return requests.request('GET', url,  headers=self._headers )
        # return self.request('GET', url, **kw)

    def post(self, url, **kw):
        return self.request('POST', url, **kw)

    def put(self, url, **kw):
        return self.request('PUT', url, **kw)

    def patch(self, url, **kw):
        return self.request('PATCH', url, **kw)

    def delete(self, url, **kw):
        return self.request('DELETE', url, **kw)
