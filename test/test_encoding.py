import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
s1 = '是。'
s2 = '是这样。'
print('s1:', repr(s1), 'bytes:', s1.encode('utf-8'))
print('s2:', repr(s2), 'bytes:', s2.encode('utf-8'))
print('startswith:', s2.startswith(s1))
print('s2[:2]:', repr(s2[:2]))
print('s2[:2]==s1:', s2[:2]==s1)
print('ord(s1[0]):', hex(ord(s1[0])))
print('ord(s2[0]):', hex(ord(s2[0])))
print('Version:', sys.version)