"""Explicit one-time provisioning surface; never imports or serves AffinityQA."""
import os
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(204 if self.path=='/healthz' else 503)
        self.send_header('Cache-Control','no-store');self.end_headers()
    def log_message(self,*args):pass
if __name__=='__main__':HTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()
