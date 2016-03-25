# p2psp_demo_cast : Run cast.py script and cast a p2psp stream to chromecast.
* Before running cast.py, make sure that a peer is listening for a player in background.
* By default it will search for chromecast* devices on local wifi "network".The chromecast device should be also connected to the same network.
* Name of first device is printed on console.
* Wait till the player is idle.
* OR just stop casting using google-cast extension in chrome browser.

## Demonstratino can be also watched at youtube : [cast](https://www.youtube.com/watch?v=uR_YlNmtUq8&feature=youtu.be) video link.

## Limitations of this demo:
* By default Player port is 9999. Configure peer accordingly or just edit the script accordingly.
* By default content-type of media is "audio/mp3". So make sure the stream is mp3. OR just change the content-type in cast.py file.
