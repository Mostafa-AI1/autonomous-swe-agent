import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from src.routing import normalize_route

def test_root():
    assert normalize_route('/') == '/'
