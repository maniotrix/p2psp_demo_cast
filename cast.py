#!/usr/bin/env python
from media_controller import MediaController
import time
def run():
    cast = MediaController()
    status = cast.get_status()
    webserver_ip = status['client'][0]
    print "my ip address: ", webserver_ip
    url = "http://"+webserver_ip+":9999"
    print "playing media from: ", url
    cast.load(url, str("audio/mp3"))
    # wait for playback to complete before exiting
    idle = False
    while not idle:
        time.sleep(1)
        print(cast.get_status())
        idle = cast.is_idle()      
            
if __name__ == "__main__":
    run()
