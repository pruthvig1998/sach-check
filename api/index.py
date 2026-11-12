"""Vercel entry point: all routes are rewritten here (see vercel.json)."""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("SACH_CACHE_DIR", "/tmp/cache")      # Vercel disk is read-only except /tmp
os.environ.setdefault("SACH_LEDGER", "/tmp/ledger.json")   # ephemeral; bundled data/ledger_seed.json is merged in
from sach.web import Handler as _H
from http.server import BaseHTTPRequestHandler


class handler(_H, BaseHTTPRequestHandler):                 # Vercel looks for a class named `handler`
    pass
