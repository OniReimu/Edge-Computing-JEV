"""Loopback HTTP OCR worker. One non-preemptive priority queue, real subprocesses."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import itertools
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit


class Worker:
    def __init__(self, node, binary, weights, log, timeout=10, capacity=16):
        self.node, self.binary, self.weights = node, binary, weights
        self.timeout = timeout
        self.queue = queue.PriorityQueue(maxsize=capacity)
        self.counter = itertools.count()
        self.lock = threading.Lock()
        self.active = None
        self.log = Path(log).open('x')
        self.version = subprocess.check_output([binary, '--version'], text=True).splitlines()[0]
        self.hashes = {k: hashlib.sha256((Path(v)/'eng.traineddata').read_bytes()).hexdigest() for k,v in weights.items()}
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while True:
            priority, sequence, item = self.queue.get()
            started = time.monotonic()
            with self.lock:
                self.active = {'id':item['id'], 'tier':item['tier'], 'priority':priority}
            result = dict(id=item['id'], node=self.node, tier=item['tier'], priority=priority,
                sequence=sequence, received_bytes=len(item['image']),
                image_sha256=hashlib.sha256(item['image']).hexdigest(),
                weight_sha256=self.hashes[item['tier']], engine=self.version,
                queue_s=started-item['received'])
            try:
                with tempfile.TemporaryDirectory(prefix='jev-ocr-') as tmp:
                    path = Path(tmp)/'input.png'
                    path.write_bytes(item['image'])
                    cpu0 = os.times().children_user + os.times().children_system
                    # subprocess.run kills and reaps the child before raising TimeoutExpired.
                    process = subprocess.run([self.binary, str(path), 'stdout', '--tessdata-dir',
                        self.weights[item['tier']], '-l', 'eng', '--oem', '1', '--psm', '8'],
                        env={**os.environ, 'OMP_THREAD_LIMIT':'1'}, capture_output=True,
                        timeout=self.timeout)
                    result.update(status='ok' if process.returncode==0 else 'ocr_error',
                        text=process.stdout.decode('utf-8', errors='replace'),
                        stderr=process.stderr.decode('utf-8', errors='replace'),
                        returncode=process.returncode,
                        cpu_s=os.times().children_user+os.times().children_system-cpu0)
            except subprocess.TimeoutExpired:
                result.update(status='ocr_timeout', text='')
            except Exception as exc:
                result.update(status='worker_error', text='', error_type=type(exc).__name__)
            result['execution_s'] = time.monotonic()-started
            with self.lock:
                self.log.write(json.dumps(result)+'\n')
                self.log.flush()
                self.active = None
            item['result'] = result
            item['event'].set()
            self.queue.task_done()


def server(worker, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body):
            data = json.dumps(body).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Work still completed and is present in the durable server ledger.

        def do_GET(self):
            if self.path != '/health':
                return self.reply(404, {'error':'not_found'})
            with worker.lock:
                body = dict(node=worker.node, engine=worker.version, weights=worker.hashes,
                    active=worker.active, waiting=worker.queue.qsize(), workers=1,
                    omp_thread_limit=1, job_id=os.environ.get('SLURM_JOB_ID'))
            self.reply(200, body)

        def do_POST(self):
            parts = urlsplit(self.path)
            if parts.path != '/ocr':
                return self.reply(404, {'error':'not_found'})
            try:
                from PIL import Image
                query = parse_qs(parts.query, strict_parsing=True)
                if set(query) != {'id','tier','priority'} or any(len(v)!=1 for v in query.values()):
                    raise ValueError('Invalid parameters')
                request_id, tier, priority = query['id'][0], query['tier'][0], int(query['priority'][0])
                length = int(self.headers.get('Content-Length','0'))
                if tier not in worker.weights or priority not in (0,1) or not 0<len(request_id)<=100 or not 0<length<=8*1024*1024:
                    raise ValueError('Invalid parameters')
                self.connection.settimeout(15)
                data = self.rfile.read(length)
                if len(data)!=length:
                    raise ValueError('Truncated body')
                with Image.open(io.BytesIO(data)) as im:
                    if im.format != 'PNG' or im.width*im.height>16000000:
                        raise ValueError('Require bounded PNG')
                    im.verify()
            except Exception:
                return self.reply(400, {'error':'invalid_request'})
            item = dict(id=request_id, tier=tier, image=data, event=threading.Event(), received=time.monotonic())
            try:
                worker.queue.put_nowait((priority,next(worker.counter),item))
            except queue.Full:
                return self.reply(429, {'error':'queue_full','node':worker.node,'received_bytes':len(data)})
            item['event'].wait()
            self.reply(200, item['result'])
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--node',required=True)
    p.add_argument('--port',type=int,required=True)
    p.add_argument('--binary',default='tesseract')
    p.add_argument('--weights',required=True)
    p.add_argument('--log',required=True)
    args=p.parse_args()
    weights={tier:str(Path(args.weights)/name) for tier,name in [('standard','tessdata_fast'),('high','tessdata_best')]}
    worker=Worker(args.node,args.binary,weights,args.log)
    service=server(worker,args.port)
    print(json.dumps(dict(ready=True,node=args.node,port=service.server_port,engine=worker.version,weights=worker.hashes)),flush=True)
    service.serve_forever()


if __name__=='__main__':
    main()
