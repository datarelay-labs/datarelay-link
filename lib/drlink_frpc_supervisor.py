#!/usr/bin/env python3
"""Linux frpc child isolation inside the existing drlink-client unit.

Canonical TOML stays authoritative. Derived private files reuse existing auth;
there is no management listener or credential. Only changed proxies restart.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def process_start(pid):
    try:
        return Path('/proc/%d/stat' % pid).read_text().rsplit(')',1)[1].split()[19]
    except (OSError, IndexError):
        return ''


def split_config(text):
    # The canonical renderer emits one flat [[proxies]] table per service.
    # Refuse unfamiliar nested layouts rather than silently changing meaning.
    sections=text.split('[[proxies]]')
    common=sections[0].strip()+'\n'
    if 'serverAddr' not in common or 'auth.token' not in common:
        raise ValueError('missing common FRP configuration')
    if re.search(r'^\s*\[',common,re.M) or 'webServer.' in common:
        raise ValueError('configuration requires the legacy FRP runtime')
    result={}
    for section in sections[1:]:
        if re.search(r'^\s*\[',section,re.M):
            raise ValueError('unsupported nested proxy configuration')
        names=re.findall(r'^name\s*=\s*("[^"\n]+")\s*$',section,re.M)
        if len(names)!=1:
            raise ValueError('invalid proxy name')
        name=json.loads(names[0])
        if name in result:raise ValueError('duplicate proxy name')
        result[name]=common+'\n[[proxies]]\n'+section.strip()+'\n'
    if not result:result['']=common  # Management-only connection.
    return result


def private_write(path, text):
    tmp=path.with_name(path.name+'.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f:
            f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)


class Child:
    def __init__(self, name, text, directory, binary):
        self.text=text;self.name=name;self.connected=False;self.ready=False;self.buffer=b''
        self.path=directory/(digest(name)+'.toml')
        private_write(self.path,text)
        self.process=subprocess.Popen([binary,'-c',str(self.path)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.start=process_start(self.process.pid)
        os.set_blocking(self.process.stdout.fileno(),False)
    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        self.process.stdout.close();self.path.unlink(missing_ok=True)
    def consume(self, data):
        self.buffer+=data
        while b'\n' in self.buffer:
            raw,self.buffer=self.buffer.split(b'\n',1)
            line=raw.decode(errors='replace').lower()
            # Parse each child's current connection epoch independently.
            if 'login to server success' in line:
                self.connected=True;self.ready=not self.name
            elif any(x in line for x in ('login server failed','login to server failed','session closed','control worker is closed','try to reconnect','try to connect to server','connect to server error','read from control stream closed')):
                self.connected=False;self.ready=False
            elif '[%s]' % self.name.lower() in line:
                if 'start proxy success' in line:self.ready=self.connected
                elif any(x in line for x in ('start proxy error','start proxy failed','stop proxy')):self.ready=False
        if len(self.buffer)>65536:self.buffer=b''  # Never persist raw FRP output.


class Supervisor:
    def __init__(self, config, directory, binary='/usr/local/bin/frpc'):
        self.config=Path(config);self.directory=Path(directory);self.binary=binary
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.directory.is_symlink() or self.directory.stat().st_uid!=os.geteuid():
            raise ValueError('unsafe runtime directory')
        os.chmod(self.directory,0o700)
        self.children={};self.config_hash='';self.selector=selectors.DefaultSelector();self.retry_after={}
    def reconcile(self):
        text=self.config.read_text();desired=split_config(text)
        # Parse the entire generation before changing any live child.
        for name,c in list(self.children.items()):
            if name not in desired or desired[name]!=c.text or c.process.poll() is not None:
                dead=c.process.poll() is not None
                self.selector.unregister(c.process.stdout);c.stop();del self.children[name]
                if dead:self.retry_after[name]=time.monotonic()+5
        for name,text_child in desired.items():
            if name not in self.children and time.monotonic()>=self.retry_after.get(name,0):
                c=Child(name,text_child,self.directory,self.binary)
                self.children[name]=c;self.selector.register(c.process.stdout,selectors.EVENT_READ,c)
        self.config_hash=digest(text) if set(self.children)==set(desired) else ''
    def snapshot(self):
        return dict(pid=os.getpid(),start=process_start(os.getpid()),invocation=os.environ.get('INVOCATION_ID',''),config_hash=self.config_hash,updated=time.time(),children={name:dict(pid=c.process.pid,start=c.start,ready=bool(c.connected and c.ready and c.process.poll() is None)) for name,c in self.children.items()})
    def close(self):
        for c in self.children.values():c.stop()
        self.children.clear();self.selector.close()
    def run(self):
        stopping=False
        def stop(*_):
            nonlocal stopping
            stopping=True
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        announced=''
        try:
            while not stopping:
                try:self.reconcile()
                except (OSError,ValueError):pass  # Retain last valid generation, fail readiness by hash.
                for key,_ in self.selector.select(.2):
                    try:data=os.read(key.fileobj.fileno(),65536)
                    except BlockingIOError:continue
                    if data:key.data.consume(data)
                snap=self.snapshot();private_write(self.directory/'status.json',json.dumps(snap))
                # Existing installer journal readers retain their startup contract.
                if snap['children'] and all(c['ready'] for c in snap['children'].values()):
                    epoch=digest(json.dumps(snap['children'],sort_keys=True)+self.config_hash)
                    if epoch!=announced:
                        print('login to server success',flush=True)
                        for name in self.children:
                            if name:print('[%s] start proxy success' % name,flush=True)
                        announced=epoch
                else:announced=''
        finally:
            self.close();(self.directory/'status.json').unlink(missing_ok=True)


def live_status(config, invocation):
    """Root-owned fresh exact-config/parent/child generation proof, fail closed."""
    config=Path(config);path=config.parent/'runtime-proxies/status.json'
    try:
        for p in (path,path.parent):
            st=p.lstat()
            if p.is_symlink() or st.st_uid!=os.geteuid() or st.st_mode&0o077:return None
        s=json.loads(path.read_text())
        if s['invocation']!=invocation or not invocation or not 0<=time.time()-s['updated']<3:return None
        if not s['start'] or process_start(s['pid'])!=s['start']:return None
        if s['config_hash']!=digest(config.read_text()):return None
        expected=set(split_config(config.read_text()))
        if set(s['children'])!=expected:return None
        for c in s['children'].values():
            if not c['ready'] or not c['start'] or process_start(c['pid'])!=c['start']:return None
            stat=Path('/proc/%d/stat'%c['pid']).read_text().rsplit(')',1)[1].split()
            if int(stat[1])!=s['pid'] or stat[0]=='Z':return None
        return s
    except (OSError,ValueError,KeyError,TypeError):return None


if __name__=='__main__':
    os.umask(0o077)
    config=Path('/etc/frp/frpc.toml')
    # Preserve explicitly provisioned legacy authenticated Admin API settings.
    if re.search(r'^\s*webServer\.',config.read_text(),re.M):
        os.execv('/usr/local/bin/frpc',['frpc','-c',str(config)])
    Supervisor(config,config.parent/'runtime-proxies').run()
