import socket, ssl, select
import json
import sys
import time
from struct import pack, unpack
import datetime
import urlparse
import httplib
from xml.etree import ElementTree

MEDIAPLAYER_APPID = "CC1AD845"
    
def search(device_limit=None, time_limit=5):
    addrs = []
    start_time = datetime.datetime.now() 
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(0)
    req = "\r\n".join(['M-SEARCH * HTTP/1.1',
                       'HOST: 239.255.255.250:1900',
                       'MAN: "ssdp:discover"',
                       'MX: 1',
                       'ST: urn:dial-multiscreen-org:service:dial:1',
                       '',''])
    sock.sendto(req, ("239.255.255.250", 1900))
    while True:
        time_remaining = time_limit - (datetime.datetime.now() - start_time).seconds
        if time_remaining <= 0:
            break
        readable = select.select([sock], [], [], time_remaining)[0]
        if sock in readable:
            st, addr = None, None
            data = sock.recv(1024)
            for line in data.split("\r\n"):
                line = line.replace(" ", "")
                if line.upper().startswith("LOCATION:"):
                    addr = urlparse.urlparse(line[9:].strip()).hostname
                elif line.upper().startswith("ST:"):
                    st = line[3:].strip()
            if addr is not None and st == "urn:dial-multiscreen-org:service:dial:1":
                addrs.append(addr)
                if device_limit and len(addrs) == device_limit:
                    break
    sock.close()
    return addrs
                                      
def get_device_name(ip_addr):
    conn = httplib.HTTPConnection(ip_addr + ":8008")
    conn.request("GET", "/ssdp/device-desc.xml")
    resp = conn.getresponse()
    if resp.status == 200:
        status_doc = resp.read()
        try:
            xml = ElementTree.fromstring(status_doc)
            device_element = xml.find("{urn:schemas-upnp-org:device-1-0}" + "device")
            return device_element.find("{urn:schemas-upnp-org:device-1-0}" + "friendlyName").text
        except ElementTree.ParseError:
            return ""    
    else:
        return ""

def find_device(name=None,time_limit=6):    
    if name is None or name == "":
        print "searching the network for a Chromecast device"
        hosts = search()
        if len(hosts) > 0:
            return hosts[0], get_device_name(hosts[0])
        else:
            return None, None
    
def extract_length_header(msg):
    if len(msg) < 4:
        return None
    len_data = msg[:4]
    remainder = ""
    if len(msg) > 4:
        remainder = msg[4:]
    length = unpack(">I", len_data)[0]
    return length, remainder
    
def extract_field_id(data):
    byte = unpack("B", data)[0]
    return byte >> 3, (byte & 7)    
    
def extract_int_field(data):
    field_id = extract_field_id(data[0])
    int_value = unpack("B", data[1])[0]
    remainder = ""
    if len(data) > 2:
        remainder = data[2:]
    
    return field_id, int_value, remainder
    
def extract_string_field(data):
    field_id = extract_field_id(data[0])    
    length = 0
    ptr = 1
    byte = unpack("B", data[ptr])[0]
    while byte & 128:
        length += byte & 127
        length = length << 7
        ptr += 1
        byte = unpack("B", data[ptr])[0]
    length += byte
    ptr += 1
    string_end_ptr = ptr + length
    string = data[ptr:string_end_ptr]
    remainder = ""
    if len(data) > string_end_ptr:
        remainder = data[string_end_ptr:]
    return field_id, string, remainder

def extract_message(data):
    resp = {}
    field_id, resp['protocol'], data = extract_int_field(data)
    field_id, resp['source_id'], data = extract_string_field(data)
    field_id, resp['destination_id'], data = extract_string_field(data)
    field_id, resp['namespace'], data = extract_string_field(data)
    field_id, resp['payload_type'], data = extract_int_field(data)
    field_id, resp['data'], data = extract_string_field(data)
    return resp
    
def format_field_id(field_no, field_type):
    """ returns a field number & type for packing into the message """
    
    return (field_no << 3) | field_type
    
def format_varint_value(int_value):
    """ returns a varint type integer from a python integer """
    
    varint_result = ""        
    
    while(int_value > 127):
        varint_result += pack("B", int_value & 127 | 128) 
        int_value >>= 7

    varint_result += pack("B", int_value & 127)  #  & 127 unnecessary?
    
    return varint_result

def format_int_field(field_number, field_data):
    field =  pack("B", format_field_id(field_number, 0))   #  0 = Int field type    
    field += pack("B", field_data)  
    return field 

def format_string_field(field_number, field_data):
    field_data_len = format_varint_value(len(field_data))
    field =  pack("B", format_field_id(field_number, 2))   #  2 = Length-delimited field type  
    field += pack("%ds" % len(field_data_len), field_data_len)
    field += pack("%ds" % len(field_data), field_data)   
    return field

def prepend_length_header(msg):
    """ prepends the message with a length value """
    
    return pack(">I%ds" % len(msg), len(msg), msg)
   
def format_message(source_id, destination_id, namespace, data):    
    msg = ""
    msg += format_int_field(1, 0)   # Protocol Version  =  0
    msg += format_string_field(2, source_id)
    msg += format_string_field(3, destination_id)
    msg += format_string_field(4, namespace)
    msg += format_int_field(5, 0)   # payload type : string  =  0
    msg += format_string_field(6, data)
    msg = prepend_length_header(msg)        
    return msg

class MediaController():
    def __init__(self, device_name=None):
        self.host, name = find_device(name=device_name)
        if self.host is None:
            sys.exit("No Chromecast found on the network")
        print "Device:", name
        self.sock = None
        self.request_id = 1
        self.source_id = "sender-0"
        self.receiver_app_status = None
        self.media_status = None
        
    def open_socket(self):
        if self.sock is None:
            self.sock = socket.socket()
            self.sock = ssl.wrap_socket(self.sock)
            self.sock.connect((self.host,8009))
                
    def close_socket(self):
        if self.sock is not None:
            self.sock.close()
        self.sock = None

    def send_data(self, namespace, data_dict):
        data = json.dumps(data_dict)
        msg = format_message(self.source_id, self.destination_id, namespace, data)
        self.sock.write(msg)
        
    def read_message(self):
        data = self.sock.recv(4)
        msg_length, data = extract_length_header(data) 
        while len(data) < msg_length:
            data += self.sock.recv(2048)
        message_dict = extract_message(data)
        message = {}
        try:
            message = json.loads(message_dict['data'])
        except:
            pass
        return message   
    
    def get_response(self, request_id):
        resp = {}
        count = 0
        while len(resp) == 0:
            msg = self.read_message()
            msg_type = msg.get("type", msg.get("responseType", ""))
            if msg_type == "PING":
                data = {"type":"PONG"}
                namespace = "urn:x-cast:com.google.cast.tp.heartbeat"
                self.send_data(namespace, data) 
                count += 1
                if count == 2:
                    return resp
            elif msg_type == "RECEIVER_STATUS":
                self.update_receiver_status_data(msg)
            elif msg_type == "MEDIA_STATUS":
                self.update_media_status_data(msg)
            if "requestId" in msg.keys() and msg['requestId'] == request_id:
                resp = msg
        return resp

    def send_msg_with_response(self, namespace, data):
        self.request_id += 1
        data['requestId'] = self.request_id
        self.send_data(namespace, data)
        return self.get_response(self.request_id)
        
    def update_receiver_status_data(self, msg):
        self.receiver_app_status = None
        if msg.has_key('status'):
            status = msg['status']
            if status.has_key('applications'):
                applications = status['applications']
                for application in applications:
                    if application.get("appId") == MEDIAPLAYER_APPID:
                        self.receiver_app_status = application
            if status.has_key('volume'):
                self.volume_status = status['volume']
                        
    def update_media_status_data(self, msg): 
        self.media_status = None
        status = msg.get("status", [])
        if len(status) > 0:  
            self.media_status = status[0] # status is an array - selecting the first result..?                 
        
    def connect(self, destination_id):  
        if self.sock is None:
            self.open_socket()
        self.destination_id = destination_id
        data = {"type":"CONNECT","origin":{}}
        namespace = "urn:x-cast:com.google.cast.tp.connection"
        self.send_data(namespace, data)
    
    def get_receiver_status(self):
        data = {"type":"GET_STATUS"}
        namespace = "urn:x-cast:com.google.cast.receiver"
        self.send_msg_with_response(namespace, data)
    
    def get_media_status(self):
        data = {"type":"GET_STATUS"}
        namespace = "urn:x-cast:com.google.cast.media"
        self.send_msg_with_response(namespace, data)   
                    
    def load(self, content_url, content_type):
        """ Launch the player app, load & play a URL """
        self.connect("receiver-0")
        self.get_receiver_status()
        if self.receiver_app_status is None:
            data = {"type":"LAUNCH","appId":MEDIAPLAYER_APPID}
            namespace = "urn:x-cast:com.google.cast.receiver"
            self.send_msg_with_response(namespace, data)
            if self.receiver_app_status is None:
                self.close_socket()
                sys.exit("Cannot launch the Media Player app")
        session_id = str(self.receiver_app_status['sessionId'])
        transport_id = str(self.receiver_app_status['transportId'])
        self.connect(transport_id)
        data = {"type":"LOAD",
                "sessionId":session_id,
                "media":{
                    "contentId":content_url,
                    "streamType":"buffered",
                    "contentType":content_type,
                    },
                "autoplay":True,
                "currentTime":0,
                "customData":{
                    "payload":{
                        "title:":""
                        }
                    }
                }
        namespace = "urn:x-cast:com.google.cast.media"
        resp = self.send_msg_with_response(namespace, data)
        if resp.get("type", "") == "MEDIA_STATUS":            
            player_state = ""
            while player_state != "PLAYING" and player_state != "IDLE":
                time.sleep(2)        
                self.get_media_status()
                player_state = self.media_status.get("playerState", "")
        self.close_socket()       
    
    def get_status(self):
        """ get the receiver and media status """
        self.connect("receiver-0")
        self.get_receiver_status()
        if self.receiver_app_status is not None:   
            transport_id = str(self.receiver_app_status['transportId']) 
            self.connect(transport_id)
            self.get_media_status()
        status = {'receiver_status':self.receiver_app_status, 
                  'media_status':self.media_status, 
                  'host':self.host, 
                  'client':self.sock.getsockname()}
        self.close_socket()
        return status
        
    def is_idle(self):
        status = self.get_status()
        if status['receiver_status'] is None:
            return True
        if status['media_status']  is None:
            return True
        return status['media_status'].get("playerState", "") == u"IDLE"
