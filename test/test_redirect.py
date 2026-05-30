import requests

# Test 1: Access /app while components not loaded -> should redirect to /start
print("=== Test 1: /app when components NOT loaded ===")
r = requests.get('http://localhost:5000/app', allow_redirects=False)
print(f"  Status: {r.status_code}")
print(f"  Location: {r.headers.get('Location', 'none')}")
if r.status_code == 302 and r.headers.get('Location') == '/start':
    print("  PASS: Redirect to /start")
else:
    print("  FAIL: Expected 302 redirect to /start")

# Test 2: Access /settings while components not loaded
print("\n=== Test 2: /settings when components NOT loaded ===")
r = requests.get('http://localhost:5000/settings', allow_redirects=False)
print(f"  Status: {r.status_code}")
print(f"  Location: {r.headers.get('Location', 'none')}")
if r.status_code == 302 and r.headers.get('Location') == '/start':
    print("  PASS: Redirect to /start")
else:
    print("  FAIL: Expected 302 redirect to /start")

# Test 3: Access /asr-debug while components not loaded
print("\n=== Test 3: /asr-debug when components NOT loaded ===")
r = requests.get('http://localhost:5000/asr-debug', allow_redirects=False)
print(f"  Status: {r.status_code}")
print(f"  Location: {r.headers.get('Location', 'none')}")
if r.status_code == 302 and r.headers.get('Location') == '/start':
    print("  PASS: Redirect to /start")
else:
    print("  FAIL: Expected 302 redirect to /start")

# Test 4: Access /translation-debug while components not loaded
print("\n=== Test 4: /translation-debug when components NOT loaded ===")
r = requests.get('http://localhost:5000/translation-debug', allow_redirects=False)
print(f"  Status: {r.status_code}")
print(f"  Location: {r.headers.get('Location', 'none')}")
if r.status_code == 302 and r.headers.get('Location') == '/start':
    print("  PASS: Redirect to /start")
else:
    print("  FAIL: Expected 302 redirect to /start")

# Test 5: Access /tts-debug while components not loaded
print("\n=== Test 5: /tts-debug when components NOT loaded ===")
r = requests.get('http://localhost:5000/tts-debug', allow_redirects=False)
print(f"  Status: {r.status_code}")
print(f"  Location: {r.headers.get('Location', 'none')}")
if r.status_code == 302 and r.headers.get('Location') == '/start':
    print("  PASS: Redirect to /start")
else:
    print("  FAIL: Expected 302 redirect to /start")

# Test 6: Access /start should always work
print("\n=== Test 6: /start always accessible ===")
r = requests.get('http://localhost:5000/start', allow_redirects=False)
print(f"  Status: {r.status_code}")
if r.status_code == 200:
    print("  PASS: /start accessible")
else:
    print(f"  FAIL: Status {r.status_code}")
