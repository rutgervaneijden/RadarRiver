import mss
import numpy as np
from PIL import Image, ImageGrab
from serial import Serial
import socket
from threading import Thread
from time import localtime, sleep
import xml.etree.ElementTree
import configparser
import os

keyb_ser_port = 'COM2'
gem_nmea_server_address = '192.168.254.5'
gem_nmea_server_port = 1234
gem_keyb_server_address = '192.168.254.5'
gem_keyb_server_port = 1235
nmea_recv_port = 55551
rar_dest_address = '192.168.254.75'
rar_dest_port = 55550
edp_address = '192.168.254.75'
edp_port = 9999

tx = 1
tune_mode = "M"
tune_val = 1
gain_val = 1
rain_val = 1
sea_mode = "M"
sea_val = 1

def ser_connect(port):    
    while True:
        try:
            conn = Serial(port)
            return conn        
        except Exception as e:
            print(f"ser_connect: {e}")
        finally:
            sleep(1)

def tcp_connect(addr, port):    
    while True:
        conn = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            conn.connect((addr, port))
            return conn        
        except Exception as e:
            print(f"tcp_connect {addr, port}: {e}")            
        finally:
            sleep(1)

def udp_connect(addr, port):    
    while True:
        conn = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            conn.bind((addr, port))
            return conn        
        except Exception as e:
            print(f"udp_connect {addr, port}: {e}")            
        finally:
            sleep(1)

def rar_send():
    global tx
    global tune_mode
    global tune_val
    global gain_val
    global rain_val
    global sea_mode
    global sea_val
    
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        sentence = f"RAR,{tx},{tune_mode},{tune_val},{gain_val},{rain_val},{sea_mode},{sea_val}"
        csum = 0
        for c in sentence:
            csum ^= ord(c)
        print(f"$--{sentence}*{csum}\r\n")
        s.sendto(f"$--{sentence}*{csum}\r\n".encode(), (rar_dest_address, rar_dest_port))

def nmea_bridge():
    nmea_in = udp_connect('0.0.0.0', nmea_recv_port)
    nmea_out = tcp_connect(gem_nmea_server_address, gem_nmea_server_port)
    while True:
        data, addr = nmea_in.recvfrom(1024)
        nmea_out.send(data)

def grab_image():
    
    with mss.mss() as sct:
        monitor = {"top": 0, "left": 0, "width": 1050, "height": 1680}
        output = "sct-{top}x{left}_{width}x{height}.png".format(**monitor)
        sct_img = sct.grab(monitor)
        px = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
    return px

def get_sea(px):
    global sea_mode
    global sea_val
    
    color = px.getpixel((504, 1500))
    if color == (255, 255, 255) or color == (230, 230, 230):
        sea_mode = "A"
    else:
        sea_mode = "M"
    
    for x in range (535, 650, 1):
        color = px.getpixel((x, 1497))
        if color == (255, 255, 255) or color == (192, 192, 192):
            sea_val = int((x - 530) / 1.2)
            break
         
def get_gain(px):
    global gain_val
    
    for x in range (535, 650, 1):
        color = px.getpixel((x, 1450))
        if color == (255, 255, 255) or color == (192, 192, 192):
            gain_val = int((x - 530) / 1.2)
            break
        
def get_tuning(px):
    global tune_mode
    global tune_val
    
    color = px.getpixel((504, 1430))
    
    if color == (255, 255, 255) or color == (230, 230, 230):
        tune_mode = "A"
    else:
        tune_mode = "M"
    
    for x in range (535, 650, 1):
        color = px.getpixel((x, 1426))
        if color == (255, 255, 255) or color == (192, 192, 192):
            tune_val = int((x - 530) * 2.17)
            break

def get_rain(px):
    global rain_val

    for x in range (535, 650, 1):
        color = px.getpixel((x, 1473))
        #color = px[x, 1473]
        if color == (255, 255, 255) or color == (192, 192, 192):
            rain_val = int((x - 530) / 1.2)
            break

def keyb_bridge():
    global tx
    keyb_in = ser_connect(keyb_ser_port)
    keyb_out = tcp_connect(gem_keyb_server_address, gem_keyb_server_port)
    while True:
        data0 = keyb_in.read()
        keyb_out.send(data0)
                
        if data0 == b'Q':
            data1 = keyb_in.read(3)
            keyb_out.send(data1)
            if data1 == b'KPK': tx = 1
            if data1 == b'LPL': tx = 0
        elif data0 == b'U':
            data1 = keyb_in.read(2)
            keyb_out.send(data1)
            px = grab_image()
            get_tuning(px)
        elif data0 == b'S':
            data1 = keyb_in.read(2)
            keyb_out.send(data1)
            px = grab_image()
            get_rain(px)
        elif data0 == b'R':
            data1 = keyb_in.read(2)
            keyb_out.send(data1)
            px = grab_image()
            get_gain(px)
        elif data0 == b'T':
            data1 = keyb_in.read(2)
            keyb_out.send(data1)
            px = grab_image()
            get_sea(px)
        
        rar_send()
        

def shipshape():
    edp = tcp_connect(edp_address, edp_port)

    while True:

        data = edp.recv(999999999)
        
        if data != b'<prefab/>\r\n':
        
            root = xml.etree.ElementTree.fromstring(data.decode())
            info = root[0]
            elements = root[1]
            
            for child in info.findall('code'): code = child.text
            for child in info.findall('name'): name = child.text
            for child in info.findall('length'): length = float(child.text)
            for child in info.findall('width'): width = float(child.text)
            
            print(f"Assigned to {code} ({name}) as {elements[0][0].text}")
            
            for child in elements.iter('element'):
            
                # if child.attrib['group'] == "CameraSlots" and child.attrib['id'] == "HelmsmanCameraSlot1":
                    # helm = child[1].text.split(",")
                    # aheadCrp = length / 2 - float(helm[1])
                    # asternCrp = length - aheadCrp
                    # leftCrp = width / 2
                    # rightCrp = width / 2
                
                if child.attrib['group'] == "Sensors" and child.attrib['type'] == "Sensors::DGPS":
                    dgps = child[1].text.split(",")
                    print(f"DGPS: {dgps}")
                    dgpsx = float(dgps[0])
                    dgpsy = float(dgps[1])
                    dgpsz = float(dgps[2])
                    # dist_to_bow = length / 2 - dgpsy
                    # dist_to_stern = length - dist_to_bow
                    # dist_to_larboard = width / 2 - dgpsx
                    # dist_to_starboard = width - dist_to_larboard
                    
                if child.attrib['group'] == "Sensors" and child.attrib['type'] == "Sensors::Radar":

                    radar_name = child[0].text.lower().replace(" ", "")

                    if radar_name == "radar" or radar_name == "radar1" or radar_name == "radarx-band":
                        single_radar = True
                        radar1 = child[1].text.split(",")
                        print(f"RADAR1: {radar1}")
                        radar1x = float(radar1[0])
                        radar1y = float(radar1[1])
                        radar1z = float(radar1[2])
                            
                    if radar_name == "radar2" or radar_name == "radars-band":
                        single_radar = False
                        radar2 = child[1].text.split(",")
                        print(f"RADAR2: {radar2}")
                        radar2x = float(radar2[0]) - dgpsx
                        radar2y = float(radar2[1]) - dgpsy
                        radar2z = float(radar2[2]) - dgpsz
            
            if single_radar:
                aheadCrp = length / 2 - radar1y
                asternCrp = length - aheadCrp
                leftCrp = width / 2 - radar1x
                rightCrp = width -leftCrp
                offsetxradar = 0
                offsetyradar = 0
                offsethradar = radar1z
            else:
                aheadCrp = length / 2 - radar2y
                asternCrp = length - aheadCrp
                leftCrp = width / 2 - radar2x
                rightCrp = width -leftCrp
                offsetxradar = 0
                offsetyradar = 0
                offsethradar = radar2z
            
            offsetxgps = 0
            offsetygps = 0
            config = configparser.ConfigParser()
            config.read('C:\\Program Files (x86)\\GEM elettronica\\RadarRiver\\Save\\InstallData.ini')
            config.set('Crp', 'aheadCrp', str(aheadCrp))
            config.set('Crp', 'asternCrp', str(asternCrp))
            config.set('Crp', 'leftCrp', str(leftCrp))
            config.set('Crp', 'rightCrp', str(rightCrp))
            config.set('OffsetRadar', 'offsetxradar', str(offsetxradar))
            config.set('OffsetRadar', 'offsetyradar', str(offsetyradar))
            config.set('OffsetRadar', 'offsethradar', str(offsethradar))
            config.set('OffsetGps', 'offsetxgps', str(offsetxgps))
            config.set('OffsetGps', 'offsetygps', str(offsetygps))
            with open('C:\\Program Files (x86)\\GEM elettronica\\RadarRiver\\Save\\InstallData.ini', 'w') as configfile:
                config.write(configfile)
            
            print("Stopping RadarRiver.exe to reload InstallData.ini") # Watchdog will restart RadarRiver.exe
            os.system("TASKKILL /F /IM RadarRiver.exe")

        else:
        
            print("Unassigned")


thread0 = Thread(target=nmea_bridge, daemon=True)
thread0.start()

thread1 = Thread(target=keyb_bridge, daemon=True)
thread1.start()

thread2 = Thread(target=shipshape, daemon=True)
#thread2.start()


while True:
    pass


