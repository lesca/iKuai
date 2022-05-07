import requests
import json
import asyncio
from datetime import datetime
from os.path import exists

class iKuaiHelper:
    def __init__(self):
        self.config = {
            "refreshRate": 5, # seconds
            "maxOnlineTime": 3000, # 1 hour
            "maxOfflineTime": 300, # 5 min
            "maxIdleTime": 300, # 5 min
            "maxBlockedTime": 600, # 10 min
            "onlineThreshold": 1024, # 1KBps
            "filter": "192.168.101",
        }

        self.devices = [] # device status
        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json;charset=UTF-8',
            # 'Cookie': cookies,
            'Origin': 'http://192.168.2.1',
            'Referer': 'http://192.168.2.1/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36 Edg/100.0.1185.50',
        }
        self.login()
        self.setIgnoredDevices() # self.ignoredDevices
        self.acl_mac("clear") # clear old records

    def login(self, relogin = False):
        cookies = None
        if not relogin and exists("cookies.txt"):
            with open("cookies.txt", "r") as file:
                self.log("Load cookies...")
                cookies = file.read()
                file.close()
        if not relogin and cookies:
            self.headers['Cookie'] = cookies
            return
        # Perform login
        with open("login.json") as file:
            self.log("Load login information ...")
            json_data = json.load(file)
            file.close
        response = requests.post('http://192.168.2.1/Action/login', headers=self.headers, json=json_data, verify=False)
        data = response.headers
        data = data.get('Set-Cookie')
        data = data.split(";")[0]
        cookies = f"{data}; username=switch; login=1"
        with open("cookies.txt", "w") as file:
            self.log("Save cookies...")
            file.write(cookies)
            file.close()
        self.headers['Cookie'] = cookies
        return

    def getOnlineDevices(self):
        json_data = {
            'func_name': 'monitor_lanip',
            'action': 'show',
            'param': {
                'TYPE': 'data,total',
                'ORDER_BY': 'ip_addr_int',
                'orderType': 'IP',
                'limit': '0,100',
                'ORDER': '',
                'FINDS': 'ip_addr,mac,comment,username',
                'KEYWORDS': self.config['filter'],
            },
        }
        response = requests.post('http://192.168.2.1/Action/call', headers=self.headers, json=json_data, verify=False)
        json_data = json.loads(response.text)
        json_data = json_data.get('Data').get('data')
        return json_data

    def acl_mac(self, action, mac = None):
        if action == "add":
            json_data = {
                'func_name': 'acl_mac',
                'action': 'add',
                'param': {
                    'enabled': 'yes',
                    'mac': mac,
                },
            }
            response = requests.post('http://192.168.2.1/Action/call', headers=self.headers, json=json_data, verify=False)

        elif action == "del":
            json_data = {
                'func_name': 'acl_mac',
                'action': 'del',
                'param': {
                    'mac': mac,
                },
            }
            response = requests.post('http://192.168.2.1/Action/call', headers=self.headers, json=json_data, verify=False)
            pass

        elif action == "clear":
            json_data = {
                'func_name': 'acl_mac',
                'action': 'show',
                'param': {
                    'TYPE': 'total,data',
                    'limit': '0,50',
                    'ORDER_BY': '',
                    'ORDER': '',
                },
            }
            response = requests.post('http://192.168.2.1/Action/call', headers=self.headers, json=json_data, verify=False)
            response = json.loads(response.text)
            devices = response.get('Data').get('data')
            for device in devices:
                if not device.get('comment'):
                    self.acl_mac("del", device['mac'])


    def getDevicesWithComments(self):
        json_data = {
            'func_name': 'mac_comment',
            'action': 'show',
            'param': {
                'TYPE': 'total,data',
                'limit': '0,50',
                'ORDER_BY': '',
                'ORDER': '',
            },
        }
        response = requests.post('http://192.168.2.1/Action/call', headers=self.headers, json=json_data, verify=False)
        json_data = json.loads(response.text)
        json_data = json_data.get('Data').get('data')        
        return json_data

    def setIgnoredDevices(self):
        self.ignoredDevices = []
        devices = self.getDevicesWithComments()
        for i,device in enumerate(devices):
            self.ignoredDevices.append(device['mac'])

    def updateDeviceStatus(self, mac, status, now):
        device = next((device for device in self.devices if device['mac'] == mac), None)
        if device is None:
            device = {"mac":mac,"online":0,"idle":0,"blocked":0,"time":0}
            self.devices.append(device)
        if device['blocked']: # blocked device can download if acl ip is used
            return
        device['time'] = now
        if status < self.config['onlineThreshold']: # not connected
            device['idle'] = device['idle'] + self.config['refreshRate']
        else: # connected and new connection
            device['online'] = device['online'] + self.config['refreshRate'] + device['idle'] if device['online'] > 0 else self.config['refreshRate']
            device['idle'] = 0
        pass

    def processOnlineDevices(self):
        now = int(datetime.now().timestamp())
        devices = self.getOnlineDevices()
        for i, device in enumerate(devices):
            if device['mac'] in self.ignoredDevices:
                continue
            self.updateDeviceStatus(device['mac'], device['download'], now)

        for i, device in enumerate(self.devices):
            if device['online'] >= self.config['maxOnlineTime']: # online over 1h
                # block mac 
                device['online'] = 0
                device['blocked'] = now
                self.acl_mac("add", device['mac'])
                self.log(f"block mac - {device['mac']}")
            if device['idle'] >= self.config['maxIdleTime']: # idle over xx min
                # reset online status
                device['online'] = 0
                device['idle'] = 0
                self.log(f"idle reset - {device['mac']}")
            if device['blocked'] and now - device['blocked'] >= self.config['maxBlockedTime']: # block over xx min
                # unblock mac
                device['blocked'] = 0
                self.acl_mac("del", device['mac'])
                self.log(f"unblock mac - {device['mac']}")
            if device['time'] and now - device['time'] >= self.config['maxOfflineTime']: # offline
                # reset online status
                device['online'] = 0
                device['idle'] = 0
                device['time'] = 0
                self.log(f"offline reset - {device['mac']}")

    async def periodicTasks(self):
        while True:
            # process online devices
            self.processOnlineDevices()

            # wait
            self.log(self.devices)
            await asyncio.sleep(self.config['refreshRate'])

    def log(self, msg):
        now = datetime.now()
        if isinstance(msg, list):
            for item in msg:
                print(f"{now} - {item}")
            print(f"{now} - ## End ##")
        else:
            print(f"{now} - {msg}")
            print(f"{now} - =========")

    def on_exit(self):
        self.acl_mac("clear")