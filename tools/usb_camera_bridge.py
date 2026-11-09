"""Open the physical D435i RGB interface and feed the ROS GUI's RGB publisher."""
import argparse
import http.client
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlsplit
from PIL import Image


def discover():
    for entry in sorted(Path('/sys/class/video4linux').glob('video*')):
        try:
            interface=(entry/'device').resolve();usb=interface.parent
            if ((usb/'idVendor').read_text().strip()=='8086' and
                (usb/'idProduct').read_text().strip()=='0b3a' and
                (interface/'bInterfaceNumber').read_text().strip()=='03' and
                (entry/'index').read_text().strip()=='0'):
                return '/dev/'+entry.name
        except FileNotFoundError:pass
    raise RuntimeError('No D435i RGB interface found')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--device');parser.add_argument('--url',default='http://127.0.0.1:8878')
    parser.add_argument('--width',type=int,default=640);parser.add_argument('--height',type=int,default=360)
    a=parser.parse_args();device=a.device or discover();url=urlsplit(a.url)
    assert url.scheme=='http' and url.hostname in ('127.0.0.1','localhost')
    stop=threading.Event();latest=[None]
    log=open('/tmp/glass_door_usb_ffmpeg.log','wb')
    process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','warning','-nostdin',
        '-f','v4l2','-input_format','yuyv422','-video_size',f'{a.width}x{a.height}','-framerate','30',
        '-i',device,'-an','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=log)
    def read_frames():
        while not stop.is_set():
            data=process.stdout.read(a.width*a.height*3)
            if len(data)!=a.width*a.height*3:stop.set();break
            latest[0]=(time.time_ns(),data)
    reader=threading.Thread(target=read_frames,daemon=True);reader.start()
    print(f'USB RGB camera opened: {device}, {a.width}x{a.height}/30 FPS -> RGB 640x360/15 FPS',flush=True)
    sent=0;previous=0
    try:
        while not stop.wait(1/15):
            frame=latest[0]
            if frame is None or frame[0]==previous:continue
            stamp,data=frame
            if time.time_ns()-stamp>200_000_000:continue
            previous=stamp
            rgb=Image.frombytes('RGB',(a.width,a.height),data).resize((640,360),Image.Resampling.BILINEAR).tobytes()
            connection=http.client.HTTPConnection(url.hostname,url.port or 80,timeout=2)
            try:
                connection.request('POST','/api/usb_frame',body=rgb,headers={
                    'Content-Type':'application/octet-stream','X-Width':'640','X-Height':'360',
                    'X-Capture-Stamp-Ns':str(stamp)})
                response=connection.getresponse();response.read()
                if response.status!=200:raise RuntimeError(f'RGB bridge HTTP {response.status}')
                sent+=1
                if sent==1 or sent%150==0:print(f'Live USB RGB frames published: {sent}',flush=True)
            except (OSError,RuntimeError) as error:
                print(str(error),flush=True);stop.wait(.5)
            finally:connection.close()
    except KeyboardInterrupt:pass
    finally:
        stop.set();process.terminate()
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()
    if process.returncode not in (0,-15,255):raise SystemExit('Camera stream ended; see /tmp/glass_door_usb_ffmpeg.log')


if __name__=='__main__':main()
