#!/usr/bin/env python3
"""Download the pinned GitHub Release model and verify SHA256 (stdlib only)."""
import argparse,hashlib,json,os,subprocess,tempfile,urllib.request,urllib.parse
from pathlib import Path

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new=super().redirect_request(req,fp,code,msg,headers,newurl)
        if new is not None and urllib.parse.urlparse(req.full_url).netloc != urllib.parse.urlparse(newurl).netloc:
            new.remove_header('Authorization')
        return new

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);a=parser.parse_args()
    root=Path(__file__).resolve().parents[1];manifest=json.loads((root/'model_release.json').read_text())
    output=a.output or root/'src/door_opening_server/models'/manifest['asset']
    def valid(path):return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==manifest['sha256']
    if valid(output):print('Already verified:',output);return
    if output.exists():raise SystemExit('Existing model checksum differs; move it aside before retrying: '+str(output))
    token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token:
        try:
            result=subprocess.run(['gh','auth','token'],capture_output=True,text=True,check=True)
            token=result.stdout.strip()
        except (OSError,subprocess.CalledProcessError):pass
    headers={'Accept':'application/vnd.github+json','User-Agent':'elevator-door-model-downloader'}
    if token:headers['Authorization']='Bearer '+token
    opener=urllib.request.build_opener(SafeRedirect())
    url=f'https://api.github.com/repos/{manifest["repository"]}/releases/tags/{manifest["tag"]}'
    try:
        with opener.open(urllib.request.Request(url,headers=headers),timeout=30) as response:release=json.load(response)
        asset=next(x for x in release['assets'] if x['name']==manifest['asset'])
        request=urllib.request.Request(asset['url'],headers=dict(headers,Accept='application/octet-stream'))
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent,delete=False,suffix='.download') as file:
            temp=Path(file.name)
            try:
                with opener.open(request,timeout=120) as response:
                    while block:=response.read(1024*1024):file.write(block)
            except BaseException:
                temp.unlink(missing_ok=True);raise
        if not valid(temp):temp.unlink();raise RuntimeError('Downloaded model SHA256 mismatch')
        temp.replace(output);print('Verified model:',output)
    except Exception as e:
        raise SystemExit(f'Download failed ({type(e).__name__}). For a private repository, run gh auth login or set GH_TOKEN with repository read access. No token is printed.') from None

if __name__=='__main__':main()
